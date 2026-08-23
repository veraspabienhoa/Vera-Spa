-- VERA SPA Web V2 daily leave statistics and quota highlighting.
-- Safe to run repeatedly in the Supabase SQL Editor.

insert into public.vera_app_setting (
  category, setting_key, value_json, source, updated_by, revision, updated_at
)
values (
  'leave_rules',
  'daily_quota',
  '{"weekday_limit":5,"weekend_limit":3,"phat_sinh_limit":2}'::jsonb,
  'web_v2_daily_stats',
  'codex',
  1,
  now()
)
on conflict (category, setting_key) do nothing;

create or replace function public.vera_v2_leave_daily_stats(p_start date, p_end date)
returns table(
  day date,
  weekday_label text,
  total_leave bigint,
  paid bigint,
  generated bigint,
  unpaid bigint,
  total_penalty numeric,
  paid_limit integer,
  generated_limit integer,
  paid_full boolean,
  generated_full boolean
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
  quota_payload jsonb := '{}'::jsonb;
  weekday_quota integer := 5;
  weekend_quota integer := 3;
  generated_quota integer := 2;
begin
  if p_start is null or p_end is null or p_end < p_start then
    raise exception 'INVALID_DATE_RANGE';
  end if;
  if p_end - p_start > 365 then
    raise exception 'DATE_RANGE_TOO_LARGE';
  end if;

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

  select coalesce(s.value_json, '{}'::jsonb)
    into quota_payload
  from public.vera_app_setting s
  where s.category = 'leave_rules'
    and s.setting_key = 'daily_quota'
  limit 1;

  if coalesce(quota_payload ->> 'weekday_limit', '') ~ '^\d+$' then
    weekday_quota := greatest(0, (quota_payload ->> 'weekday_limit')::integer);
  end if;
  if coalesce(quota_payload ->> 'weekend_limit', '') ~ '^\d+$' then
    weekend_quota := greatest(0, (quota_payload ->> 'weekend_limit')::integer);
  end if;
  if coalesce(quota_payload ->> 'phat_sinh_limit', '') ~ '^\d+$' then
    generated_quota := greatest(0, (quota_payload ->> 'phat_sinh_limit')::integer);
  end if;

  return query
  with raw as (
    select
      l.leave_date,
      coalesce(l.penalty, 0)::numeric as penalty_value,
      public.vera_v2_normalize_login(l.leave_type) as type_key,
      public.vera_v2_normalize_login(l.leave_reason) as reason_key
    from public.leave_records l
    where l.leave_date between p_start and p_end
      and exists (
        select 1
        from public.employees e
        where lower(btrim(e.username)) = lower(btrim(l.employee_name))
          and coalesce(e.login_locked, false) = false
          and coalesce(e.source_sheet_id, 'credentials') = 'credentials'
          and lower(coalesce(e.role, '')) not in ('admin', 'letan', 'locker', 'tapvu')
      )
  ), classified as (
    select
      raw.*,
      case
        when position('khong phep' in type_key) > 0 then 'khong_phep'
        when position('phat sinh' in type_key) > 0 then 'phat_sinh'
        when position('co phep' in type_key) > 0 then 'co_phep'
        when position('khong phep' in reason_key) > 0 then 'khong_phep'
        when position('phat sinh' in reason_key) > 0 then 'phat_sinh'
        when position('co phep' in reason_key) > 0
          or position('nghi phep' in reason_key) > 0
          or position('nghi dam hieu' in reason_key) > 0
          or reason_key ~ '(^|\s)cp($|\s)' then 'co_phep'
        else ''
      end as group_key
    from raw
  ), grouped as (
    select
      classified.leave_date,
      count(*) filter (where group_key <> '')::bigint as total_leave,
      count(*) filter (where group_key = 'co_phep')::bigint as paid,
      count(*) filter (where group_key = 'phat_sinh')::bigint as generated,
      count(*) filter (where group_key = 'khong_phep')::bigint as unpaid,
      sum(penalty_value)::numeric as penalty_sum
    from classified
    group by classified.leave_date
  )
  select
    grouped.leave_date,
    case extract(isodow from grouped.leave_date)::integer
      when 1 then 'Thứ 2'
      when 2 then 'Thứ 3'
      when 3 then 'Thứ 4'
      when 4 then 'Thứ 5'
      when 5 then 'Thứ 6'
      when 6 then 'Thứ 7'
      else 'Chủ nhật'
    end,
    grouped.total_leave,
    grouped.paid,
    grouped.generated,
    grouped.unpaid,
    case when can_view_penalty then grouped.penalty_sum else null::numeric end,
    case when extract(isodow from grouped.leave_date)::integer in (6, 7)
      then weekend_quota else weekday_quota end,
    case when extract(isodow from grouped.leave_date)::integer in (6, 7)
      then 0 else generated_quota end,
    grouped.paid >= case when extract(isodow from grouped.leave_date)::integer in (6, 7)
      then weekend_quota else weekday_quota end,
    case
      when extract(isodow from grouped.leave_date)::integer in (6, 7) then grouped.generated > 0
      when generated_quota = 0 then grouped.generated > 0
      else grouped.generated >= generated_quota
    end
  from grouped
  order by grouped.leave_date;
end;
$function$;

revoke execute on function public.vera_v2_leave_daily_stats(date, date) from public, anon;
grant execute on function public.vera_v2_leave_daily_stats(date, date) to authenticated, service_role;
