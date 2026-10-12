"""Bounded read-only live checks: counts and configuration booleans only."""
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import VN_TZ
from vera_attendance_source import source_for
import vera_auto_check as auto
import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime

def main():
    expected=os.environ['VERA_VERIFY_SHA']
    if not re.fullmatch(r'[a-f0-9]{40}',expected):raise SystemExit('invalid_expected_revision')
    verify_runtime(expected)
    e=runtime_engine(readonly=True)
    try:
     with e.begin() as c:
      now=datetime.now(VN_TZ);day=now.date()
      paused=auto.penalties_paused(c)
      def switch(table, extra='', params=None):
       if not c.execute(text('SELECT to_regclass(:table)'),{'table':table}).scalar():return None
       value=c.execute(text('SELECT enabled FROM '+table+" WHERE notification_key='missing_checkin'"+extra),params or {}).scalar()
       return True if value is None else bool(value)
      popup=switch('vera_v2_notification_channel_setting'," AND channel='popup'")
      family=switch('vera_v2_notification_setting')
      data=fg.project_evidence(c,day,day)
      eligible=runtime._alert_eligible_users(data,day)
      from types import SimpleNamespace
      from vera_missing_checkin_notifications import current_missing_checkins
      popup_rows=current_missing_checkins(c,SimpleNamespace(role='admin',employee_username='Admin'),now,include_expiry=True)
      yesterday=fg.project_evidence(c,day-__import__('datetime').timedelta(days=1),day-__import__('datetime').timedelta(days=1))
      result={'ok':True,'database_writes':False,'revision_verified':True,'facegate_selected':source_for(day)=='facegate','auto_penalty_running':not paused,'missing_checkin_enabled':family,'missing_checkin_popup_enabled':popup,'archive_complete':runtime.archive_complete(data,day),'archive_fresh':runtime.archive_fresh(data,day,now),'blocking_issue_counts':dict(__import__('collections').Counter(i.get('reason','unknown') for i in runtime.blocking_issues(data,day))),'popup_eligible_employee_count':len(eligible),'popup_candidate_count':len(popup_rows),'previous_day_rename_review_count':len(yesterday.get('rename_reviews',[])),'previous_day_blocking_issue_counts':dict(__import__('collections').Counter(i.get('reason','unknown') for i in runtime.blocking_issues(yesterday)))}
     cron=subprocess.run(['crontab','-l'],capture_output=True,text=True,timeout=5)
     result['minute_cron_verified']=cron.returncode==0 and any(re.match(r'^\s*\*\s+\*\s+\*\s+\*\s+\*\s+',line) and 'vera_facegate_auto_sync.py' in line for line in cron.stdout.splitlines())
     timer=subprocess.run(['systemctl','is-active','--quiet','vera-facegate-sync.timer'],capture_output=True,timeout=5)
     result['timer_active']=timer.returncode==0
     log=Path('/opt/vera-spa/.facegate-sync-last.log')
     result['worker_log_age_seconds']=int(datetime.now(timezone.utc).timestamp()-log.stat().st_mtime) if log.is_file() else None
     print(json.dumps(result,sort_keys=True))
    finally:e.dispose()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__,'database_writes':False}))
        raise SystemExit(1)
