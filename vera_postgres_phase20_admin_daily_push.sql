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
  identity_text text := '';
BEGIN
  identity_text := CASE TG_TABLE_NAME
    WHEN 'employees' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.username ELSE NEW.username END), '')
    WHEN 'leave_records' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.record_uid ELSE NEW.record_uid END)::text, '')
    WHEN 'vera_app_setting' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.category || '/' || OLD.setting_key ELSE NEW.category || '/' || NEW.setting_key END), '')
    WHEN 'vera_dataset_cache' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.dataset_key ELSE NEW.dataset_key END), '')
    WHEN 'vera_phase14_record' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.dataset || '/' || OLD.logical_id ELSE NEW.dataset || '/' || NEW.logical_id END), '')
    WHEN 'vera_v2_user_profile' THEN COALESCE((CASE WHEN TG_OP='DELETE' THEN OLD.employee_username ELSE NEW.employee_username END), '')
    ELSE ''
  END;
  INSERT INTO public.vera_sync_event(dataset_key, event_type, detail, created_at)
  VALUES (TG_TABLE_NAME, lower(TG_OP), left(identity_text, 500), now());
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
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
