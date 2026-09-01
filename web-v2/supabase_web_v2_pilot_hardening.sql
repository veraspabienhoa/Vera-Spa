-- VERA SPA Web V2 pilot hardening.
-- Safe to run repeatedly in the Supabase SQL Editor.

create or replace function public.vera_v2_normalize_login(input_value text)
returns text
language sql
immutable
security invoker
set search_path = pg_catalog
as $function$
  select trim(regexp_replace(
    translate(
      lower(coalesce(input_value, '')),
      'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ',
      'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd'
    ),
    '\s+',
    ' ',
    'g'
  ));
$function$;

create or replace function public.vera_v2_employees()
returns table(username text, full_name text, role text)
language plpgsql
stable
security definer
set search_path = public
as $function$
declare
  caller_username text;
  caller_role text;
begin
  select p.employee_username, lower(coalesce(p.role, ''))
    into caller_username, caller_role
  from public.vera_v2_user_profile p
  where p.auth_user_id = (select auth.uid())
    and p.is_active = true
  limit 1;

  if caller_username is null then
    raise exception 'UNAUTHORIZED';
  end if;

  if caller_role in ('admin', 'quanly', 'letan') then
    return query
      select e.username, coalesce(e.full_name, ''), coalesce(e.role, '')
      from public.employees e
      where coalesce(e.login_locked, false) = false
        and coalesce(e.source_sheet_id, 'credentials') = 'credentials'
        and lower(btrim(coalesce(e.role, ''))) in ('leader', 'nhanvien')
        and coalesce(e.payload->>'Trạng thái làm việc', e.payload->>'employment_status', 'Đang làm việc') = 'Đang làm việc'
      order by e.username;
  else
    return query
      select e.username, coalesce(e.full_name, ''), coalesce(e.role, '')
      from public.employees e
      where coalesce(e.login_locked, false) = false
        and lower(btrim(e.username)) = lower(btrim(caller_username))
      limit 1;
  end if;
end;
$function$;

create or replace function public.vera_v2_leave_records(p_date date)
returns table(
  record_uid text,
  employee_name text,
  leave_reason text,
  detail text,
  penalty numeric,
  updated_by text,
  updated_at timestamptz
)
language plpgsql
stable
security definer
set search_path = public
as $function$
declare
  caller_username text;
  caller_role text;
  permission_payload jsonb := '{}'::jsonb;
  permission_item jsonb;
  permission_matched boolean := false;
  can_view_penalty boolean := false;
begin
  select public.vera_v2_normalize_login(p.employee_username), lower(coalesce(p.role, ''))
    into caller_username, caller_role
  from public.vera_v2_user_profile p
  where p.auth_user_id = (select auth.uid())
    and p.is_active = true
  limit 1;

  if caller_username is null then
    raise exception 'UNAUTHORIZED';
  end if;

  can_view_penalty := caller_role = 'admin';
  if not can_view_penalty then
    select coalesce(s.value_json, '{}'::jsonb)
      into permission_payload
    from public.vera_app_setting s
    where s.category = 'authorization'
      and s.setting_key = 'feature_permissions'
    limit 1;

    for permission_item in
      select entry
      from jsonb_array_elements(coalesce(permission_payload -> 'accounts', '[]'::jsonb)) as entries(entry)
    loop
      if public.vera_v2_normalize_login(permission_item ->> 'target') = caller_username
        and coalesce(permission_item ->> 'feature', '') = 'employee_penalty_view' then
        can_view_penalty := lower(coalesce(permission_item ->> 'allowed', 'false'))
          in ('1', 'true', 'yes', 'y', 'co', 'có', 'x');
        permission_matched := true;
        exit;
      end if;
    end loop;

    if not permission_matched then
      for permission_item in
        select entry
        from jsonb_array_elements(coalesce(permission_payload -> 'roles', '[]'::jsonb)) as entries(entry)
      loop
        if lower(btrim(coalesce(permission_item ->> 'target', ''))) = caller_role
          and coalesce(permission_item ->> 'feature', '') = 'employee_penalty_view' then
          can_view_penalty := lower(coalesce(permission_item ->> 'allowed', 'false'))
            in ('1', 'true', 'yes', 'y', 'co', 'có', 'x');
          exit;
        end if;
      end loop;
    end if;
  end if;

  return query
    select
      l.record_uid,
      l.employee_name,
      l.leave_reason,
      l.detail,
      case when can_view_penalty then l.penalty else null::numeric end,
      l.updated_by,
      l.updated_at
    from public.leave_records l
    where l.leave_date = p_date
    order by l.employee_name, l.record_uid;
end;
$function$;

create or replace function public.vera_v2_leave_summary(p_date date)
returns table(working bigint, leave bigint, paid bigint, unpaid bigint)
language plpgsql
stable
security definer
set search_path = public
as $function$
declare
  active_employees bigint;
begin
  if not public.vera_v2_is_authenticated_employee() then
    raise exception 'UNAUTHORIZED';
  end if;

  select count(*)
    into active_employees
  from public.employees e
  where coalesce(e.login_locked, false) = false
    and coalesce(e.source_sheet_id, 'credentials') = 'credentials'
    and lower(coalesce(e.role, '')) not in ('admin', 'letan', 'locker', 'tapvu');

  return query
  with covered as (
    select
      lower(btrim(l.employee_name)) as employee_key,
      lower(coalesce(l.leave_type, '')) as type_key,
      lower(coalesce(l.leave_reason, '')) as reason_key
    from public.leave_records l
    where l.leave_date = p_date
      and coalesce(l.calculated_days, 0) > 0
      and lower(btrim(coalesce(l.leave_reason, ''))) like 'nghỉ%'
  ), grouped as (
    select
      employee_key,
      bool_or(
        position('có phép' in type_key) > 0
        and position('không phép' in type_key) = 0
      ) as is_paid,
      bool_or(
        position('không phép' in type_key) > 0
        or position('không phép' in reason_key) > 0
      ) as is_unpaid
    from covered
    where employee_key <> ''
    group by employee_key
  )
  select
    greatest(active_employees - count(*), 0)::bigint,
    count(*)::bigint,
    count(*) filter (where is_paid)::bigint,
    count(*) filter (where is_unpaid)::bigint
  from grouped;
end;
$function$;

-- PostgreSQL grants EXECUTE to PUBLIC by default.  Web V2 RPCs are available
-- only after Supabase Auth has issued an authenticated session.
revoke execute on function public.vera_v2_is_authenticated_employee() from public, anon;
revoke execute on function public.vera_v2_normalize_login(text) from public, anon;
revoke execute on function public.vera_v2_me() from public, anon;
revoke execute on function public.vera_v2_employees() from public, anon;
revoke execute on function public.vera_v2_leave_reasons() from public, anon;
revoke execute on function public.vera_v2_leave_records(date) from public, anon;
revoke execute on function public.vera_v2_leave_summary(date) from public, anon;

grant execute on function public.vera_v2_is_authenticated_employee() to authenticated, service_role;
grant execute on function public.vera_v2_normalize_login(text) to authenticated, service_role;
grant execute on function public.vera_v2_me() to authenticated, service_role;
grant execute on function public.vera_v2_employees() to authenticated, service_role;
grant execute on function public.vera_v2_leave_reasons() to authenticated, service_role;
grant execute on function public.vera_v2_leave_records(date) to authenticated, service_role;
grant execute on function public.vera_v2_leave_summary(date) to authenticated, service_role;
