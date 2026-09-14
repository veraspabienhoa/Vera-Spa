from datetime import date
from types import SimpleNamespace

import pytest
import vera_web_v2_api as api


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params):
        sql = str(statement)
        assert 'WHERE leave_date=:d' in sql
        assert 'AND source_sheet_id' not in sql
        assert 'FOR UPDATE' in sql
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))


@pytest.mark.parametrize('weekend,enabled', [(False, False), (True, True), (True, False)])
def test_rebalance_includes_server_rows_preserves_identity_and_mirrors_only_main(monkeypatch, weekend, enabled):
    day = date(2026, 9, 13 if weekend else 14)
    rows = [dict(record_uid=f'uid-{i}', source_sheet_id=sid, source_row=srow,
                 leave_date=day, leave_reason='Nghỉ không phép', detail='Ghi chú', penalty=0)
            for i, (sid, srow) in enumerate([(api.LEAVE_SHEET_ID, 2), ('server', 3), ('', None)])]
    conn = Connection(rows)
    updates = []
    monkeypatch.setattr(api, 'load_weekend_unpaid_enabled', lambda c: enabled)
    monkeypatch.setattr(api, '_reason_item', lambda c, reason: {'name': reason, 'penalty': 50000})
    monkeypatch.setattr(api, '_update_record', lambda c, row, number, sid: updates.append((row, number, sid)))
    mirrors = api._rebalance_progressive_rows(conn, day, {api._progressive_key('Nghỉ không phép')})
    assert len(updates) == 3
    assert len(mirrors) == 1 and mirrors[0][0] == 2
    assert [u[2] for u in updates] == [api.LEAVE_SHEET_ID, 'server', '']
    assert updates[-1][1] == 0
    active = not weekend or enabled
    assert updates[-1][0]['penalty'] == (150000 if active else 50000)
    assert updates[-1][0]['detail'] == ('Người Thứ 3 nghỉ không phép | Ghi chú' if active else 'Ghi chú')


def test_edit_rebalances_old_and_new_groups_in_same_transaction():
    import inspect
    source = inspect.getsource(api.update_leave)
    assert '_rebalance_progressive_rows(conn, old["leave_date"], {old_key, new_key})' in source
    assert source.index('_rebalance_progressive_rows(') < source.index('tx.commit()')


def test_reason_conversion_renumbers_both_groups_and_is_idempotent(monkeypatch):
    day = date(2026, 9, 14)
    rows = [dict(record_uid=f'u{i}', source_sheet_id='server', source_row=None,
                 leave_date=day, leave_reason=reason, detail=detail, penalty=150000)
            for i, (reason, detail) in enumerate([
                ('Nghỉ không phép', 'Người Thứ 2 nghỉ không phép | Ghi chú A'),
                ('Nghỉ không phép', 'Người Thứ 3 nghỉ không phép | Ghi chú B'),
                ('Về sớm không phép', 'Người Thứ 1 về sớm không phép'),
                ('Về sớm không phép', 'Người Thứ 2 về sớm không phép'),
                ('Về sớm không phép', 'Ghi chú của bản ghi vừa đổi'),
            ])]
    conn = Connection(rows)
    updates = []
    monkeypatch.setattr(api, 'load_weekend_unpaid_enabled', lambda c: False)
    monkeypatch.setattr(api, '_reason_item', lambda c, reason: {'name': reason, 'penalty': 50000})
    def update(c, record, number, sid):
        updates.append(record['record_uid'])
        next(r for r in rows if r['record_uid'] == record['record_uid']).update(record)
    monkeypatch.setattr(api, '_update_record', update)
    keys = {api._progressive_key('Nghỉ không phép'), api._progressive_key('Về sớm không phép')}
    assert api._rebalance_progressive_rows(conn, day, keys) == []  # No MainData mirrors.
    assert [api._existing_progressive_ordinal(r['detail']) for r in rows] == [1, 2, 1, 2, 3]
    assert [r['penalty'] for r in rows] == [50000, 50000, 50000, 50000, 150000]
    assert rows[0]['detail'].endswith('Ghi chú A')
    updates.clear()
    api._rebalance_progressive_rows(conn, day, keys)
    assert updates == []
