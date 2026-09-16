-- Phase 22: production Live Tour projection queue watchdog.
-- Independent of GitHub Actions scheduler. Uses the existing Vault webhook secret
-- and pg_net to invoke the production API every 5 minutes.
BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

DO $do$
DECLARE job record;
BEGIN
  FOR job IN SELECT jobid FROM cron.job WHERE jobname='vera-live-tour-queue-watchdog' LOOP
    PERFORM cron.unschedule(job.jobid);
  END LOOP;
END;
$do$;

SELECT cron.schedule(
  'vera-live-tour-queue-watchdog',
  '*/5 * * * *',
  $cron$
    SELECT net.http_post(
      url := 'https://api.veraspa.vn/v2/live-tour/projection-queue/watchdog',
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

-- Deployment verification queries:
SELECT jobid, jobname, schedule, active, command
FROM cron.job
WHERE jobname='vera-live-tour-queue-watchdog';

SELECT jobid, status, return_message, start_time, end_time
FROM cron.job_run_details
WHERE jobid=(SELECT jobid FROM cron.job WHERE jobname='vera-live-tour-queue-watchdog' LIMIT 1)
ORDER BY start_time DESC
LIMIT 10;
