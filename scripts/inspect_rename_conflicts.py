import json
from collections import Counter
from sqlalchemy import text
from vera_facegate_cutover import runtime_engine, verify_runtime
from vera_facegate_control_log import mapping_device_id
verify_runtime('8aa549d5ad56be2ea40cabe7fe34c47f0d32108d')
e=runtime_engine(readonly=True)
try:
 with e.begin() as c:
  rows=c.execute(text("SELECT x.event_id,x.occurred_at,x.observed_payload_json,o.payload_json FROM vera_facegate_event_conflict x JOIN vera_facegate_event o USING(device_id,event_id,occurred_at) WHERE x.device_id=:device AND x.work_date BETWEEN '2026-10-08' AND '2026-10-12'"),{'device':mapping_device_id()}).mappings().all()
  differences=Counter()
  for r in rows:
   a,b=r['payload_json'],r['observed_payload_json']
   a=json.loads(a) if isinstance(a,str) else a;b=json.loads(b) if isinstance(b,str) else b
   differences.update(k for k in set(a)|set(b) if a.get(k)!=b.get(k))
  print(json.dumps({'conflict_count':len(rows),'all_events_operator_confirmed':all(str(r['event_id']) in {'80905','81064'} for r in rows),'changed_field_counts':dict(differences)}))
finally:e.dispose()
