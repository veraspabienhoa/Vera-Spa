import asyncio
from copy import deepcopy
from io import BytesIO
from threading import Event
from time import monotonic
from zipfile import ZipFile

try:
    import httpx2 as httpx
except ImportError:
    import httpx
from fastapi import FastAPI
from starlette.responses import Response
from PIL import Image

import vera_web_v2_excel_export_style as styling
import vera_live_tour_resource_store as store
from test_staff_export_and_quota_regressions import workbook_builder
import vera_web_v2_staff as staff


def test_camera_portraits_are_resampled_to_excel_display_size(workbook_builder):
    photo = BytesIO()
    Image.new('RGB', (1800, 2400), 'green').save(photo, format='WEBP')
    row = staff._public_employee({'username': 'Test', 'role': 'nhanvien'}, 'Đang làm việc')
    output = workbook_builder([row], {}, {'Test': photo.getvalue()})
    with ZipFile(BytesIO(output)) as archive:
        image = Image.open(BytesIO(archive.read('xl/media/image1.png')))
        assert image.size == (216, 288)


def test_excel_styling_does_not_block_other_requests(monkeypatch):
    started, release = Event(), Event()
    def slow_style(payload):
        started.set()
        release.wait(2)
        return payload
    monkeypatch.setattr(styling, 'style_workbook_bytes', slow_style)
    app = FastAPI()
    @app.get('/export.xlsx')
    async def export():
        return Response(b'PKtest', media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    @app.get('/ping')
    async def ping():
        return {'ok': True}
    styling.install_excel_export_style(app)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            start = monotonic()
            exporting = asyncio.create_task(client.get('/export.xlsx'))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                response = await client.get('/ping')
                assert response.status_code == 200
                assert monotonic() - start < 1
            finally:
                release.set()
                result = await exporting
            assert result.content == b'PKtest'
    asyncio.run(exercise())


def test_payment_discovers_same_locks_without_loading_audit_twice(monkeypatch):
    state = {'employees': [{'id': 'e', 'room': '1.1'}], 'rooms': [],
             'customers': [], 'pending': [], 'invoices': [],
             'audit': [{'detail': 'large history'}], 'idempotency': {'old': {'status': 'completed'}},
             'counter_business_date': '2026-09-25'}
    reads, locks = [], []
    def read(conn, collections=None):
        reads.append(collections)
        if collections is None:
            assert locks
            return deepcopy(state), 7, {}
        return {key: deepcopy(value) for key, value in state.items() if key in collections}, 7, {}
    monkeypatch.setattr(store, 'read', read)
    monkeypatch.setattr(store, 'lock', lambda *args, **kwargs: None)
    monkeypatch.setattr(store.concurrency, 'lock_resources', lambda conn, resources, wait: locks.append(resources))
    class Conn:
        info = {}
    result, revision, fresh = store.begin_action(Conn(), 'quick_checkout', {'employee_id': 'e'}, 7, 'new-payment-key', '2026-09-25')
    expected = store.action_resources(state, 'quick_checkout', {'employee_id': 'e'}, 'new-payment-key')
    assert locks == [expected]
    assert ('live_tour_ledger', 'invoices') in expected
    assert reads == [store.LOCK_DISCOVERY_COLLECTIONS, None]
    assert result['audit'] == state['audit'] and result['idempotency'] == state['idempotency']
    assert revision == 7 and fresh
