"""Secure staff password reset and compressed identity-document storage for Web V2.

Passwords are never returned to the browser. Admin may replace a VERA password
in PostgreSQL without forcing the employee to change it at the next Web V2 login.

Citizen-ID images are stored in PostgreSQL only after the browser compresses
them to a small raster image. Access is restricted to the employee themself or
an Admin. SVG and other active formats are intentionally rejected.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata
from typing import Any, Callable
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from PIL import Image as PILImage, ImageFilter, ImageOps
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from vera_web_v2_local_auth import revoke_local_sessions
from vera_web_v2_security import password_policy_error


STAFF_SECURITY_RELEASE = "4.5-batch-profiles-mobile-crop"
MAX_IDENTITY_BYTES = 700 * 1024
IDENTITY_SIDES = {"front": "Mặt trước", "back": "Mặt sau"}
MEDIA_SIDES = {**IDENTITY_SIDES, "portrait": "Ảnh nhân viên"}
ALLOWED_IMAGE_TYPES = {"image/webp", "image/jpeg", "image/png"}
BUSINESS_NAME = "HỘ KINH DOANH VERA"
BUSINESS_ADDRESS = "193 Trương Định, Phường Tam Hiệp, Thành Phố Đồng Nai"


class StaffPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


class StaffBatchPdfRequest(BaseModel):
    usernames: list[str] = Field(min_length=1, max_length=100)


def _ensure_identity_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_employee_identity_document (
            employee_username text NOT NULL,
            side text NOT NULL CHECK (side IN ('front','back','portrait')),
            content_type text NOT NULL,
            content bytea NOT NULL,
            size_bytes integer NOT NULL,
            sha256 text NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT NOW(),
            updated_by text NOT NULL DEFAULT '',
            PRIMARY KEY (employee_username, side)
        )
    """))
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid='vera_employee_identity_document'::regclass
                  AND conname='vera_employee_identity_document_side_check'
                  AND pg_get_constraintdef(oid) NOT ILIKE '%portrait%'
            ) THEN
                ALTER TABLE vera_employee_identity_document
                    DROP CONSTRAINT vera_employee_identity_document_side_check;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid='vera_employee_identity_document'::regclass
                  AND conname='vera_employee_identity_document_side_check'
            ) THEN
                ALTER TABLE vera_employee_identity_document
                    ADD CONSTRAINT vera_employee_identity_document_side_check
                    CHECK (side IN ('front','back','portrait'));
            END IF;
        END $$;
    """))
    conn.execute(text("""
        ALTER TABLE vera_employee_identity_document
        ADD COLUMN IF NOT EXISTS ocr_payload jsonb NOT NULL DEFAULT '{}'::jsonb
    """))


def _valid_image(data: bytes, content_type: str) -> bool:
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/jpeg":
        return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"
    if content_type == "image/png":
        return len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n"
    return False


def _image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        with PILImage.open(BytesIO(data)) as image:
            image.verify()
        with PILImage.open(BytesIO(data)) as image:
            width, height = int(image.width), int(image.height)
            if width < 160 or height < 160:
                raise HTTPException(400, "Ảnh quá nhỏ; cần tối thiểu 160 × 160 px.")
            if width > 6000 or height > 6000 or width * height > 24_000_000:
                raise HTTPException(400, "Ảnh có độ phân giải quá lớn; vui lòng nén ảnh trước khi tải lên.")
            return width, height
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Không đọc được dữ liệu ảnh.") from exc


def _ocr_text(data: bytes) -> str:
    command = shutil.which("tesseract")
    if not command:
        return ""
    try:
        with PILImage.open(BytesIO(data)) as source:
            normalized = ImageOps.exif_transpose(source).convert("RGB")
        if max(normalized.size) < 1800:
            scale = 1800 / max(normalized.size)
            normalized = normalized.resize(
                (max(1, round(normalized.width * scale)), max(1, round(normalized.height * scale))),
                PILImage.Resampling.LANCZOS,
            )
        grayscale = ImageOps.autocontrast(ImageOps.grayscale(normalized)).filter(ImageFilter.SHARPEN)
        variants = []
        for image in (normalized, grayscale):
            output = BytesIO()
            image.save(output, format="PNG", optimize=True)
            variants.append(output.getvalue())
    except Exception:
        variants = [data]

    for language in ("vie+eng", "eng"):
        texts = []
        for payload, page_mode in zip(variants, ("6", "11")):
            try:
                result = subprocess.run(
                    [command, "stdin", "stdout", "-l", language, "--psm", page_mode],
                    input=payload,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0:
                value = result.stdout.decode("utf-8", errors="ignore").strip()
                if value and value not in texts:
                    texts.append(value)
        if texts:
            return "\n".join(texts)[:24000]
    return ""


def _extract_cccd_fields(data: bytes) -> dict[str, str]:
    raw = _ocr_text(data)
    if not raw:
        return {}
    clean = "\n".join(" ".join(line.split()) for line in raw.splitlines() if line.strip())
    full_name = ""
    name_match = re.search(
        r"(?:h[oọ]\s+v[aà]\s+t[eê]n|full\s*name)"
        r"(?:\s*/\s*(?:full\s*name|h[oọ]\s+v[aà]\s+t[eê]n))?"
        r"\s*[:\-]?\s*([^\n]{3,120})",
        clean,
        flags=re.IGNORECASE,
    )
    if name_match:
        candidate = re.sub(r"\s+", " ", name_match.group(1)).strip(" .,:;-")
        if not re.search(r"(?:ng[aà]y\s*sinh|date\s*of\s*birth|gi[oớ]i\s*t[ií]nh|sex)", candidate, flags=re.IGNORECASE):
            full_name = candidate[:300]
    compact_digits = re.sub(r"(?<=\d)[\s.\-]+(?=\d)", "", clean)
    number_match = re.search(r"(?<!\d)(\d{12})(?!\d)", compact_digits)
    if not number_match:
        number_match = re.search(r"(?<!\d)(\d{9})(?!\d)", compact_digits)

    issue_date = ""
    date_patterns = (
        r"(?:ngày\s*cấp|date\s*of\s*issue)[^\d]{0,32}(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        r"(?:ngày,?\s*tháng,?\s*năm|date,?\s*month,?\s*year)[^\d]{0,32}(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        r"(?:ngày\s*cấp|date\s*of\s*issue|ngày,?\s*tháng,?\s*năm)[^\d]{0,32}(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})",
    )
    for pattern in date_patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            try:
                candidate = (
                    "/".join(match.groups()[:3]) if len(match.groups()) >= 3 and match.group(2)
                    else match.group(1).replace("-", "/").replace(".", "/")
                )
                issue_date = datetime.strptime(candidate, "%d/%m/%Y").strftime("%d/%m/%Y")
            except ValueError:
                issue_date = ""
            if issue_date:
                break

    place = ""
    place_match = re.search(
        r"(?:nơi\s*cấp\s*/\s*place\s*of\s*issue|nơi\s*cấp|place\s*of\s*issue)\s*[:\-]?\s*([^\n]{3,300})",
        clean,
        flags=re.IGNORECASE,
    )
    if place_match:
        place = place_match.group(1).strip(" .,:;-")[:500]
    elif re.search(
        r"c[uụ]c\s+(?:trưởng\s+c[uụ]c\s+)?c[aả]nh\s+s[aá]t.*qu[aả]n\s+l[yý]\s+h[aà]nh\s+ch[ií]nh.*tr[aậ]t\s+t[uự]\s+x[aã]\s+h[oộ]i",
        clean,
        flags=re.IGNORECASE,
    ):
        # Mặt sau CCCD gắn chip thường chỉ in tên cơ quan ký, không có
        # nhãn “Nơi cấp / Place of issue”. Chuẩn hóa về tên cơ quan cấp.
        place = "Cục Cảnh sát quản lý hành chính về trật tự xã hội"

    def labeled_value(label: str, stops: str) -> str:
        match = re.search(
            rf"(?:{label})\s*[:\-]?\s*(.+?)(?=\n\s*(?:{stops})\b|$)",
            clean,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        value = re.sub(r"\s+", " ", match.group(1)).strip(" .,:;-")
        return value[:1000]

    place_of_origin = labeled_value(
        r"qu[eê]\s*qu[aá]n(?:\s*/\s*place\s*of\s*origin)?|place\s*of\s*origin",
        r"n[oơ]i\s*thường\s*tr[uú]|place\s*of\s*residence|nơi\s*cấp|date\s*of\s*issue|c[oó]\s*gi[aá]\s*tr[iị]",
    )
    permanent_address = labeled_value(
        r"n[oơ]i\s*thường\s*tr[uú](?:\s*/\s*place\s*of\s*residence)?|đ[iị]a\s*ch[iỉ]\s*thường\s*tr[uú]|place\s*of\s*residence|permanent\s*residence",
        r"c[oó]\s*gi[aá]\s*tr[iị]|date\s*of\s*expiry|đ[aặ]c\s*đi[eể]m\s*nh[aậ]n\s*d[aạ]ng|personal\s*identification|nơi\s*cấp|date\s*of\s*issue",
    )

    return {
        key: value for key, value in {
            "full_name": full_name,
            "cccd_number": number_match.group(1) if number_match else "",
            "cccd_issue_date": issue_date,
            "cccd_issue_place": place,
            "place_of_origin": place_of_origin,
            "permanent_address": permanent_address,
        }.items() if value
    }


def _identity_match_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D").casefold()
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def validate_saved_identity_matches(
    conn, username: str, *, full_name: str, cccd_number: str,
) -> dict[str, str]:
    """Validate saved CCCD images against the proposed profile identity.

    Legacy employees without CCCD images remain editable. Once either CCCD side
    exists, both sides and readable matching name/number are mandatory.
    """
    _ensure_identity_table(conn)
    rows = conn.execute(text("""
        SELECT side, content, COALESCE(ocr_payload,'{}'::jsonb) ocr_payload
        FROM vera_employee_identity_document
        WHERE employee_username=:username AND side IN ('front','back')
        ORDER BY side
    """), {"username": username}).mappings().all()
    if not rows:
        return {}
    present = {str(row["side"]) for row in rows}
    missing = [IDENTITY_SIDES[side] for side in IDENTITY_SIDES if side not in present]
    if missing:
        raise HTTPException(400, f"Hồ sơ CCCD còn thiếu {', '.join(missing)}; vui lòng tải đủ hai mặt trước khi lưu.")

    extracted: dict[str, str] = {}
    for row in rows:
        cached = row.get("ocr_payload") if isinstance(row.get("ocr_payload"), dict) else {}
        for key, value in cached.items():
            if value and not extracted.get(key):
                extracted[key] = str(value)
    if not extracted.get("full_name") or not extracted.get("cccd_number"):
        for row in rows:
            detected = _extract_cccd_fields(bytes(row["content"]))
            conn.execute(text("""
                UPDATE vera_employee_identity_document
                SET ocr_payload=CAST(:ocr_payload AS jsonb)
                WHERE employee_username=:username AND side=:side
            """), {
                "ocr_payload": json.dumps(detected, ensure_ascii=False),
                "username": username,
                "side": row["side"],
            })
            for key, value in detected.items():
                if value and not extracted.get(key):
                    extracted[key] = str(value)

    declared_name = str(full_name or "").strip()
    declared_number = re.sub(r"\D", "", str(cccd_number or ""))
    detected_name = str(extracted.get("full_name") or "").strip()
    detected_number = re.sub(r"\D", "", str(extracted.get("cccd_number") or ""))
    if not declared_name or not declared_number:
        raise HTTPException(400, "Phải khai Họ và tên đầy đủ và Số Căn cước trước khi lưu hồ sơ có ảnh CCCD.")
    if not detected_name:
        raise HTTPException(400, "Không đọc rõ Họ và tên trên ảnh CCCD; vui lòng chụp hoặc tải lại ảnh rõ hơn.")
    if not detected_number:
        raise HTTPException(400, "Không đọc rõ Số Căn cước trên ảnh CCCD; vui lòng chụp hoặc tải lại ảnh rõ hơn.")
    if _identity_match_key(detected_name) != _identity_match_key(declared_name):
        raise HTTPException(400, f"Họ và tên trên CCCD ({detected_name}) không khớp với Họ và tên đã khai ({declared_name}).")
    if detected_number != declared_number:
        raise HTTPException(400, f"Số Căn cước trên CCCD ({detected_number}) không khớp với số đã khai ({declared_number}).")
    return extracted


def _apply_extracted_cccd(conn, row: dict[str, Any], extracted: dict[str, str]) -> dict[str, str]:
    if not extracted:
        return {}
    payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
    key_map = {
        "cccd_number": "Số CCCD",
        "cccd_issue_date": "Ngày cấp CCCD",
        "cccd_issue_place": "Nơi cấp CCCD",
        "place_of_origin": "Quê quán CCCD",
        "permanent_address": "Địa chỉ thường trú CCCD",
    }
    applied = {}
    for field, payload_key in key_map.items():
        if extracted.get(field) and not str(payload.get(payload_key) or "").strip():
            payload[payload_key] = extracted[field]
            applied[field] = extracted[field]
    if applied:
        conn.execute(text("""
            UPDATE employees
            SET payload=CAST(:payload AS jsonb), updated_at=NOW()
            WHERE username=:username
        """), {
            "payload": json.dumps(payload, ensure_ascii=False),
            "username": row["username"],
        })
    return applied


def _full_employee_address(row: dict[str, Any], payload: dict[str, Any]) -> str:
    detail = str(payload.get("Địa chỉ chi tiết") or "").strip()
    ward = str(payload.get("Xã/Phường") or "").strip()
    district = str(payload.get("Quận/Huyện") or "").strip()
    province = str(payload.get("Tỉnh/Thành phố") or "").strip()
    stored = str(row.get("address") or payload.get("Địa chỉ") or "").strip()
    if detail:
        return ", ".join(part for part in (detail, ward, district, province) if part)
    parts = [stored]
    folded_stored = stored.casefold()
    for value in (ward, district, province):
        if value and value.casefold() not in folded_stored:
            parts.append(value)
    return ", ".join(part for part in parts if part)


def _employee_profile_record(row: dict[str, Any]) -> dict[str, str]:
    payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
    return {
        "username": str(row.get("username") or ""),
        "full_name": str(row.get("full_name") or ""),
        "birth_date": str(row.get("birth_date") or ""),
        "gender": str(payload.get("Giới tính") or ""),
        "ethnicity": str(payload.get("Dân tộc") or ""),
        "phone": str(row.get("phone") or ""),
        "email": str(row.get("email") or ""),
        "address": _full_employee_address(row, payload),
        "role": str(row.get("role") or ""),
        "employment_status": str(payload.get("Trạng thái làm việc") or "Đang làm việc"),
        "employment_start_date": str(row.get("employment_start_date") or ""),
        "employment_end_date": str(payload.get("Ngày nghỉ việc") or payload.get("Ngày kết thúc làm việc") or payload.get("employment_end_date") or ""),
        "work_shift": str(row.get("work_shift") or ""),
        "cccd_number": str(payload.get("Số CCCD") or ""),
        "cccd_issue_date": str(payload.get("Ngày cấp CCCD") or ""),
        "cccd_issue_place": str(payload.get("Nơi cấp CCCD") or ""),
        "bank_account": str(row.get("bank_account") or ""),
        "bank_name": str(row.get("bank_name") or ""),
    }


def _merge_profile_pdfs(items: list[tuple[dict[str, Any], dict[str, bytes]]]) -> bytes:
    writer = PdfWriter()
    for page_number, (profile, media) in enumerate(items, start=1):
        reader = PdfReader(BytesIO(_build_employee_profile_pdf(profile, media, page_label=page_number)))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _pdf_font_names() -> tuple[str, str]:
    regular_candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts/DejaVuSans.ttf"),
    )
    bold_candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts/DejaVuSans-Bold.ttf"),
    )
    regular = next((path for path in regular_candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    if regular and bold:
        if "VeraProfile" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("VeraProfile", str(regular)))
        if "VeraProfileBold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("VeraProfileBold", str(bold)))
        return "VeraProfile", "VeraProfileBold"
    return "Helvetica", "Helvetica-Bold"


def _pdf_image(data: bytes | None, width: float, height: float, label: str, styles) -> Any:
    if data:
        try:
            return PdfImage(BytesIO(data), width=width, height=height, kind="proportional")
        except Exception:
            pass
    placeholder = Table([[Paragraph(escape(label), styles["placeholder"])]], colWidths=[width], rowHeights=[height])
    placeholder.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#B9C9C1")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F6F4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return placeholder


def _build_employee_profile_pdf(
    profile: dict[str, Any], media: dict[str, bytes], *, page_label: int | None = None,
) -> bytes:
    font, bold = _pdf_font_names()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="vera_title", fontName=bold, fontSize=16, leading=20, textColor=colors.HexColor("#173D2F"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="vera_center", fontName=font, fontSize=9, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#3F5149")))
    styles.add(ParagraphStyle(name="section", fontName=bold, fontSize=11, leading=14, textColor=colors.HexColor("#173D2F"), spaceBefore=4, spaceAfter=5))
    styles.add(ParagraphStyle(name="cell", fontName=font, fontSize=8.2, leading=11, textColor=colors.HexColor("#263832")))
    styles.add(ParagraphStyle(name="cell_bold", fontName=bold, fontSize=8.2, leading=11, textColor=colors.HexColor("#173D2F")))
    styles.add(ParagraphStyle(name="signature_title", fontName=bold, fontSize=8.2, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#173D2F")))
    styles.add(ParagraphStyle(name="signature_note", fontName=font, fontSize=8.2, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#3F5149")))
    styles.add(ParagraphStyle(name="placeholder", fontName=bold, fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#789087")))
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Hồ sơ nhân viên - {profile.get('full_name') or profile.get('username') or ''}",
        author=BUSINESS_NAME,
    )
    story = [
        Paragraph(BUSINESS_NAME, styles["vera_title"]),
        Paragraph(f"Địa chỉ: {escape(BUSINESS_ADDRESS)}", styles["vera_center"]),
        Spacer(1, 5 * mm),
        Paragraph("HỒ SƠ NHÂN VIÊN", styles["vera_title"]),
        Spacer(1, 3 * mm),
    ]
    rows = [
        ("Họ và tên", profile.get("full_name")),
        ("Ngày sinh", profile.get("birth_date")),
        ("Giới tính", profile.get("gender")),
        ("Dân tộc", profile.get("ethnicity")),
        ("Số CCCD", profile.get("cccd_number")),
        ("Ngày cấp CCCD", profile.get("cccd_issue_date")),
        ("Nơi cấp CCCD", profile.get("cccd_issue_place")),
        ("Điện thoại", profile.get("phone")),
        ("Email", profile.get("email")),
        ("Địa chỉ", profile.get("address")),
        ("Trạng thái làm việc", profile.get("employment_status")),
        ("Ngày bắt đầu làm", profile.get("employment_start_date")),
    ]
    if str(profile.get("employment_status") or "").strip() == "Đã nghỉ việc":
        rows.insert(11, ("Ngày nghỉ việc", profile.get("employment_end_date")))
    info = Table([
        [Paragraph(escape(label), styles["cell_bold"]), Paragraph(escape(str(value or "")), styles["cell"])]
        for label, value in rows
    ], colWidths=[35 * mm, 91 * mm])
    info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6E0DB")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EDF5F1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    portrait = _pdf_image(media.get("portrait"), 38 * mm, 50.7 * mm, "ẢNH NHÂN VIÊN\n3:4", styles)
    summary = Table([[info, portrait]], colWidths=[129 * mm, 43 * mm])
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([summary, Spacer(1, 5 * mm), Paragraph("ẢNH CĂN CƯỚC CÔNG DÂN", styles["section"])])
    front = _pdf_image(media.get("front"), 82 * mm, 51.7 * mm, "MẶT TRƯỚC CCCD", styles)
    back = _pdf_image(media.get("back"), 82 * mm, 51.7 * mm, "MẶT SAU CCCD", styles)
    cards = Table([[front, back]], colWidths=[86 * mm, 86 * mm])
    cards.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    generated = datetime.now().strftime("%d/%m/%Y %H:%M")
    signatures = Table([
        [Paragraph("Người lao động", styles["signature_title"]), Paragraph("Đại diện HỘ KINH DOANH VERA", styles["signature_title"])],
        [Paragraph("(Ký và ghi rõ họ tên)", styles["signature_note"]), Paragraph("(Ký và ghi rõ họ tên)", styles["signature_note"])],
        ["", ""],
    ], colWidths=[86 * mm, 86 * mm], rowHeights=[7 * mm, 6 * mm, 17 * mm])
    signatures.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.extend([
        KeepTogether([cards, Spacer(1, 4 * mm)]),
        Paragraph(f"Ngày xuất hồ sơ: {generated}", styles["vera_center"]),
        Spacer(1, 5 * mm),
        signatures,
    ])

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#6F7F78"))
        canvas.drawCentredString(A4[0] / 2, 7 * mm, f"{BUSINESS_NAME} - Trang {page_label or doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()


def install_staff_security_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity: Callable[..., Any],
    require_feature: Callable[[Any, Any, str], None],
    norm: Callable[[Any], str],
    identity_type: type,
) -> None:
    if getattr(app.state, "staff_security_routes_installed", False):
        return

    def employee_row(conn, username: str, *, for_update: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if for_update else ""
        row = conn.execute(text("""
            SELECT *
            FROM employees
            WHERE lower(btrim(username))=lower(btrim(:username))
              AND COALESCE(payload->>'__deleted','false') <> 'true'
            LIMIT 1
        """ + suffix), {"username": str(username or "").strip()}).mappings().first()
        if not row:
            raise HTTPException(404, "Không tìm thấy nhân viên.")
        return dict(row)

    def require_identity_access(conn, ident, username: str, *, for_update: bool = False) -> dict[str, Any]:
        row = employee_row(conn, username, for_update=for_update)
        is_admin = str(getattr(ident, "role", "") or "").lower() == "admin"
        is_self = norm(row["username"]) == norm(getattr(ident, "employee_username", ""))
        if not (is_admin or is_self):
            raise HTTPException(403, "Chỉ nhân viên đó hoặc Admin được xem Căn cước công dân.")
        return row

    @app.get("/v2/staff-security/health")
    def staff_security_health():
        return {"ok": True, "release": STAFF_SECURITY_RELEASE}

    @app.post("/v2/staff/identity/ocr")
    async def extract_identity_fields(request: Request, ident: identity_type = Depends(current_identity)):
        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Chỉ chấp nhận ảnh WebP, JPEG hoặc PNG.")
        content = await request.body()
        if not content or len(content) > MAX_IDENTITY_BYTES:
            raise HTTPException(400, "Ảnh CCCD trống hoặc vượt quá dung lượng cho phép.")
        if not _valid_image(content, content_type):
            raise HTTPException(400, "Nội dung file ảnh không hợp lệ.")
        _image_dimensions(content)
        extracted = _extract_cccd_fields(content)
        return {
            "ok": True,
            "extracted_fields": extracted,
            "ocr_status": "extracted" if extracted else "not_detected",
            "message": "Đã đọc thông tin CCCD." if extracted else "Không đọc được thông tin CCCD; vui lòng nhập tay.",
        }

    @app.post("/v2/staff/{username}/reset-password")
    def reset_staff_password(
        username: str,
        body: StaffPasswordReset,
        ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được reset mật khẩu nhân viên.")

        engine = engine_instance()
        conn = engine.connect()
        tx = conn.begin()
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:employees'))"))
            require_feature(conn, ident, "employee_edit_save")
            row = employee_row(conn, username, for_update=True)
            if str(row.get("role") or "").lower() == "admin":
                raise HTTPException(400, "Không reset mật khẩu tài khoản Admin qua hồ sơ nhân viên.")

            error = password_policy_error(
                body.new_password,
                username=str(row.get("username") or ""),
                full_name=str(row.get("full_name") or ""),
            )
            if error:
                raise HTTPException(400, error)

            payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
            payload["must_change_password"] = False
            conn.execute(text("""
                UPDATE employees
                SET password_value=:password,
                    remember_token_hash='', remember_token_expiry='',
                    payload=CAST(:payload AS jsonb), updated_at=NOW()
                WHERE username=:username
            """), {
                "password": body.new_password,
                "payload": json.dumps(payload, ensure_ascii=False),
                "username": row["username"],
            })
            revoke_local_sessions(conn, str(row["username"]), "admin_password_reset")
            tx.commit()
            return {
                "ok": True,
                "message": f"Đã reset mật khẩu cho {row['username']}.",
            }
        except HTTPException:
            if tx.is_active:
                tx.rollback()
            raise
        except Exception as exc:
            if tx.is_active:
                tx.rollback()
            raise HTTPException(500, "Không reset được mật khẩu. Vui lòng thử lại.") from exc
        finally:
            conn.close()

    @app.get("/v2/staff/{username}/identity")
    def identity_metadata(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            records = conn.execute(text("""
                SELECT side, content_type, size_bytes, sha256, updated_at, updated_by
                FROM vera_employee_identity_document
                WHERE employee_username=:username
                ORDER BY side
            """), {"username": row["username"]}).mappings().all()
            by_side = {str(item["side"]): dict(item) for item in records}
            return {
                "ok": True,
                "employee_username": row["username"],
                "front": by_side.get("front"),
                "back": by_side.get("back"),
                "portrait": by_side.get("portrait"),
                "max_bytes": MAX_IDENTITY_BYTES,
                "can_delete_identity": str(getattr(ident, "role", "") or "").lower() == "admin",
                "can_edit_saved_identity": str(getattr(ident, "role", "") or "").lower() == "admin",
            }

    @app.get("/v2/staff/{username}/identity/{side}")
    def identity_image(username: str, side: str, ident: identity_type = Depends(current_identity)):
        if side not in MEDIA_SIDES:
            raise HTTPException(404, "Loại ảnh hồ sơ không hợp lệ.")
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            document = conn.execute(text("""
                SELECT content_type, content
                FROM vera_employee_identity_document
                WHERE employee_username=:username AND side=:side
            """), {"username": row["username"], "side": side}).mappings().first()
            if not document:
                raise HTTPException(404, f"Chưa có {MEDIA_SIDES[side].lower()}.")
            content = bytes(document["content"])
            return Response(
                content=content,
                media_type=str(document["content_type"]),
                headers={
                    "Cache-Control": "private, no-store, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @app.put("/v2/staff/{username}/identity/{side}")
    async def upload_identity_image(
        username: str,
        side: str,
        request: Request,
        ident: identity_type = Depends(current_identity),
    ):
        if side not in MEDIA_SIDES:
            raise HTTPException(404, "Loại ảnh hồ sơ không hợp lệ.")
        content_type = str(request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Chỉ chấp nhận ảnh WebP, JPEG hoặc PNG.")
        content = await request.body()
        if not content:
            raise HTTPException(400, "Ảnh hồ sơ đang trống.")
        if len(content) > MAX_IDENTITY_BYTES:
            raise HTTPException(413, "Ảnh sau nén vẫn quá lớn. Vui lòng chọn ảnh rõ hơn hoặc thử lại.")
        if not _valid_image(content, content_type):
            raise HTTPException(400, "Nội dung file ảnh không hợp lệ.")
        width, height = _image_dimensions(content)
        if side == "portrait" and abs((width / max(height, 1)) - 0.75) > 0.035:
            raise HTTPException(400, "Ảnh nhân viên phải được Crop đúng tỷ lệ dọc 3:4 trước khi lưu.")

        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username, for_update=True)
            _ensure_identity_table(conn)
            digest = hashlib.sha256(content).hexdigest()
            extracted = _extract_cccd_fields(content) if side in IDENTITY_SIDES else {}
            conn.execute(text("""
                INSERT INTO vera_employee_identity_document(
                    employee_username, side, content_type, content, size_bytes,
                    sha256, updated_at, updated_by, ocr_payload
                ) VALUES (
                    :username, :side, :content_type, :content, :size_bytes,
                    :sha256, NOW(), :updated_by, CAST(:ocr_payload AS jsonb)
                )
                ON CONFLICT (employee_username, side) DO UPDATE SET
                    content_type=EXCLUDED.content_type,
                    content=EXCLUDED.content,
                    size_bytes=EXCLUDED.size_bytes,
                    sha256=EXCLUDED.sha256,
                    updated_at=NOW(),
                    updated_by=EXCLUDED.updated_by,
                    ocr_payload=EXCLUDED.ocr_payload
            """), {
                "username": row["username"],
                "side": side,
                "content_type": content_type,
                "content": content,
                "size_bytes": len(content),
                "sha256": digest,
                "updated_by": str(getattr(ident, "employee_username", "") or ""),
                "ocr_payload": json.dumps(extracted, ensure_ascii=False),
            })
            applied = _apply_extracted_cccd(conn, row, extracted)
            return {
                "ok": True,
                "side": side,
                "size_bytes": len(content),
                "sha256": digest,
                "extracted_fields": extracted,
                "applied_fields": applied,
                "ocr_status": "extracted" if extracted else ("not_applicable" if side == "portrait" else "not_detected"),
                "message": f"Đã lưu {MEDIA_SIDES[side]} ({round(len(content) / 1024)} KB).",
            }

    @app.delete("/v2/staff/{username}/identity/{side}")
    def delete_identity_image(username: str, side: str, ident: identity_type = Depends(current_identity)):
        if side not in MEDIA_SIDES:
            raise HTTPException(404, "Loại ảnh hồ sơ không hợp lệ.")
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            if side in IDENTITY_SIDES and str(getattr(ident, "role", "") or "").lower() != "admin":
                raise HTTPException(403, "Nhân viên không được xóa ảnh CCCD sau khi đã lưu. Vui lòng liên hệ Admin.")
            _ensure_identity_table(conn)
            result = conn.execute(text("""
                DELETE FROM vera_employee_identity_document
                WHERE employee_username=:username AND side=:side
            """), {"username": row["username"], "side": side})
            return {
                "ok": True,
                "deleted": int(result.rowcount or 0),
                "message": f"Đã xóa {MEDIA_SIDES[side].lower()}.",
            }

    @app.get("/v2/staff/{username}/profile.pdf")
    def export_employee_profile_pdf(username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            row = require_identity_access(conn, ident, username)
            _ensure_identity_table(conn)
            documents = conn.execute(text("""
                SELECT side, content
                FROM vera_employee_identity_document
                WHERE employee_username=:username
            """), {"username": row["username"]}).mappings().all()
            media = {str(item["side"]): bytes(item["content"]) for item in documents}
            profile = _employee_profile_record(row)
        content = _build_employee_profile_pdf(profile, media)
        safe_name = re.sub(r"[^\w.-]+", "_", profile["full_name"] or profile["username"], flags=re.UNICODE).strip("_") or "Nhan_Vien"
        filename = f"Ho_So_{safe_name}.pdf"
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                "Cache-Control": "private, no-store, max-age=0",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/v2/staff/profiles.pdf")
    def export_selected_employee_profiles_pdf(
        body: StaffBatchPdfRequest,
        ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được xuất đồng loạt hồ sơ nhân viên.")
        usernames = []
        seen = set()
        for value in body.usernames:
            username = str(value or "").strip()
            key = norm(username)
            if username and key not in seen:
                seen.add(key)
                usernames.append(username)
        if not usernames:
            raise HTTPException(400, "Chưa chọn nhân viên cần xuất hồ sơ PDF.")

        items = []
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "staff_export")
            _ensure_identity_table(conn)
            for username in usernames:
                row = employee_row(conn, username)
                documents = conn.execute(text("""
                    SELECT side, content
                    FROM vera_employee_identity_document
                    WHERE employee_username=:username
                """), {"username": row["username"]}).mappings().all()
                media = {str(item["side"]): bytes(item["content"]) for item in documents}
                items.append((_employee_profile_record(row), media))

        content = _merge_profile_pdfs(items)
        filename = f"Ho_So_Nhan_Vien_Da_Chon_{len(items)}.pdf"
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                "Cache-Control": "private, no-store, max-age=0",
                "X-Content-Type-Options": "nosniff",
            },
        )

    app.state.staff_security_routes_installed = True
    app.state.staff_security_release = STAFF_SECURITY_RELEASE
