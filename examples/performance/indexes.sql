-- Run statements individually in autocommit, never inside BEGIN/COMMIT.
-- Compare with pg_indexes first: leave date/employee indexes already exist in VERA.
SET lock_timeout = '2s';
SET statement_timeout = '120s';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leave_records_date_employee
    ON leave_records (leave_date, employee_name);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leave_records_employee_date
    ON leave_records (employee_name, leave_date DESC);

-- Candidate only for the proposed paged month endpoint's stable ordering.
-- Check EXPLAIN (ANALYZE, BUFFERS) before adding this overlapping index.
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_leave_month_page
--     ON leave_records (leave_date, employee_name, record_uid);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_background_projection_retention
    ON vera_background_job (completed_at, id)
    WHERE queue_name='live_tour_projection' AND status='done' AND locked_at IS NULL;

-- Verify validity after interruption; IF NOT EXISTS does not repair an invalid index.
SELECT c.relname, i.indisvalid, i.indisready
FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
WHERE c.relname IN ('idx_leave_records_date_employee',
                   'idx_leave_records_employee_date',
                   'idx_background_projection_retention');

-- Bounded monthly read: sargable range, no EXTRACT(month/year) on the indexed column.
EXPLAIN (ANALYZE, BUFFERS)
SELECT record_uid, leave_date, employee_name, leave_reason, leave_type
FROM leave_records
WHERE leave_date >= DATE '2026-09-01' AND leave_date < DATE '2026-10-01'
ORDER BY leave_date, employee_name, record_uid
LIMIT 51;
