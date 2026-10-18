"""Re-evaluate only the employee/day of a committed manual leave deletion."""
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime
import io

from sqlalchemy import text

import vera_postgres_job_queue as queue
from vera_facegate_control_log import VN_TZ
from vera_facegate_attendance import EvidenceError

QUEUE = 'leave-penalty-recheck'


class EvidencePending(Exception):
    pass


def enqueue_deleted(conn, rows, *, manual_sheet_id):
    """Commit jobs with the deletion, never reset existing automatic events."""
    count = 0
    for row in rows:
        source = str(row.get('source_sheet_id') or '')
        actor = str(row.get('updated_by') or '').strip().casefold()
        if (source not in {manual_sheet_id, 'postgres:web_v2'}
                or actor.startswith(('auto ', 'đồng bộ ', 'vera · tự động'))):
            continue
        employee = str(row.get('employee_name') or '').strip()
        day = row.get('leave_date')
        uid = str(row.get('record_uid') or '')
        if not employee or not isinstance(day, date) or not uid:
            continue
        # Historical auto rows can have a Sheets mirror. Its event linkage,
        # not the editable actor label, distinguishes it from manual input.
        if conn.execute(text('SELECT 1 FROM vera_auto_check_event WHERE leave_record_uid=:uid LIMIT 1'),
                        {'uid': uid}).scalar():
            continue
        count += queue.enqueue_conn(conn, QUEUE, 'manual-delete:' + uid,
                                    {'employee': employee, 'work_date': day.isoformat()})
    return count


class _TransactionEngine:
    """Adapt existing rule entrypoints without acquiring a nested pool slot."""
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def begin(self):
        with self.conn.begin_nested():
            yield self.conn


def evaluate(conn, employee, day):
    import timesoft_sync_job as sync
    import vera_auto_check as auto
    import vera_facegate_runtime as runtime
    from vera_attendance_source import source_for
    from vera_missing_checkin_absence import process as absence

    if source_for(day) != 'facegate':
        raise EvidencePending('attendance_source_not_facegate')
    if day > datetime.now(VN_TZ).date():
        raise EvidencePending('future_day')
    if not auto.automatic_penalty_employee_eligible(conn, employee, day):
        return
    evidence = [row for row in runtime.records(conn, day, day)
                if auto._norm(row.get('employee_name')) == auto._norm(employee)]
    if len(evidence) != 1 or evidence[0].get('attendance_fine_evidence_ready') is not True:
        raise EvidencePending('attendance_evidence_pending')
    # Use the verified canonical username for every financial and schedule read.
    employee = evidence[0]['employee_name']
    cfg = auto.load_config(conn)
    catalog = auto.load_catalog(conn)
    frames = runtime.worker_frames(conn, [day])
    frames = [(d, frame[frame['employeeInfo.Name'] == employee].copy())
              for d, frame in frames if not frame.empty]
    engine = _TransactionEngine(conn)
    with redirect_stdout(io.StringIO()):
        arrival = sync.process_timesoft_penalties(engine, cfg,
            {sync._employee_key(employee): employee}, catalog, frames, include_synced_history=True)
        breaks = sync.process_break_return_penalties(engine, catalog,
            work_date=day, employee_names={employee})
        missing = absence(conn, work_date=day, employee_names={employee})
    if arrival.get('errors') or breaks.get('errors') or missing.get('review_required'):
        raise EvidencePending('rule_inputs_pending')
    if missing.get('reason') in {'stale_evidence', 'incomplete_or_ambiguous_evidence'}:
        raise EvidencePending('attendance_evidence_changed')


def process_one(engine_instance):
    item = queue.claim_one(engine_instance, QUEUE)
    if not item:
        return False
    try:
        payload = item['payload']
        day = date.fromisoformat(payload['work_date'])
        employee = str(payload['employee'])
        with engine_instance().begin() as conn:
            if not queue.lease_current(conn, item):
                return True
            # Match absence -> leave lock ordering. New manual registrations
            # cannot race the canonical recheck or be ignored during its write.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:missing-checkin-absence'))"))
            from vera_resource_concurrency import lock_transition
            lock_transition(conn, [('leave_employee', employee)], legacy_keys=['vera:phase4:leave_primary'])
            if payload.get('mode') == 'open-break':
                from vera_open_break_exemption import reconcile
                reconcile(conn, employee, day)
            else:
                evaluate(conn, employee, day)
        queue.mark_done(engine_instance, item)
    except (EvidencePending, EvidenceError):
        # Missing/stale device evidence must not lose the request.
        queue.reschedule(engine_instance, item, delay_seconds=60)
    except Exception as exc:
        # Queue diagnostics contain no names, raw scans or SQL parameters.
        queue.mark_retry(engine_instance, item, RuntimeError(type(exc).__name__))
    return True
