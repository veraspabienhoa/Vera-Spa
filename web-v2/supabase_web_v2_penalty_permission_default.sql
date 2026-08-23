-- One-time VERA SPA Web V2 permission baseline.
-- Existing non-admin role/account overrides are reset to false so only Admin
-- sees penalty money initially. Admin can grant the existing
-- employee_penalty_view feature later from Phân quyền chức năng.

begin;

update public.vera_app_setting as setting
set value_json = jsonb_set(
      jsonb_set(
        setting.value_json,
        '{roles}',
        coalesce((
          select jsonb_agg(
            case
              when entry ->> 'feature' = 'employee_penalty_view'
                then jsonb_set(entry, '{allowed}', 'false'::jsonb, true)
              else entry
            end
          )
          from jsonb_array_elements(coalesce(setting.value_json -> 'roles', '[]'::jsonb)) as items(entry)
        ), '[]'::jsonb),
        true
      ),
      '{accounts}',
      coalesce((
        select jsonb_agg(
          case
            when entry ->> 'feature' = 'employee_penalty_view'
              then jsonb_set(entry, '{allowed}', 'false'::jsonb, true)
            else entry
          end
        )
        from jsonb_array_elements(coalesce(setting.value_json -> 'accounts', '[]'::jsonb)) as items(entry)
      ), '[]'::jsonb),
      true
    ),
    source = 'web_v2_penalty_permission_default',
    updated_by = 'system:web_v2_penalty_permission_default',
    revision = coalesce(setting.revision, 0) + 1,
    updated_at = now()
where setting.category = 'authorization'
  and setting.setting_key = 'feature_permissions';

commit;
