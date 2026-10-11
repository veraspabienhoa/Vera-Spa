"""Refresh bounded evidence for overnight October 11 shifts; no fine writes."""
import json
from datetime import datetime
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import VN_TZ
from vera_facegate_sync import sync_day
verify_runtime('8aa549d5ad56be2ea40cabe7fe34c47f0d32108d')
if datetime.now(VN_TZ).date().isoformat() != '2026-10-12':
    raise SystemExit('outside_authorized_refresh_day')
e=runtime_engine()
try:
 for day in ['2026-10-11','2026-10-12']:
  result=sync_day(e,day,apply=True)
  print(json.dumps({k:result[k] for k in ['ok','date','complete_fetch','inserted_count','conflict_count','unmatched_count']}))
finally:e.dispose()
