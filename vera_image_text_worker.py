"""Bounded, copy-only image OCR, isolated from the ASGI/shared worker pools.

Admission includes upload time and has no waiting queue. A timed-out/cancelled
request cannot cancel a running Python thread, so only the concurrent future's
completion releases its slot. Images/text are never persisted or logged here.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import threading
from time import monotonic

from fastapi import HTTPException, Request


def _bounded_setting(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Image text deadline exceeded")
    return remaining


async def _read_image(request: Request, maximum_bytes: int) -> bytes:
    # Request.body() would buffer an arbitrarily large chunked upload before
    # applying the size guard. Retain no more than the existing image limit.
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum_bytes:
            raise HTTPException(400, "Ảnh trống hoặc vượt quá dung lượng cho phép.")
        content.extend(chunk)
    if not content:
        raise HTTPException(400, "Ảnh trống hoặc vượt quá dung lượng cho phép.")
    return bytes(content)


def _consume_exception(future: asyncio.Future) -> None:
    # A disconnected caller no longer consumes a late validation/OCR failure.
    # Retrieve it without logging potentially sensitive image/text details.
    if not future.cancelled():
        future.exception()


class ImageTextWorker:
    def __init__(self, *, max_workers: int, timeout_seconds: float):
        if max_workers < 1 or timeout_seconds <= 0:
            raise ValueError("Image text worker limits must be positive")
        self.timeout_seconds = timeout_seconds
        self._slots = threading.BoundedSemaphore(max_workers)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="vera-image-text",
        )

    @staticmethod
    def _extract(content: bytes, content_type: str, security, deadline: float) -> str:
        _remaining(deadline)
        if not security._valid_image(content, content_type):
            raise HTTPException(400, "Nội dung file ảnh không hợp lệ.")
        # Pillow verification, decoding, resizing and every tesseract attempt
        # all run in this dedicated worker, never on the event loop.
        security._image_dimensions(content)
        _remaining(deadline)
        raw_text = security._ocr_text(content, deadline=deadline).strip()
        _remaining(deadline)
        return raw_text

    async def extract(self, request: Request, *, security) -> dict:
        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in security.ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Chỉ chấp nhận ảnh WebP, JPEG hoặc PNG.")
        if not self._slots.acquire(blocking=False):
            raise HTTPException(
                503, "Nhận dạng ảnh đang bận. Vui lòng thử lại sau.",
                headers={"Retry-After": "1"},
            )
        deadline = monotonic() + self.timeout_seconds
        submitted = False
        try:
            remaining = _remaining(deadline)
            content = await asyncio.wait_for(
                _read_image(request, security.MAX_IDENTITY_BYTES),
                timeout=remaining,
            )
            _remaining(deadline)
            future = self._executor.submit(self._extract, content, content_type, security, deadline)
            submitted = True
            # Release on real completion, including a worker-side exception.
            # Shielding the wrapped future alone is not a capacity limiter.
            future.add_done_callback(lambda _future: self._slots.release())
            result = asyncio.wrap_future(future)
            result.add_done_callback(_consume_exception)
            remaining = _remaining(deadline)
            raw_text = await asyncio.wait_for(asyncio.shield(result), timeout=remaining)
        except TimeoutError:
            raise HTTPException(504, "Nhận dạng ảnh quá thời gian cho phép. Vui lòng thử lại.") from None
        finally:
            if not submitted:
                self._slots.release()
        return {
            "ok": True,
            "text": raw_text,
            "ocr_status": "extracted" if raw_text else "not_detected",
            "message": "Đã nhận dạng chữ trên ảnh." if raw_text else "Không nhận dạng được chữ trên ảnh.",
        }


# Limits are per API process. Keep this separate from the auth/business pools
# and Starlette's shared thread capacity. Environment changes need a restart.
image_text_worker = ImageTextWorker(
    max_workers=_bounded_setting("VERA_IMAGE_TEXT_WORKERS", 1, 4),
    timeout_seconds=_bounded_setting("VERA_IMAGE_TEXT_TIMEOUT_SECONDS", 30, 60),
)
