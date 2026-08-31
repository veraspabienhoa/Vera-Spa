-- Phase 21: server-side break reminders/overdue Web Push.
-- Runs independently of whether any browser or iPhone PWA is open.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

DO $do$
DECLARE job record;
BEGIN
  FOR job IN SELECT jobid FROM cron.job WHERE jobname='vera-v2-break-alert-dispatch' LOOP
    PERFORM cron.unschedule(job.jobid);
  END LOOP;
END;
$do$;

SELECT cron.schedule(
  'vera-v2-break-alert-dispatch',
  '*/5 * * * *',
  $cron$
    SELECT net.http_post(
      url := 'https://vera-spa-api-589916994342.asia-southeast1.run.app/v2/attendance/break-alerts/dispatch',
      headers := jsonb_build_object(
        'Content-Type','application/json',
        'x-vera-push-webhook',(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='vera_v2_push_webhook_secret' LIMIT 1)
      ),
      body := '{}'::jsonb,
      timeout_milliseconds := 25000
    );
  $cron$
);

COMMIT;
