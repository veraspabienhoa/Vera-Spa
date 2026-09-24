import hashlib
import json

import pytest

from vera_face_id_import import load_batch, plan_hash, import_batch
from test_face_id_photos import png


def manifest(tmp_path):
    content = png()
    (tmp_path/'photo.png').write_bytes(content)
    body = {'source':'timesoft', 'entries':[{'employee_code':'42','username':'worker','file':'photo.png','sha256':hashlib.sha256(content).hexdigest(),'mapping_confirmed':True}]}
    path = tmp_path/'manifest.json'
    path.write_text(json.dumps(body))
    return path, body


def test_valid_export_and_plan_binding(tmp_path):
    path, _ = manifest(tmp_path)
    batch = load_batch(path)
    original = plan_hash(batch)
    batch[0]['username'] = 'someone_else'
    assert plan_hash(batch) != original


@pytest.mark.parametrize('change', ['duplicate','hash','unconfirmed','escape'])
def test_reject_ambiguous_or_changed_export(tmp_path, change):
    path, body = manifest(tmp_path)
    if change == 'duplicate': body['entries'] *= 2
    if change == 'hash': body['entries'][0]['sha256'] = '0'*64
    if change == 'unconfirmed': body['entries'][0]['mapping_confirmed'] = False
    if change == 'escape': body['entries'][0]['file'] = '../outside.png'
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError): load_batch(path)


class Conn:
    def __init__(self, existing=False): self.sql=[]; self.existing=existing
    def execute(self, query, params=None):
        sql=str(query); self.sql.append(sql)
        value = True if 'to_regclass' in sql else 'worker' if 'FROM employees' in sql else self.existing if 'SELECT 1' in sql else None
        return type('Result',(),{'scalar':lambda self:value})()


def test_dry_run_has_no_writes_and_apply_requires_plan(tmp_path):
    path,_=manifest(tmp_path); batch=load_batch(path); conn=Conn()
    assert not import_batch(conn,batch)['applied']
    assert all(sql.startswith('SELECT') for sql in conn.sql)
    with pytest.raises(ValueError): import_batch(conn,batch,apply=True,actor='admin')
    assert import_batch(conn,batch,apply=True,actor='admin',expected_plan=plan_hash(batch))['applied']
    assert any('INSERT INTO vera_face_id_import_audit' in sql for sql in conn.sql)


def test_existing_photo_is_never_overwritten(tmp_path):
    path,_=manifest(tmp_path); batch=load_batch(path); conn=Conn(existing=True)
    with pytest.raises(ValueError,match='existing_photo_preserved|previously_imported_mapping'):
        import_batch(conn,batch,apply=True,actor='admin',expected_plan=plan_hash(batch))
    assert all(sql.startswith('SELECT') for sql in conn.sql)
