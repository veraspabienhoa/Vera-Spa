from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from openpyxl import load_workbook
import vera_web_v2_work_schedule as schedule


def setup(allowed):
    app = FastAPI()
    checks = []
    conn = object()

    class Engine:
        @contextmanager
        def begin(self):
            yield conn

    def permission(connection, ident, feature):
        assert connection is conn
        checks.append(feature)
        return allowed

    schedule.install_work_schedule_routes(app, engine_instance=Engine, current_identity=lambda: None, feature_allowed=permission)
    route = next(r.endpoint for r in app.routes if r.path == '/v2/work-schedule/table/export.xlsx')
    return route, checks


@pytest.mark.parametrize('department', list(schedule.WORK_SCHEDULE_FEATURES))
@pytest.mark.parametrize('kind', ['statistics', 'violations'])
def test_visible_snapshot_export_checks_department_and_produces_real_xlsx(department, kind):
    route, checks = setup(True)
    cells = ['=HYPERLINK("invalid")', '—', 1, 50000, 'Ghi chú', '', '07-10-2026 19:00:00']
    if kind == 'statistics':
        cells = ['Nhân viên', 2, 1, 1, 1, 1.5, '—', '—']
    body = schedule.ScheduleTableExport(department=department, kind=kind, start=date(2026, 10, 1), end=date(2026, 10, 7), rows=[cells])
    response = route(body, SimpleNamespace(role='letan'))
    assert response.media_type.endswith('spreadsheetml.sheet')
    assert checks == [schedule.WORK_SCHEDULE_FEATURES[department]]
    sheet = load_workbook(schedule._schedule_table_workbook(body)).active
    assert sheet['A2'].value == '01-10-2026 – 07-10-2026'
    assert tuple(c.value for c in sheet[3]) == schedule.SCHEDULE_TABLE_HEADERS[kind]
    assert list(c.value for c in sheet[4]) == [None if v == '' else v for v in cells]
    assert sheet['A4'].data_type == 's'
    assert sheet['D4'].data_type == 'n'
    assert sheet.freeze_panes == 'A4'


def test_denied_department_cannot_export_and_invalid_range_is_rejected_first():
    route, checks = setup(False)
    body = schedule.ScheduleTableExport(department='locker', kind='statistics', start=date(2026, 10, 1), end=date(2026, 10, 7))
    with pytest.raises(HTTPException) as exc:
        route(body, SimpleNamespace(role='locker'))
    assert exc.value.status_code == 403
    assert checks == ['work_schedule_locker']
    with pytest.raises(HTTPException) as exc:
        route(body.model_copy(update={'end': date(2026, 9, 1)}), None)
    assert exc.value.status_code == 400
    assert len(checks) == 1


def test_workbook_rejects_malformed_rows():
    body = schedule.ScheduleTableExport(department='letan', kind='violations', start=date(2026, 10, 1), end=date(2026, 10, 7), rows=[['wrong shape']])
    with pytest.raises(HTTPException) as exc:
        schedule._schedule_table_workbook(body)
    assert exc.value.status_code == 400
