"""Bounded arrival reconciliation; writes require explicit apply mode."""
import json
import hashlib
import math
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
from vera_attendance_rules import supported_late_minutes

RELEASE = '8aa549d5ad56be2ea40cabe7fe34c47f0d32108d'
START = date(2026, 10, 8)
END = date(2026, 10, 11)


# Only these two operator-confirmed scans can receive this bounded metadata
# review. Original events and every conflicting observation remain immutable.
CONFIRMED_OWNER = 'Cậu Tưởng'
CONFIRMED_EVENTS = {'80905':'2026-10-10T08:26:40+07:00', '81064':'2026-10-11T08:22:43+07:00'}
RAW_READ_EVIDENCE = fg.read_evidence


def verified_name_only_conflict(event, conflict, mapping, job, address):
    try:
        event_id = str(event['event_id'])
        if (event_id not in CONFIRMED_EVENTS or str(event['occurred_at']) != CONFIRMED_EVENTS[event_id]
                or str(conflict['event_id']) != event_id or conflict['occurred_at'] != event['occurred_at']):
            return False
        original, observed = event['payload_json'], conflict['observed_payload_json']
        original = json.loads(original) if isinstance(original,str) else original
        observed = json.loads(observed) if isinstance(observed,str) else observed
        digest = lambda p: hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        if (digest(original) != event['payload_sha256'] or digest(original) != conflict['stored_payload_sha256']
                or digest(observed) != conflict['observed_payload_sha256']
                or {k for k in set(original)|set(observed) if original.get(k)!=observed.get(k)} != {'device_name'}):
            return False
        ref = fg.reference(original.get('registration_ref'))
        job_ref = job['registration_ref']
        job_ref = json.loads(job_ref) if isinstance(job_ref,str) else job_ref
        return bool(ref and fg.reference(observed.get('registration_ref')) == ref
            and fg.reference(mapping.get('registration_ref')) == ref and fg.reference(job_ref) == ref
            and mapping.get('confirmed_by') and mapping.get('device_address') == address
            and original.get('device_address') == address and observed.get('device_address') == address
            and auto._norm(mapping.get('username')) == auto._norm(CONFIRMED_OWNER)
            and job['employee_username'] == mapping['username'] and job['status'] == 'verified'
            and job['device_address'] == address and str(job['profile_id']) == str(mapping['profile_id'])
            and job['old_name'] == original['device_name'] and job['new_name'] == observed['device_name']
            and mapping['device_name'] == observed['device_name'])
    except (KeyError,TypeError,ValueError):
        return False


def read_reviewed_evidence(conn, start, end, *, include_conflicts=False):
    result = RAW_READ_EVIDENCE(conn,start,end,include_conflicts=include_conflicts)
    if not include_conflicts or not result[4]:
        return result
    from vera_facegate_control_log import mapping_device_id
    address, mappings, events, syncs, conflicts = result
    device = mapping_device_id()
    owners = [m for m in mappings if auto._norm(m.get('username')) == auto._norm(CONFIRMED_OWNER)]
    if len(owners) != 1 or not conn.execute(text("SELECT 1 FROM employees WHERE username=:name AND COALESCE(payload->>'__deleted','false')<>'true'"),{'name':owners[0]['username']}).scalar():
        return result
    if not conn.execute(text("SELECT to_regclass('vera_facegate_rename_job')")).scalar():
        return result
    jobs = conn.execute(text("SELECT * FROM vera_facegate_rename_job WHERE device_id=:device AND employee_username=:name AND status='verified'"),{'device':device,'name':owners[0]['username']}).mappings().all()
    observed = conn.execute(text("SELECT * FROM vera_facegate_event_conflict WHERE device_id=:device AND work_date BETWEEN :start AND :end"),{'device':device,'start':start.isoformat(),'end':(end+timedelta(days=1)).isoformat()}).mappings().all()
    retained = []
    for conflict in conflicts:
        matching = [e for e in events if e['event_id']==conflict['event_id'] and e['occurred_at']==conflict['occurred_at']]
        versions = [c for c in observed if c['event_id']==conflict['event_id'] and c['occurred_at']==conflict['occurred_at']]
        if (len(matching)!=1 or not versions or not all(any(verified_name_only_conflict(matching[0],c,owners[0],j,address) for j in jobs) for c in versions)):
            retained.append(conflict)
    return address,mappings,events,syncs,retained


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


def arrival_after_allowances(conn, row, day, leaves):
    """Use official saved leave/late allowances; never infer an employee identity."""
    username = row['employee_name']
    minutes = float(row.get('late_minutes') or 0)
    if not math.isfinite(minutes) or minutes <= 0:
        return None, 'invalid_lateness'
    if any(auto._norm(l['leave_reason']).startswith('di tre') and float(l['penalty'] or 0)>0 for l in leaves):
        return None, 'existing_positive_arrival_fine'
    registered, baseline, _ = auto.registered_late_for_day(conn,day,username)
    support, allowance, _ = auto.late_support_for_day(conn,day,username)
    permitted = set(auto.REGISTERED_LATE_REASONS)
    if any('ho tro' not in auto._norm(l['leave_reason']) and auto._norm(l['leave_reason']) not in permitted for l in leaves):
        return None, 'other_leave_or_manual_decision'
    if registered:
        clock = auto.daily_clock(conn,day,username,'late')
        if not clock or not row.get('check_in_at'):
            return None, 'unknown_registered_baseline'
        instant = datetime.fromisoformat(str(row['check_in_at']))
        if instant.tzinfo is None:
            return None, 'invalid_checkin_timestamp'
        instant = instant.astimezone(VN_TZ)
        allowed = datetime.combine(day,datetime.min.time(),tzinfo=VN_TZ)+timedelta(minutes=baseline)
        minutes = max(0.0,(instant-allowed).total_seconds()/60)
    elif support:
        minutes = supported_late_minutes(minutes,allowance)
        if minutes is None:
            return None, 'unknown_support_allowance'
    return minutes, 'allowance_covered' if minutes <= 0 else 'chargeable'


def main():
    verify_runtime(RELEASE)
    fg.read_evidence = read_reviewed_evidence
    apply = os.environ.get('VERA_BACKFILL_MODE', 'readonly') == 'apply'
    engine = runtime_engine(readonly=not apply)
    written = []
    try:
        with engine.begin() as conn:
            now = datetime.now(VN_TZ)
            if apply:
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:hc-rules'))"))
                owners = conn.execute(text('SELECT DISTINCT employee_username FROM vera_work_schedule WHERE work_date BETWEEN :start AND :end'),{'start':START,'end':END}).scalars().all()
                lock_transition(conn,[('leave_employee',name) for name in owners],legacy_keys=['vera:phase4:leave_primary'])
            current = hc.policy(conn)
            current['eligible_departments'] = set(hc.definitions(conn))
            configs = pay._employee_config_map(conn)
            paused = auto.penalties_paused(conn)
            if apply and paused:
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
                        minutes, disposition = arrival_after_allowances(conn,row,day,leaves)
                        if disposition != 'chargeable':
                            counts['ktv_'+disposition] += 1
                            continue
                        counts['ktv_chargeable_after_allowances'] += 1
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
                        checkin = datetime.fromisoformat(str(row['check_in_at']))
                        if checkin.tzinfo is None:
                            raise ValueError('invalid_checkin_timestamp')
                        late_window = (checkin-timedelta(minutes=minutes),checkin)
                        if intervals(conn,*late_window,[username]).get(username):
                            counts['ktv_holiday_covered'] += 1
                            continue
                        counts['ktv_ready'] += 1
                        if apply:
                            ok, status = auto.save_violation(conn,work_date=day,employee=username,reason_item=item,detail='Đối soát FaceGate 08–11-10-2026 · Lịch VERA · check-in '+str(row['check_in']),source='VERA · ĐỐI SOÁT ĐI TRỄ 08–11-10-2026',minutes=minutes,approved_window=late_window)
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
