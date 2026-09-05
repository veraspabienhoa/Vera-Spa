"""Admin API for changing the shared TourVera Google Drive source."""
from __future__ import annotations

from io import BytesIO
from typing import Any, Callable
from zipfile import BadZipFile, ZipFile

from fastapi import Depends, HTTPException
from google.auth.transport.requests import AuthorizedSession
from pydantic import BaseModel

from vera_google_credentials import google_credentials
from vera_tour_source import (
    TOUR_MIME,
    extract_tour_file_id,
    get_tour_source,
    save_tour_source,
)


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


class TourSourceUpdate(BaseModel):
    url: str


def _require_admin(ident: Any) -> None:
    if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
        raise HTTPException(403, "Chỉ Admin được thay đổi link TourVera.")


def _validate_tour_workbook(payload: bytes) -> None:
    try:
        with ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
            if "xl/vbaProject.bin" not in names:
                raise HTTPException(400, "File phải là TourVera.xlsm có macro VBA.")
            workbook_xml = archive.read("xl/workbook.xml")
    except HTTPException:
        raise
    except (BadZipFile, KeyError) as exc:
        raise HTTPException(400, "File Google Drive không phải workbook TourVera hợp lệ.") from exc
    for required_sheet in (b' name="Input"', b' name="Room"', b' name="Nghi"'):
        if required_sheet not in workbook_xml:
            raise HTTPException(400, "TourVera phải có đủ các sheet Input, Room và Nghi.")


def _inspect_drive_file(file_id: str) -> dict[str, Any]:
    try:
        session = AuthorizedSession(google_credentials([DRIVE_SCOPE]))
        metadata_response = session.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}"
            "?supportsAllDrives=true&fields=id,name,mimeType,modifiedTime,size",
            timeout=45,
        )
    except Exception as exc:
        raise HTTPException(503, f"Không kết nối được Google Drive: {exc}") from exc
    if metadata_response.status_code != 200:
        raise HTTPException(
            400,
            f"Không đọc được file từ link này (Google Drive HTTP {metadata_response.status_code}). "
            "Hãy chia sẻ file cho tài khoản dịch vụ của hệ thống.",
        )
    metadata = dict(metadata_response.json() or {})
    if str(metadata.get("mimeType") or "") != TOUR_MIME:
        raise HTTPException(400, "Link phải trỏ trực tiếp tới file TourVera định dạng .xlsm.")
    try:
        download_response = session.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true",
            timeout=90,
        )
    except Exception as exc:
        raise HTTPException(503, f"Không tải được TourVera từ Google Drive: {exc}") from exc
    if download_response.status_code != 200:
        raise HTTPException(400, "Không tải được nội dung TourVera để kiểm tra.")
    payload = bytes(download_response.content or b"")
    if not payload:
        raise HTTPException(400, "File TourVera đang rỗng.")
    _validate_tour_workbook(payload)
    return {
        "file_id": file_id,
        "name": str(metadata.get("name") or "TourVera.xlsm"),
        "mime_type": str(metadata.get("mimeType") or TOUR_MIME),
        "modified_time": str(metadata.get("modifiedTime") or ""),
        "size": int(metadata.get("size") or len(payload)),
    }


def install_tour_source_routes(
    app,
    *,
    current_identity,
    identity_type,
    invalidate_tour_cache: Callable[[], None] | None = None,
) -> None:
    @app.get("/v2/tour/source")
    def read_source(ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        return get_tour_source()

    @app.put("/v2/tour/source")
    def update_source(body: TourSourceUpdate, ident: identity_type = Depends(current_identity)):
        _require_admin(ident)
        try:
            file_id = extract_tour_file_id(body.url)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        metadata = _inspect_drive_file(file_id)
        try:
            saved = save_tour_source(
                metadata,
                updated_by=str(getattr(ident, "employee_username", "") or "admin"),
            )
        except Exception as exc:
            raise HTTPException(503, f"Không lưu được cấu hình TourVera vào PostgreSQL: {exc}") from exc
        if invalidate_tour_cache:
            invalidate_tour_cache()
        return saved
