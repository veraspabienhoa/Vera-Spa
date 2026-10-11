"""Bounded production preflight. Logs contain aggregates only; no financial writes."""
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import VN_TZ
import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime
import vera_hc_rules as hc
import vera_auto_check as auto
import vera_web_v2_department_payroll as pay
from vera_attendance_participation import suspended
from vera_holiday_leave import intervals, uncovered
from vera_resource_concurrency import lock_transition
from vera_attendance_source import source_for

RELEASE = '8aa549d5ad56be2ea40cabe7fe34c47f0d32108d'
START = date(2026, 10, 8)
END = date(2026, 10, 11)


def evidence_reasons(data, username, day, now, window):
    """Historical freshness is waived only for positively complete closed captures."""
    reasons = runtime.fine_evidence_reasons(data, username, day, now=now, interval=window)
    if window and window[1] + timedelta(hours=2) < now and day < now.date():
        # fine_evidence_reasons independently proves all required captures reach
        # the closing window. Missing/invalid/future captures remain blockers.
        if reasons == ['stale_archive'] and all(
                runtime.archive_sync(data,date.fromisoformat(str(s['work_date']))) <= now
                for s in data.get('syncs',[]) if runtime.archive_sync(data,date.fromisoformat(str(s['work_date'])))):
            reasons = []
    return reasons


def existing_arrival(conn, day, username):
    params = {'day':day,'name':username}
    rows = conn.execute(text('SELECT reason FROM vera_auto_check_event WHERE work_date=:day AND lower(btrim(employee_name))=lower(btrim(:name))'),params).scalars().all()
    return any(auto._norm(r).startswith('di tre') for r in rows)


def main():
    verify_runtime(RELEASE)
    apply = os.environ.get('VERA_BACKFILL_MODE', 'readonly') == 'apply'
    engine = runtime_engine(readonly=not apply)
    written = []
    try:
        with engine.begin() as conn:
            now = datetime.now(VN_TZ)
            current = hc.policy(conn)
            current['eligible_departments'] = set(hc.definitions(conn))
            configs = pay._employee_config_map(conn)
            paused = auto.penalties_paused(conn)
            if apply:
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hc-rules'))"))
                owners = conn.execute(text('SELECT DISTINCT employee_username FROM vera_work_schedule WHERE work_date BETWEEN :start AND :end'),{'start':START,'end':END}).scalars().all()
                lock_transition(conn,[('leave_employee',name) for name in owners],legacy_keys=['vera:phase4:leave_primary'])
                if paused:
                    raise RuntimeError('paused')
            catalog = auto.load_catalog(conn)
            days = []
            for offset in range((END-START).days+1):
                day = START + timedelta(days=offset)
                if source_for(day) != 'facegate':
                    raise RuntimeError('unexpected_attendance_source')
                data = fg.project_evidence(conn, day, day)
                counts = Counter()
                issues = Counter(i.get('reason', 'unknown') for i in runtime.blocking_issues(data, day))
                for row in hc.scheduled_rows(conn, day):
                    username = row['employee_username']
                    if row['employee_role'] in hc.EXCLUDED or row['hc_department'] in hc.EXCLUDED or suspended(username, day):
                        counts['excluded'] += 1
                        continue
                    if row['hc_department'] in hc.KTV_DEPARTMENTS:
                        counts['ktv_schedule'] += 1
                        continue
                    leaves = [dict(r) for r in conn.execute(text('SELECT leave_reason,penalty FROM leave_records WHERE leave_date=:day AND lower(btrim(employee_name))=lower(btrim(:name))'), {'day':day, 'name':username}).mappings()]
                    exists = conn.execute(text('SELECT 1 FROM vera_hc_penalty_event WHERE work_date=:day AND employee_name=:name'), {'day':day, 'name':username}).scalar()
                    if exists:
                        counts['existing_event'] += 1
                        continue
                    decision = hc.candidate(row, day, data, current, now, leaves)
                    if not decision or decision['kind'] != 'late':
                        counts['no_chargeable_late_decision'] += 1
                        continue
                    counts['late_candidate'] += 1
                    reasons = evidence_reasons(data, username, day, now, hc.interval(day,row['main_start'],row['main_end']))
                    for reason in reasons:
                        counts['blocked_'+reason] += 1
                    if reasons:
                        continue
                    holiday = intervals(conn, decision['start'],decision['end'],[username]).get(username,[])
                    remaining = uncovered(decision['start'],decision['end'],holiday)
                    if not remaining:
                        counts['holiday_covered'] += 1
                        continue
                    if holiday:
                        decision['minutes'] = sum((b-a).total_seconds() for a,b in remaining)/60
                        decision['holiday_periods'] = [{'starts_at':p['starts_at'].isoformat(),'ends_at':p['ends_at'].isoformat()} for p in holiday]
                    rule = hc.active_rule(current,row['hc_department'],decision)
                    if not rule:
                        counts['rule_inactive'] += 1
                        continue
                    config = configs.get(username.casefold()) or pay._settings(conn,row['hc_department'])['config']
                    try:
                        amount = hc.decision_penalty(config,row,day,decision,rule)
                    except ValueError:
                        counts['invalid_pricing'] += 1
                        continue
                    counts['ready' if amount > 0 and not paused else 'paused_or_zero_amount'] += 1
                    if apply and amount > 0:
                        decision['rule'] = rule
                        decision['rule_department_activation'] = dict(hc.rule_switch(current,row['hc_department'],rule))
                        if hc.write_penalty(conn,row,day,decision,amount,current['revision'],config):
                            uid = conn.execute(text('SELECT leave_record_uid FROM vera_hc_penalty_event WHERE work_date=:day AND employee_name=:name'),{'day':day,'name':username}).scalar_one()
                            written.append((uid,day,amount))
                            counts['added'] += 1
                rows = runtime.records(conn,day,day)
                for row in rows:
                    if row.get('employee_role') in auto.AUTO_PENALTY_ROLES and row.get('check_in') and float(row.get('late_minutes') or 0)>0:
                        counts['ktv_late_projection'] += 1
                        username = row['employee_name']
                        if existing_arrival(conn,day,username):
                            counts['ktv_existing_event'] += 1
                            continue
                        leaves = conn.execute(text('SELECT leave_reason,penalty FROM leave_records WHERE leave_date=:day AND lower(btrim(employee_name))=lower(btrim(:name))'),{'day':day,'name':username}).mappings().all()
                        if leaves:
                            positive_arrival = any(auto._norm(l['leave_reason']).startswith('di tre') and float(l['penalty'] or 0)>0 for l in leaves)
                            counts['ktv_existing_positive_arrival_fine' if positive_arrival else 'ktv_other_leave_requires_review'] += 1
                            # Preserve manual decisions and every approved leave;
                            # never resurrect revoked fines or guess allowances.
                            counts['ktv_existing_leave_or_manual_record'] += 1
                            continue
                        if not auto.automatic_penalty_employee_eligible(conn,username,day):
                            counts['ktv_ineligible_assignment'] += 1
                            continue
                        window = fg.shift_interval(day,row.get('shift_start'),row.get('shift_end'))
                        window = tuple(t.replace(tzinfo=VN_TZ) for t in window) if window else None
                        reasons = evidence_reasons(data,username,day,now,window)
                        if not window:
                            reasons.append('missing_vera_shift')
                        for reason in reasons:
                            counts['ktv_blocked_'+reason] += 1
                        if reasons:
                            continue
                        item = auto.catalog_item(catalog,'Đi trễ không phép')
                        if not item or item['days'] != 0 or item['penalty'] <= 0:
                            counts['ktv_invalid_catalog'] += 1
                            continue
                        if intervals(conn,*window,[username]).get(username):
                            counts['ktv_holiday_covered'] += 1
                            continue
                        counts['ktv_ready'] += 1
                        if apply:
                            ok, status = auto.save_violation(conn,work_date=day,employee=username,reason_item=item,detail='Đối soát FaceGate 08–11-10-2026 · Lịch VERA · check-in '+str(row['check_in']),source='VERA · ĐỐI SOÁT ĐI TRỄ 08–11-10-2026',minutes=float(row['late_minutes']),approved_window=window)
                            if not ok or status != 'ADDED':
                                raise RuntimeError('unexpected_writer_result')
                            event_key = f"{day.isoformat()}|{auto._norm(username)}|{auto._norm(item['name'])}"
                            uid = conn.execute(text('SELECT leave_record_uid FROM vera_auto_check_event WHERE event_key=:key'),{'key':event_key}).scalar_one()
                            amount = conn.execute(text('SELECT penalty FROM leave_records WHERE record_uid=:uid'),{'uid':uid}).scalar_one()
                            written.append((uid,day,amount))
                            counts['ktv_added'] += 1
                days.append({'date':day.isoformat(),'counts':dict(counts),'blocking_issue_counts':dict(issues),
                             'archive_complete':runtime.archive_complete(data,day,before=runtime.archive_sync(data,day)),
                             'archive_fresh':runtime.archive_fresh(data,day,now)})
            for uid, day, amount in written:
                actual = conn.execute(text('SELECT leave_date,penalty,calculated_days FROM leave_records WHERE record_uid=:uid'),{'uid':uid}).mappings().one()
                if actual['leave_date'] != day or actual['penalty'] != amount or actual['calculated_days'] != 0 or not START <= day <= END:
                    raise RuntimeError('write_verification_failed')
        # Read back through a new transaction only after the owning commit.
        with engine.begin() as conn:
            for uid, day, amount in written:
                actual = conn.execute(text('SELECT leave_date,penalty,calculated_days FROM leave_records WHERE record_uid=:uid'),{'uid':uid}).mappings().one()
                if actual['leave_date'] != day or actual['penalty'] != amount or actual['calculated_days'] != 0:
                    raise RuntimeError('committed_readback_failed')
        print(json.dumps({'ok':True,'mode':'apply' if apply else 'readonly','database_writes':bool(written),'added_and_committed_verified':len(written),'paused':paused,'days':days},sort_keys=True))
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'database_writes':False}))
        raise SystemExit(1)
