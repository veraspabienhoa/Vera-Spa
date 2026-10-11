"""Bounded production preflight. Logs contain aggregates only; no financial writes."""
import json
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

RELEASE = '8aa549d5ad56be2ea40cabe7fe34c47f0d32108d'
START = date(2026, 10, 8)
END = date(2026, 10, 11)


def main():
    verify_runtime(RELEASE)
    engine = runtime_engine(readonly=True)
    try:
        with engine.begin() as conn:
            now = datetime.now(VN_TZ)
            current = hc.policy(conn)
            current['eligible_departments'] = set(hc.definitions(conn))
            configs = pay._employee_config_map(conn)
            paused = auto.penalties_paused(conn)
            days = []
            for offset in range((END-START).days+1):
                day = START + timedelta(days=offset)
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
                    reasons = runtime.fine_evidence_reasons(data, username, day, now=now, interval=hc.interval(day,row['main_start'],row['main_end']))
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
                rows = runtime.records(conn,day,day)
                for row in rows:
                    if row.get('employee_role') in auto.AUTO_PENALTY_ROLES and row.get('check_in') and float(row.get('late_minutes') or 0)>0:
                        counts['ktv_late_projection'] += 1
                        for reason in row.get('attendance_fine_evidence_reasons',[]):
                            counts['ktv_blocked_'+reason] += 1
                days.append({'date':day.isoformat(),'counts':dict(counts),'blocking_issue_counts':dict(issues),
                             'archive_complete':runtime.archive_complete(data,day,before=runtime.archive_sync(data,day)),
                             'archive_fresh':runtime.archive_fresh(data,day,now)})
            print(json.dumps({'ok':True,'mode':'readonly','database_writes':False,'paused':paused,'days':days},sort_keys=True))
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'database_writes':False}))
        raise SystemExit(1)
