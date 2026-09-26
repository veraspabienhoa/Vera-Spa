from types import SimpleNamespace
import pytest
from fastapi import HTTPException
import vera_web_v2_work_schedule as schedule

CUSTOMERS = [dict(id='c',name='Canonical',phone='0901000001',combo_purchases=[
    dict(id='new',combo_name='New',remaining=12,purchased_at='2026-09-26T10:00:00+07:00'),
    dict(id='old',combo_name='Old',remaining=20,purchased_at='2026-09-01T10:00:00+07:00'),
    dict(id='deleted',combo_name='Deleted',remaining=30,purchased_at='2026-09-27',deleted_at='2026-09-27')])]

def body(**patch):
    return schedule.ComboSaleSave(sale_date='2026-09-26',employee_username='seller',department='letan',
        customer_name='Untrusted name',customer_phone='wrong',combo_ticket='wrong',
        **dict(customer_id='c',combo_purchase_id='new',**patch))


def test_combo_sale_resolves_canonical_customer_and_latest_purchase_using_same_connection(monkeypatch):
    conn = object()
    def read(caller):
        assert caller is conn
        return CUSTOMERS
    monkeypatch.setattr(schedule, '_combo_customers', read)
    resolved = schedule._resolve_combo_customer(conn,body(),SimpleNamespace(role='letan'),lambda *args:True)
    assert (resolved.customer_name,resolved.customer_phone,resolved.combo_ticket) == ('Canonical','0901000001','New · còn 12 vé')
    for patch in ({'combo_purchase_id':'old'},{'customer_id':'missing'}):
        value=body().model_copy(update=patch)
        with pytest.raises(HTTPException) as exc:
            schedule._resolve_combo_customer(conn,value,SimpleNamespace(role='admin'),lambda *args:True)
        assert exc.value.status_code == 409
    legacy=body().model_copy(update={'customer_id':'','combo_purchase_id':''})
    assert schedule._resolve_combo_customer(conn,legacy,None,None) is legacy


def test_compact_catalog_reads_customers_from_both_storage_modes(database, monkeypatch):
    import json
    from sqlalchemy import text
    import vera_live_tour_resource_store as store
    with database.begin() as conn:
        old, _, _ = store.read(conn)
        from copy import deepcopy
        new = deepcopy(old); new['customers'] = CUSTOMERS
        store.write(conn, old, new, 'test')
    with database.connect() as conn:
        assert schedule._combo_customers(conn) == CUSTOMERS
    monkeypatch.setenv('VERA_LIVE_TOUR_RELATIONAL_MODE','off')
    with database.begin() as conn:
        conn.execute(text("UPDATE vera_app_setting SET value_json=jsonb_set(value_json,'{customers}',CAST(:data AS jsonb)) WHERE category='live_tour' AND setting_key='state'"), {'data':json.dumps(CUSTOMERS)})
        assert schedule._combo_customers(conn) == CUSTOMERS


from test_live_tour_resource_postgres import database  # noqa: E402,F401


def test_saved_attendance_codes_project_real_postgres_json_without_replaying_attendance(database):
    from sqlalchemy import text
    import json
    from vera_web_v2_attendance_codes import saved_codes
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE vera_dataset_cache(dataset_key text PRIMARY KEY,payload jsonb)'))
        rows = [{'EmployeeName':'Synthetic', 'EnrollNumber':'00123','EmployeeCode':'EMP001','Mobile':'0901000001'}]
        for key in ('timesoft_employee_checkin_today','timesoft_employee_checkin_2026-09-26','ignored'):
            conn.execute(text('INSERT INTO vera_dataset_cache VALUES(:key,CAST(:rows AS jsonb))'),{'key':key,'rows':json.dumps(rows+rows)})
        assert saved_codes(conn) == [dict(name='Synthetic',phone='0901000001',attendance_code='00123',employee_code='EMP001')]
