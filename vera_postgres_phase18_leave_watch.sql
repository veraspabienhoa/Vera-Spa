-- VERA SPA Web V2 Phase 18: per-user watched leave dates.
-- The browser never accesses this table directly. All reads and writes pass
-- through the authenticated Python API, which filters by auth_user_id.

CREATE TABLE IF NOT EXISTS public.vera_v2_leave_watch (
    auth_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    employee_username TEXT NOT NULL,
    watched_date DATE NOT NULL,
    last_seen_paid_count INTEGER NOT NULL DEFAULT 0 CHECK (last_seen_paid_count >= 0),
    current_paid_count INTEGER NOT NULL DEFAULT 0 CHECK (current_paid_count >= 0),
    has_unread BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (auth_user_id, watched_date)
);

CREATE INDEX IF NOT EXISTS idx_vera_v2_leave_watch_user_unread
ON public.vera_v2_leave_watch(auth_user_id, has_unread, watched_date);

ALTER TABLE public.vera_v2_leave_watch ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.vera_v2_leave_watch FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.vera_v2_leave_watch TO service_role;
