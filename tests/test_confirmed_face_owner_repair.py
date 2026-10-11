import importlib.util
from pathlib import Path
from datetime import datetime
import pytest
spec=importlib.util.spec_from_file_location('repair_owner',Path(__file__).parents[1]/'scripts/repair_confirmed_face_owner.py')
repair=importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

class Rows:
    def __init__(self, rows): self.rows=rows
    def execute(self,*args): return self
    def mappings(self): return self
    def all(self): return self.rows

def sample():
    ref={'file_type':0,'file_index':0,'file_position':42}
    return [{'event_id':event,'occurred_at':datetime.fromisoformat(at),'payload_json':{'registration_ref':dict(ref)},'payload_sha256':'fixed'} for event,at in repair.EVENTS.items()]

def test_same_confirmed_events_resolve_one_persistent_profile():
    rows=sample()
    assert repair.event_snapshot(Rows(rows),'device')==(rows,(0,0,42))

@pytest.mark.parametrize('change',['missing','wrong_time','missing_reference','different_profiles'])
def test_inexact_operator_evidence_is_rejected(change):
    rows=sample()
    if change=='missing': rows.pop()
    if change=='wrong_time': rows[0]['occurred_at']=rows[1]['occurred_at']
    if change=='missing_reference': rows[0]['payload_json']['registration_ref']=None
    if change=='different_profiles': rows[0]['payload_json']['registration_ref']['file_position']=43
    with pytest.raises(ValueError): repair.event_snapshot(Rows(rows),'device')
