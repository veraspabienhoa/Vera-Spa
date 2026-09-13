from unittest.mock import Mock
import pytest
import vera_vps_payroll_schema as schema


def test_ddl_matches_canonical_schema_and_preserves_data():
    sql = '\n'.join(schema.statements())
    assert 'CREATE TABLE IF NOT EXISTS payroll_history_rows' in sql
    assert 'ENABLE ROW LEVEL SECURITY' in sql
    assert 'idx_payroll_history_batch' in sql
    assert 'idx_payroll_history_employee' in sql
    assert not any(word in sql.upper() for word in ('DROP ', 'DELETE ', 'TRUNCATE ', 'GRANT '))


@pytest.mark.parametrize('exists', [True, False])
def test_migration_is_idempotent_and_verified(monkeypatch, exists):
    inspector = Mock()
    inspector.has_table.return_value = exists
    monkeypatch.setattr(schema, 'inspect', lambda conn: inspector)
    verify = Mock()
    monkeypatch.setattr(schema, 'verify', verify)
    conn = Mock()
    schema.migrate(conn)
    verify.assert_called_once_with(conn)
    sql = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert any('lock_timeout' in s for s in sql)
    assert sum('CREATE TABLE' in s for s in sql) == (0 if exists else 1)


def test_schema_mismatch_stops_without_rewriting(monkeypatch):
    inspector = Mock()
    inspector.get_columns.return_value = [{'name': 'id', 'type': 'TEXT'}]
    monkeypatch.setattr(schema, 'inspect', lambda conn: inspector)
    conn = Mock()
    with pytest.raises(RuntimeError, match='schema mismatch'):
        schema.verify(conn)
    conn.execute.assert_not_called()
