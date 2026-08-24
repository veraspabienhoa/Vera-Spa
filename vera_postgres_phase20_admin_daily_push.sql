-- Phase 20: audit operational mutations and notify Admin once every morning.
-- No password, push key, bank data, payroll amount or revenue value is copied
-- into the audit detail.
BEGIN;

CREATE OR REPLACE FUNCTION public.vera_audit_operational_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $fn$
DECLARE
  -- OLD/NEW have a different composite type for every trigger table.  Accessing
  -- a table-specific field on OLD inside one shared CASE makes PostgreSQL resolve it for
  -- e.g. vera_v2_user_profile as well, which aborts every profile upsert and in
  -- turn breaks the shared Web V2 login bridge.  JSONB keeps the lookup generic.
  row_data jsonb := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
  identity_text text := '';
BEGIN
  identity_text := CASE TG_TABLE_NAME
    WHEN 'employees' THEN COALESCE(row_data ->> 'username', '')
    WHEN 'leave_records' THEN COALESCE(row_data ->> 'record_uid', '')
    WHEN 'vera_app_setting' THEN concat_ws('/', row_data ->> 'category', row_data ->> 'setting_key')
    WHEN 'vera_dataset_cache' THEN COALESCE(row_data ->> 'dataset_key', '')
    WHEN 'vera_phase14_record' THEN concat_ws('/', row_data ->> 'dataset', row_data ->> 'logical_id')
    WHEN 'vera_v2_user_profile' THEN COALESCE(row_data ->> 'employee_username', '')
    ELSE ''
  END;
  INSERT INTO public.vera_sync_event(dataset_key, event_type, detail, created_at)
  VALUES (TG_TABLE_NAME, lower(TG_OP), left(identity_text, 500), now());
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$fn$;

REVOKE ALL ON FUNCTION public.vera_audit_operational_change() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.vera_audit_operational_change() TO service_role;

DO $do$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'employees','leave_records','vera_app_setting','vera_dataset_cache',
    'vera_phase14_record','vera_v2_user_profile'
  ] LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS vera_audit_change ON public.%I', table_name);
    EXECUTE format(
      'CREATE TRIGGER vera_audit_change AFTER INSERT OR UPDATE OR DELETE ON public.%I '
      'FOR EACH ROW EXECUTE FUNCTION public.vera_audit_operational_change()', table_name
    );
  END LOOP;
END;
$do$;

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

DO $do$
DECLARE job record;
BEGIN
  FOR job IN SELECT jobid FROM cron.job WHERE jobname='vera-v2-admin-daily-changes' LOOP
    PERFORM cron.unschedule(job.jobid);
  END LOOP;
END;
$do$;

SELECT cron.schedule(
  'vera-v2-admin-daily-changes',
  '0 1 * * *',
  $cron$
    SELECT net.http_post(
      url := 'https://vera-spa-api-589916994342.asia-southeast1.run.app/v2/push/admin-daily-dispatch',
      headers := jsonb_build_object(
        'Content-Type','application/json',
        'x-vera-push-webhook',(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='vera_v2_push_webhook_secret' LIMIT 1)
      ),
      body := '{}'::jsonb,
      timeout_milliseconds := 15000
    );
  $cron$
);

COMMIT;
