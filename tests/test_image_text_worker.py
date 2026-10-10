"""Copy-only OCR must not starve requests or outlive its capacity accounting."""
from __future__ import annotations

import ast
import asyncio
from io import BytesIO
from pathlib import Path
import subprocess
from threading import Event, Lock, get_ident
from time import monotonic
from types import SimpleNamespace

from fastapi import Depends, FastAPI, HTTPException, Request
from PIL import Image
import pytest

try:
    import httpx2 as httpx
except ImportError:
    import httpx

import vera_image_text_worker as workers
import vera_web_v2_staff_security as security


ROOT = Path(__file__).resolve().parents[1]


def sample_image(size=(200, 200), image_format="PNG"):
    output = BytesIO()
    Image.new("1", size).save(output, format=image_format)
    return output.getvalue()


def app_for(worker):
    """Register the actual production route without unrelated DB installers."""
    app = FastAPI()
    auth_calls = []

    async def current_identity(request: Request):
        token = request.headers.get("authorization")
        auth_calls.append(token)
        if token != "Bearer valid":
            raise HTTPException(403 if token else 401, "Denied")
        return "verified"

    source = ast.parse((ROOT / "vera_web_v2_api_v38.py").read_text())
    route = next(node for node in source.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name == "extract_profile_image_text")
    scope = dict(Request=Request, Depends=Depends,
                 _api=SimpleNamespace(Identity=str, current_identity=current_identity),
                 _shared=SimpleNamespace(app=app), _staff_security=security,
                 image_text_worker=worker)
    exec(compile(ast.Module(body=[route], type_ignores=[]), str(ROOT / "vera_web_v2_api_v38.py"), "exec"), scope)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app, auth_calls


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def post(client, content=None, *, content_type="image/png", token="Bearer valid"):
    headers = {"content-type": content_type}
    if token:
        headers["authorization"] = token
    return await client.post("/v2/staff/image-text", content=sample_image() if content is None else content,
                             headers=headers)


@pytest.fixture
def worker_factory():
    created = []

    def create(*, max_workers=1, timeout_seconds=1):
        worker = workers.ImageTextWorker(max_workers=max_workers, timeout_seconds=timeout_seconds)
        created.append(worker)
        return worker

    yield create
    for worker in created:
        worker._executor.shutdown(wait=True)


def test_pillow_and_ocr_leave_event_loop_responsive(worker_factory, monkeypatch):
    worker = worker_factory()
    started, release = Event(), Event()
    phases = []
    event_loop_thread = get_ident()

    def dimensions(_content):
        phases.append(("dimensions", get_ident()))
        started.set()
        assert release.wait(2)

    def ocr(_content, *, deadline):
        phases.append(("ocr", get_ident()))
        assert deadline > monotonic()
        return "  Selectable text  "

    monkeypatch.setattr(security, "_image_dimensions", dimensions)
    monkeypatch.setattr(security, "_ocr_text", ocr)
    app, _ = app_for(worker)

    async def exercise():
        async with client_for(app) as client:
            extraction = asyncio.create_task(post(client))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                ping = await asyncio.wait_for(client.get("/ping"), timeout=0.3)
                assert ping.status_code == 200
                assert not extraction.done()
            finally:
                release.set()
                response = await extraction
            assert response.status_code == 200
            assert response.json() == {
                "ok": True, "text": "Selectable text", "ocr_status": "extracted",
                "message": "Đã nhận dạng chữ trên ảnh.",
            }

    asyncio.run(exercise())
    assert [phase for phase, _ in phases] == ["dimensions", "ocr"]
    assert all(thread != event_loop_thread for _, thread in phases)


def test_worker_concurrency_is_bounded_and_excess_requests_do_not_queue(worker_factory, monkeypatch):
    worker = worker_factory(max_workers=2)
    started, release = Event(), Event()
    lock = Lock()
    active = maximum = calls = 0

    def ocr(_content, *, deadline):
        nonlocal active, maximum, calls
        with lock:
            calls += 1
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                started.set()
        try:
            assert release.wait(2)
            return "text"
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(security, "_ocr_text", ocr)
    app, _ = app_for(worker)

    async def exercise():
        async with client_for(app) as client:
            pending = [asyncio.create_task(post(client)) for _ in range(2)]
            try:
                assert await asyncio.to_thread(started.wait, 1)
                rejected = await asyncio.wait_for(asyncio.gather(*(post(client) for _ in range(8))), 0.3)
                assert all(response.status_code == 503 for response in rejected)
                assert all(response.headers["retry-after"] == "1" for response in rejected)
                assert calls == 2
            finally:
                release.set()
                responses = await asyncio.gather(*pending)
            assert all(response.status_code == 200 for response in responses)
            assert (await post(client)).status_code == 200

    asyncio.run(exercise())
    assert maximum == 2
    assert calls == 3


@pytest.mark.parametrize("abandon", ["timeout", "cancel"])
def test_abandoned_worker_keeps_its_slot_until_real_completion(worker_factory, monkeypatch, abandon):
    worker = worker_factory(timeout_seconds=0.08 if abandon == "timeout" else 1)
    started, release = Event(), Event()
    calls = []

    def dimensions(_content):
        started.set()
        assert release.wait(2)

    def ocr(_content, *, deadline):
        calls.append("ocr")
        return "text"

    monkeypatch.setattr(security, "_image_dimensions", dimensions)
    monkeypatch.setattr(security, "_ocr_text", ocr)
    app, _ = app_for(worker)

    async def exercise():
        async with client_for(app) as client:
            task = asyncio.create_task(post(client))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                if abandon == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    response = await asyncio.wait_for(task, 0.5)
                    assert response.status_code == 504
                for _ in range(3):
                    assert (await post(client)).status_code == 503
                assert not calls
                assert (await client.get("/ping")).status_code == 200
            finally:
                release.set()
                if not task.done():
                    await task
            end = monotonic() + 1
            while True:
                recovered = await post(client)
                if recovered.status_code != 503:
                    break
                assert monotonic() < end
                await asyncio.sleep(0.005)
            assert recovered.status_code == 200

    asyncio.run(exercise())
    # The expired worker must not begin OCR after slow Pillow work finishes.
    assert len(calls) == (1 if abandon == "timeout" else 2)


@pytest.mark.parametrize("token,status", [(None, 401), ("Bearer revoked", 403), ("Bearer locked", 403)])
def test_authentication_still_precedes_image_processing(worker_factory, monkeypatch, token, status):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Unverified request reached image processing")

    monkeypatch.setattr(security, "_valid_image", forbidden)
    app, auth_calls = app_for(worker_factory())

    async def exercise():
        async with client_for(app) as client:
            assert (await post(client, token=token)).status_code == status

    asyncio.run(exercise())
    assert auth_calls == [token]


@pytest.mark.parametrize("content,content_type", [
    (b"", "image/png"),
    (b"<svg>active content</svg>", "image/svg+xml"),
    (b"not a PNG", "image/png"),
    (sample_image(image_format="JPEG"), "image/png"),
    (b"\x89PNG\r\n\x1a\ninvalid", "image/png"),
    (sample_image((100, 200)), "image/png"),
    (sample_image((6001, 160)), "image/png"),
    (sample_image((5000, 5000)), "image/png"),
    (b"x" * (security.MAX_IDENTITY_BYTES + 1), "image/png"),
])
def test_existing_image_security_guards_and_failure_recovery(worker_factory, monkeypatch, content, content_type):
    calls = []
    monkeypatch.setattr(security, "_ocr_text", lambda _content, **_kwargs: calls.append("ocr") or "")
    app, _ = app_for(worker_factory())

    async def exercise():
        async with client_for(app) as client:
            rejected = await post(client, content, content_type=content_type)
            assert rejected.status_code == 400
            assert not calls
            response = await post(client)
            assert response.status_code == 200
            assert response.json()["ocr_status"] == "not_detected"
            assert response.json()["text"] == ""

    asyncio.run(exercise())


def test_chunked_upload_stops_at_byte_limit(worker_factory, monkeypatch):
    read_chunks = []
    monkeypatch.setattr(security, "_ocr_text", lambda *_args, **_kwargs: pytest.fail("Oversize upload reached OCR"))
    app, _ = app_for(worker_factory())

    async def chunks():
        for chunk in [b"x" * security.MAX_IDENTITY_BYTES, b"extra", b"must not read"]:
            read_chunks.append(len(chunk))
            yield chunk

    async def exercise():
        async with client_for(app) as client:
            assert (await post(client, chunks())).status_code == 400

    asyncio.run(exercise())
    assert read_chunks == [security.MAX_IDENTITY_BYTES, 5]


def test_total_deadline_includes_slow_upload_and_releases_unsubmitted_slot(worker_factory, monkeypatch):
    worker = worker_factory(timeout_seconds=0.04)
    monkeypatch.setattr(security, "_ocr_text", lambda *_args, **_kwargs: "text")
    app, _ = app_for(worker)

    async def slow_upload():
        yield b"\x89PNG\r\n\x1a\n"
        await asyncio.sleep(0.2)
        yield b"late"

    async def exercise():
        async with client_for(app) as client:
            response = await asyncio.wait_for(post(client, slow_upload()), 0.3)
            assert response.status_code == 504
            assert (await post(client)).status_code == 200

    asyncio.run(exercise())


def test_upload_and_processing_share_one_deadline(worker_factory, monkeypatch):
    worker = worker_factory(timeout_seconds=0.12)
    remaining_at_ocr = []
    app, _ = app_for(worker)

    def ocr(_content, *, deadline):
        remaining_at_ocr.append(deadline - monotonic())
        return "text"

    monkeypatch.setattr(security, "_ocr_text", ocr)

    async def delayed_upload():
        await asyncio.sleep(0.07)
        yield sample_image()

    async def exercise():
        async with client_for(app) as client:
            assert (await post(client, delayed_upload())).status_code == 200

    asyncio.run(exercise())
    assert len(remaining_at_ocr) == 1
    assert 0 < remaining_at_ocr[0] < 0.065


def test_upload_cancellation_releases_slot_without_starting_worker(worker_factory, monkeypatch):
    worker = worker_factory()
    started = asyncio.Event()
    calls = []
    monkeypatch.setattr(security, "_ocr_text", lambda *_args, **_kwargs: calls.append("ocr") or "text")
    app, _ = app_for(worker)

    async def stalled_upload():
        started.set()
        await asyncio.sleep(2)
        yield sample_image()

    async def exercise():
        async with client_for(app) as client:
            task = asyncio.create_task(post(client, stalled_upload()))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert calls == []
            assert (await post(client)).status_code == 200

    asyncio.run(exercise())
    assert calls == ["ocr"]


def test_late_worker_exception_is_consumed_without_sensitive_logging(worker_factory, monkeypatch, caplog):
    worker = worker_factory()
    started, release, finished = Event(), Event(), Event()
    private_detail = "synthetic private image contents"

    def fail(_content):
        started.set()
        try:
            assert release.wait(2)
            raise ValueError(private_detail)
        finally:
            finished.set()

    monkeypatch.setattr(security, "_image_dimensions", fail)
    app, _ = app_for(worker)

    async def exercise():
        loop = asyncio.get_running_loop()
        errors = []
        loop.set_exception_handler(lambda _loop, context: errors.append(context))
        async with client_for(app) as client:
            task = asyncio.create_task(post(client))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
            assert await asyncio.to_thread(finished.wait, 1)
            await asyncio.sleep(0.01)
            assert errors == []

    asyncio.run(exercise())
    assert private_detail not in caplog.text


def test_submission_failure_releases_capacity(worker_factory, monkeypatch):
    worker = worker_factory()
    original = worker._executor.submit
    monkeypatch.setattr(security, "_ocr_text", lambda *_args, **_kwargs: "text")
    app, _ = app_for(worker)

    def fail(*_args, **_kwargs):
        raise RuntimeError("executor unavailable")

    async def exercise():
        async with client_for(app) as client:
            monkeypatch.setattr(worker._executor, "submit", fail)
            with pytest.raises(RuntimeError, match="executor unavailable"):
                await post(client)
            monkeypatch.setattr(worker._executor, "submit", original)
            assert (await post(client)).status_code == 200

    asyncio.run(exercise())


def test_subprocess_attempts_share_remaining_total_budget(monkeypatch):
    now = [100.0]
    timeouts = []
    monkeypatch.setattr(security, "monotonic", lambda: now[0])
    monkeypatch.setattr(security.shutil, "which", lambda _: "/test/tesseract")

    def run(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        assert command[1:3] == ["stdin", "stdout"]
        assert kwargs["stderr"] == subprocess.PIPE
        now[0] += kwargs["timeout"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(security.subprocess, "run", run)
    with pytest.raises(TimeoutError):
        security._ocr_text(sample_image(), deadline=125.0)
    assert timeouts == [20, 5]


def test_preprocessing_deadline_is_not_swallowed_as_image_fallback(monkeypatch):
    now = [100.0]
    original = security.ImageOps.exif_transpose
    monkeypatch.setattr(security, "monotonic", lambda: now[0])
    monkeypatch.setattr(security.shutil, "which", lambda _: "/test/tesseract")

    def transpose(image):
        now[0] = 126.0
        return original(image)

    monkeypatch.setattr(security.ImageOps, "exif_transpose", transpose)
    monkeypatch.setattr(security.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Expired worker started OCR"))
    with pytest.raises(TimeoutError):
        security._ocr_text(sample_image(), deadline=125.0)


def test_legacy_ocr_callers_keep_language_fallback_and_attempt_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(security.shutil, "which", lambda _: "/test/tesseract")

    def run(command, **kwargs):
        calls.append((command[4], kwargs["timeout"]))
        return SimpleNamespace(returncode=0 if command[4] == "eng" else 1, stdout=b"  text  ")

    monkeypatch.setattr(security.subprocess, "run", run)
    assert security._ocr_text(sample_image()) == "text"
    assert calls == [("vie+eng", 20), ("vie+eng", 20), ("eng", 20), ("eng", 20)]


@pytest.mark.parametrize("value,expected", [("bad", 1), ("0", 1), ("-4", 1), ("100", 4), ("2", 2)])
def test_worker_configuration_is_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("VERA_IMAGE_TEXT_WORKERS", value)
    assert workers._bounded_setting("VERA_IMAGE_TEXT_WORKERS", 1, 4) == expected
