-- VERA SPA Web V2 Phase 19: private Web Push subscriptions and async dispatch.
-- VAPID/webhook values are created separately in Supabase Vault and never
-- committed to source control.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_net;
CREATE SCHEMA IF NOT EXISTS vera_private;

CREATE TABLE IF NOT EXISTS public.vera_v2_push_subscription (
    subscription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    employee_username text NOT NULL,
    endpoint text NOT NULL UNIQUE,
    p256dh text NOT NULL,
    auth_secret text NOT NULL,
    user_agent text NOT NULL DEFAULT '',
    is_active boolean NOT NULL DEFAULT true,
    failure_count integer NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    last_success_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_vera_v2_push_subscription_user_active
ON public.vera_v2_push_subscription(auth_user_id, is_active, updated_at DESC);

ALTER TABLE public.vera_v2_push_subscription ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.vera_v2_push_subscription FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.vera_v2_push_subscription TO service_role;

COMMENT ON TABLE public.vera_v2_push_subscription IS
'Private backend-managed browser push subscriptions for authenticated VERA users.';

CREATE OR REPLACE FUNCTION vera_private.notify_leave_push()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    webhook_secret text;
    affected_dates date[];
BEGIN
    affected_dates := ARRAY(
        SELECT DISTINCT value
        FROM unnest(ARRAY[
            CASE WHEN TG_OP <> 'INSERT' THEN OLD.leave_date ELSE NULL END,
            CASE WHEN TG_OP <> 'DELETE' THEN NEW.leave_date ELSE NULL END
        ]) AS value
        WHERE value IS NOT NULL
    );

    IF COALESCE(array_length(affected_dates, 1), 0) = 0 THEN
        RETURN NULL;
    END IF;

    SELECT decrypted_secret
      INTO webhook_secret
      FROM vault.decrypted_secrets
     WHERE name = 'vera_v2_push_webhook_secret'
     LIMIT 1;

    IF COALESCE(webhook_secret, '') = '' THEN
        RETURN NULL;
    END IF;

    PERFORM net.http_post(
        url := 'https://vera-spa-api-589916994342.asia-southeast1.run.app/v2/push/dispatch',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'X-VERA-Push-Webhook', webhook_secret
        ),
        body := jsonb_build_object('dates', to_jsonb(affected_dates)),
        timeout_milliseconds := 5000
    );
    RETURN NULL;
EXCEPTION WHEN OTHERS THEN
    -- A notification delivery problem must never roll back a leave mutation.
    RAISE WARNING 'VERA Web Push enqueue failed: %', SQLERRM;
    RETURN NULL;
END;
$function$;

REVOKE ALL ON FUNCTION vera_private.notify_leave_push() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS trg_vera_leave_push_insert_delete ON public.leave_records;
CREATE TRIGGER trg_vera_leave_push_insert_delete
AFTER INSERT OR DELETE ON public.leave_records
FOR EACH ROW EXECUTE FUNCTION vera_private.notify_leave_push();

DROP TRIGGER IF EXISTS trg_vera_leave_push_update ON public.leave_records;
CREATE TRIGGER trg_vera_leave_push_update
AFTER UPDATE OF leave_date, leave_reason ON public.leave_records
FOR EACH ROW
WHEN (
    OLD.leave_date IS DISTINCT FROM NEW.leave_date
    OR OLD.leave_reason IS DISTINCT FROM NEW.leave_reason
)
EXECUTE FUNCTION vera_private.notify_leave_push();

COMMIT;
