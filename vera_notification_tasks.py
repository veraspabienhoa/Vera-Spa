"""Searchable catalog of installed API mutations; successful operations emit safe summaries."""
import asyncio
import hashlib
import json
import uuid
from fastapi.routing import APIRoute
from vera_notification_delivery import route_event

EXCLUDED = ('/v2/auth', '/v2/notification', '/v2/push', '/v2/me', '/v2/ui-layout')
GROUPS = {'live-tour':'Live Tour','leave':'Đăng ký nghỉ','long-leave':'Phép năm','training':'Đào tạo & đánh giá',
          'payroll':'Bảng lương','staff':'Nhân viên','employees':'Nhân viên','revenue':'Doanh thu',
          'work-schedule':'Lịch làm việc','profile':'Hồ sơ','settings':'Cài đặt','products':'Sản phẩm'}
ACTIONS = {'start':'Thực hiện dịch vụ','start_room':'Thực hiện cả phòng','finish_to_pending':'Hoàn thành dịch vụ',
           'finish_room':'Hoàn thành cả phòng','booking':'Đặt booking','multi_booking':'Đặt nhiều booking',
           'checkout':'Thanh toán','quick_checkout':'Thanh toán nhanh','cancel_booking':'Hủy booking',
           'set_work_status':'Đổi trạng thái đi làm','start_break':'Bắt đầu nghỉ giữa ca','end_break':'Kết thúc nghỉ giữa ca'}


def task_key(method, path, action=''):
    return 'task-' + hashlib.sha256(f'{method}:{path}:{action}'.encode()).hexdigest()[:24]


def task_catalog(app):
    output = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/v2/') or route.path.startswith(EXCLUDED):
            continue
        for method in sorted((route.methods or set()) & {'POST','PUT','PATCH','DELETE'}):
            group = GROUPS.get(route.path.split('/')[2], 'Hệ thống')
            verbs = {'POST':'Thực hiện', 'PUT':'Cập nhật', 'PATCH':'Chỉnh sửa', 'DELETE':'Xóa'}
            actions = ['']
            if route.path == '/v2/live-tour/action':
                from vera_web_v2_live_tour import IDEMPOTENCY_REQUIRED_ACTIONS
                actions = sorted(IDEMPOTENCY_REQUIRED_ACTIONS)
            for action in actions:
                key = task_key(method, route.path, action)
                label = ACTIONS.get(action) or (action.replace('_',' ') if action else route.summary or route.name.replace('_',' '))
                output[key] = {'key': key, 'label': f'{group} · {verbs[method]} · {label}', 'group': group,
                               'description': f'{method} {route.path}' + (f' · {action}' if action else '')}
    return list(output.values())


class TaskNotificationMiddleware:
    def __init__(self, app, *, owner, engine_instance):
        self.app, self.owner, self.engine_instance = app, owner, engine_instance

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST','PUT','PATCH','DELETE'} or scope.get('path','').startswith(EXCLUDED):
            return await self.app(scope, receive, send)
        status = 500
        chunks = bytearray()
        response_chunks = bytearray()
        async def capture_receive():
            message = await receive()
            if message['type'] == 'http.request' and len(chunks) < 65536:
                chunks.extend(message.get('body', b'')[:65536-len(chunks)])
            return message
        async def capture_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            if message['type'] == 'http.response.body' and len(response_chunks) < 65536:
                response_chunks.extend(message.get('body', b'')[:65536-len(response_chunks)])
            await send(message)
        await self.app(scope, capture_receive, capture_send)
        if not 200 <= status < 300:
            return
        try:
            result = json.loads(response_chunks)
            if isinstance(result, dict) and (result.get('ok') is False or result.get('success') is False or result.get('duplicate') is True): return
        except (ValueError, UnicodeDecodeError): pass
        route = scope.get('route')
        if not isinstance(route, APIRoute):
            return
        action = ''
        if route.path == '/v2/live-tour/action':
            try: action = json.loads(chunks).get('action','')
            except (ValueError, AttributeError): return
        key = task_key(scope['method'], route.path, action)
        task = next((item for item in task_catalog(self.owner) if item['key'] == key), None)
        if task:
            # No request/response contents, account credentials or customer data in generic alerts.
            payload = {'title': task['label'], 'body': 'Tác vụ đã hoàn tất thành công trong hệ thống Vera Spa.', 'tag': str(uuid.uuid4())}
            try: await asyncio.to_thread(route_event, self.engine_instance(), key, payload)
            except Exception: pass  # Completed business writes are never converted to errors.
