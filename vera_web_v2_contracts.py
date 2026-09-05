"""Editable KTV contracts and printable PDF exports for Leader/employee profiles."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any, Callable, Literal
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import text

from vera_web_v2_staff_security import _ensure_identity_table, _extract_cccd_fields


CONTRACT_RELEASE = "1.2-role-specific-contracts"
SETTING_CATEGORY = "contract"
SETTING_KEY = "contract_1"
ELIGIBLE_ROLES = ("leader", "nhanvien")
ROLE_LABELS = {
    "leader": "Leader",
    "nhanvien": "Nhân viên",
    "letan": "Lễ tân",
    "locker": "Locker",
    "quanly": "Quản lý",
    "tapvu": "Tạp vụ",
}
ContractType = Literal["ktv", "letan", "locker", "quanly", "tapvu"]

DEFAULT_TEMPLATE_CONTENT = """Điều 1: Thời hạn và công việc hợp đồng
Loại hợp đồng lao động: Nhân viên bán thời gian.
Thời hạn hợp đồng: {{contract_term}}.
Công việc phải làm: Xoa bóp, gội đầu.
Địa điểm làm việc: Trụ sở hộ kinh doanh tại {{business_address}}.

Điều 2: Chế độ làm việc
Được sử dụng khăn, điện thoại bàn và những đồ dùng cần thiết phục vụ cho công việc.

Điều 3: Nghĩa vụ và quyền lợi của người lao động
1. Quyền lợi
a) Mức lương: {{salary}}.
b) Hình thức trả lương: Được trả lương vào ngày 10 hằng tháng.
c) Chế độ nghỉ ngơi: Mỗi tuần được nghỉ một ngày theo sự sắp xếp của quản lý hoặc người sử dụng lao động.

2. Nghĩa vụ
a) Hoàn thành những công việc đã cam kết trong hợp đồng lao động.
b) Chấp hành nghiêm túc nội quy, quy chế của đơn vị, nội quy kỷ luật lao động và an toàn lao động.
c) Thực hiện nghiêm túc BẢN CAM KẾT THỰC HIỆN ĐÚNG NỘI QUY VÀ QUY CHẾ KỶ LUẬT.
d) Nghỉ việc phải viết đơn xin nghỉ việc theo mẫu của Hộ Kinh Doanh Vera và viết đơn trước 30 ngày. Người sử dụng lao động có quyền quyết định cho người lao động nghỉ việc ngay sau khi nhận được đơn xin nghỉ việc.
e) Người lao động bị cho thôi việc ngay lập tức nếu vi phạm nội quy của Hộ Kinh Doanh Vera và sẽ không được nhận số tiền lương còn lại.
f) Bồi thường thiệt hại khi người lao động vi phạm nội quy hoặc có hành động làm ảnh hưởng tới chất lượng dịch vụ, hoạt động kinh doanh của Hộ Kinh Doanh Vera.

Điều 4: Nghĩa vụ và quyền hạn của người sử dụng lao động
1. Nghĩa vụ
a) Bảo đảm việc làm và thực hiện đầy đủ những điều đã cam kết trong hợp đồng lao động.
b) Thanh toán đầy đủ, đúng thời hạn các chế độ và quyền lợi cho người lao động theo hợp đồng lao động.

2. Quyền hạn
a) Điều hành người lao động hoàn thành công việc theo hợp đồng, kỷ luật người lao động theo nội quy; có quyền bố trí, điều chuyển, tạm ngừng việc hoặc chấm dứt hợp đồng lao động.
b) Có quyền chấm dứt hợp đồng với người lao động ngay lập tức khi nhận được đơn xin nghỉ việc của người lao động.
c) Có quyền chấm dứt hợp đồng với người lao động ngay lập tức khi người lao động vi phạm nội quy của Hộ Kinh Doanh Vera.

Điều 5: Điều khoản chung
Hợp đồng lao động được làm thành 02 bản có giá trị ngang nhau, mỗi bên giữ một bản.
Hợp đồng lao động có hiệu lực: {{contract_effective}}.
Hợp đồng làm tại: Trụ sở Hộ Kinh Doanh Vera.
Hợp đồng ký ngày: {{sign_day}}/{{sign_month}}/{{sign_year}}."""

DEFAULT_SETTINGS: dict[str, str] = {
    "representative_name": "Huỳnh Thị Bạch Tuyết",
    "representative_title": "Chủ hộ",
    "business_name": "HỘ KINH DOANH VERA",
    "business_address": "193 Trương Định, Phường Tam Hiệp, Thành phố Đồng Nai",
    "contract_term": "30 ngày kể từ ngày ký hợp đồng",
    "contract_effective": "Kể từ ngày ký hợp đồng",
    "signing_place": "Đồng Nai",
    "signing_date": "",
    "salary_amount": "25.000",
    "salary_unit": "VNĐ/giờ",
    "template_content": DEFAULT_TEMPLATE_CONTENT,
}


def _role_template(
    *,
    contract_type_line: str,
    work_line: str,
    equipment_line: str,
    salary_line: str,
) -> str:
    return (
        DEFAULT_TEMPLATE_CONTENT
        .replace("Loại hợp đồng lao động: Nhân viên bán thời gian.", contract_type_line)
        .replace("Công việc phải làm: Xoa bóp, gội đầu.", work_line)
        .replace(
            "Được sử dụng khăn, điện thoại bàn và những đồ dùng cần thiết phục vụ cho công việc.",
            equipment_line,
        )
        .replace("a) Mức lương: {{salary}}.", salary_line)
    )


LE_TAN_TEMPLATE_CONTENT = _role_template(
    contract_type_line="Loại hợp đồng lao động: Nhân viên Lễ tân bán thời gian.",
    work_line=(
        "Công việc phải làm: Đón tiếp và hướng dẫn khách; tiếp nhận đặt lịch; thu ngân; "
        "phối hợp sắp xếp phòng, nhân viên và thực hiện các công việc Lễ tân theo phân công."
    ),
    equipment_line=(
        "Được sử dụng máy tính, điện thoại bàn, phần mềm quản lý, máy in và những đồ dùng "
        "cần thiết phục vụ cho công việc."
    ),
    salary_line="a) Mức lương theo giờ: {{salary}}.",
)

LOCKER_TEMPLATE_CONTENT = _role_template(
    contract_type_line="Loại hợp đồng lao động: Nhân viên Locker bán thời gian.",
    work_line=(
        "Công việc phải làm: Tiếp nhận, bảo quản và bàn giao tư trang của khách; quản lý "
        "chìa khóa, tủ đồ, khăn và vật dụng tại khu vực Locker; hỗ trợ khách và thực hiện "
        "các công việc Locker theo phân công."
    ),
    equipment_line=(
        "Được sử dụng chìa khóa, tủ đồ, sổ bàn giao, điện thoại nội bộ và những đồ dùng "
        "cần thiết phục vụ cho công việc."
    ),
    salary_line="a) Mức lương theo giờ: {{salary}}.",
)

QUAN_LY_TEMPLATE_CONTENT = _role_template(
    contract_type_line="Loại hợp đồng lao động: Nhân viên Quản lý bán thời gian.",
    work_line=(
        "Công việc phải làm: Điều hành hoạt động trong ca; phân công và giám sát nhân viên; "
        "xử lý tình huống với khách; kiểm tra chất lượng dịch vụ, doanh thu và thực hiện "
        "các công việc Quản lý theo phân công."
    ),
    equipment_line=(
        "Được sử dụng máy tính, điện thoại, phần mềm quản lý, máy in, hồ sơ vận hành và "
        "những đồ dùng cần thiết phục vụ cho công việc."
    ),
    salary_line="a) Mức lương theo giờ: {{salary}}.",
)

TAP_VU_TEMPLATE_CONTENT = _role_template(
    contract_type_line="Loại hợp đồng lao động: Nhân viên Tạp vụ.",
    work_line=(
        "Công việc phải làm: Vệ sinh phòng dịch vụ, khu vực chung và nhà vệ sinh; giặt, "
        "gấp, bổ sung khăn và vật dụng; thu gom rác, sắp xếp dụng cụ và thực hiện các "
        "công việc Tạp vụ theo phân công."
    ),
    equipment_line=(
        "Được sử dụng dụng cụ, máy móc, hóa chất vệ sinh, đồ bảo hộ và những đồ dùng "
        "cần thiết phục vụ cho công việc."
    ),
    salary_line="a) Mức lương cơ bản: {{salary}}.",
)


def _defaults_for(template_content: str, salary_amount: str, salary_unit: str) -> dict[str, str]:
    return {
        **DEFAULT_SETTINGS,
        "salary_amount": salary_amount,
        "salary_unit": salary_unit,
        "template_content": template_content,
    }


CONTRACT_TYPE_CONFIGS: dict[str, dict[str, Any]] = {
    "ktv": {
        "label": "Hợp đồng KTV",
        "short_label": "KTV",
        "roles": ELIGIBLE_ROLES,
        "setting_key": SETTING_KEY,
        "document_title": "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN",
        "file_slug": "Hop_Dong_KTV",
        "defaults": DEFAULT_SETTINGS,
    },
    "letan": {
        "label": "Hợp đồng Lễ tân",
        "short_label": "Lễ tân",
        "roles": ("letan",),
        "setting_key": "contract_1_letan",
        "document_title": "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN",
        "file_slug": "Hop_Dong_Le_Tan",
        "defaults": _defaults_for(
            LE_TAN_TEMPLATE_CONTENT,
            "26.000 VNĐ/giờ từ 09:00 đến 16:30; 30.000 VNĐ/giờ từ 16:30 đến 22:00; "
            "33.000 VNĐ/giờ từ 22:00 đến 03:00",
            "",
        ),
    },
    "locker": {
        "label": "Hợp đồng Locker",
        "short_label": "Locker",
        "roles": ("locker",),
        "setting_key": "contract_1_locker",
        "document_title": "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN",
        "file_slug": "Hop_Dong_Locker",
        "defaults": _defaults_for(
            LOCKER_TEMPLATE_CONTENT,
            "………………………",
            "VNĐ/giờ, áp dụng theo cấu hình lương hiện hành của Hộ Kinh Doanh Vera tại thời điểm ký hợp đồng",
        ),
    },
    "quanly": {
        "label": "Hợp đồng Quản lý",
        "short_label": "Quản lý",
        "roles": ("quanly",),
        "setting_key": "contract_1_quanly",
        "document_title": "HỢP ĐỒNG LAO ĐỘNG BÁN THỜI GIAN",
        "file_slug": "Hop_Dong_Quan_Ly",
        "defaults": _defaults_for(
            QUAN_LY_TEMPLATE_CONTENT,
            "………………………",
            "VNĐ/giờ, áp dụng theo cấu hình lương hiện hành của Hộ Kinh Doanh Vera tại thời điểm ký hợp đồng",
        ),
    },
    "tapvu": {
        "label": "Hợp đồng Tạp vụ",
        "short_label": "Tạp vụ",
        "roles": ("tapvu",),
        "setting_key": "contract_1_tapvu",
        "document_title": "HỢP ĐỒNG LAO ĐỘNG",
        "file_slug": "Hop_Dong_Tap_Vu",
        "defaults": _defaults_for(
            TAP_VU_TEMPLATE_CONTENT,
            "………………………",
            "VNĐ/tháng, tính theo 26 ngày công/tháng và áp dụng theo cấu hình lương hiện hành của Hộ Kinh Doanh Vera",
        ),
    },
}

SETTING_FIELDS = tuple(DEFAULT_SETTINGS)
GENERAL_SETTING_FIELDS = tuple(field for field in SETTING_FIELDS if field != "template_content")


class ContractSettingsUpdate(BaseModel):
    contract_type: ContractType = "ktv"
    representative_name: str | None = Field(default=None, max_length=300)
    representative_title: str | None = Field(default=None, max_length=200)
    business_name: str | None = Field(default=None, max_length=300)
    business_address: str | None = Field(default=None, max_length=1000)
    contract_term: str | None = Field(default=None, max_length=500)
    contract_effective: str | None = Field(default=None, max_length=500)
    signing_place: str | None = Field(default=None, max_length=300)
    signing_date: str | None = Field(default=None, max_length=30)
    salary_amount: str | None = Field(default=None, max_length=100)
    salary_unit: str | None = Field(default=None, max_length=100)
    template_content: str | None = Field(default=None, max_length=30000)
    expected_revision: int | None = Field(default=None, ge=0)


class ContractExportRequest(BaseModel):
    contract_type: ContractType = "ktv"
    scope: Literal["selected", "individual", "department", "all"] = "selected"
    username: str = Field(default="", max_length=300)
    usernames: list[str] = Field(default_factory=list, max_length=500)
    role: Literal["leader", "nhanvien", "letan", "locker", "quanly", "tapvu"] | None = None


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "có", "co"}


def _contract_config(contract_type: str) -> dict[str, Any]:
    config = CONTRACT_TYPE_CONFIGS.get(str(contract_type or "").strip().lower())
    if not config:
        raise HTTPException(400, "Loại hợp đồng không hợp lệ.")
    return config


def _settings(conn, contract_type: str = "ktv") -> tuple[dict[str, str], int]:
    config = _contract_config(contract_type)
    row = conn.execute(text("""
        SELECT value_json, revision
        FROM vera_app_setting
        WHERE category=:category AND setting_key=:setting_key
        LIMIT 1
    """), {
        "category": SETTING_CATEGORY,
        "setting_key": config["setting_key"],
    }).mappings().first()
    saved = row.get("value_json") if row and isinstance(row.get("value_json"), dict) else {}
    merged = {
        field: str(saved.get(field) if saved.get(field) is not None else default)
        for field, default in config["defaults"].items()
    }
    return merged, int(row.get("revision") or 0) if row else 0


def _employee_status(payload: dict[str, Any]) -> str:
    return str(payload.get("Trạng thái làm việc") or payload.get("employment_status") or "Đang làm việc").strip()


def _employee_hidden(payload: dict[str, Any]) -> bool:
    return _as_bool(payload.get("Ẩn nhân viên") if "Ẩn nhân viên" in payload else payload.get("profile_hidden"))


def _eligible_employee_rows(conn, roles: tuple[str, ...] = ELIGIBLE_ROLES) -> list[dict[str, Any]]:
    allowed_roles = {str(role).strip().lower() for role in roles}
    rows = conn.execute(text("""
        SELECT *
        FROM employees
        WHERE lower(COALESCE(role,'')) IN ('leader','nhanvien','letan','locker','quanly','tapvu')
          AND COALESCE(payload->>'__deleted','false') <> 'true'
        ORDER BY CASE lower(COALESCE(role,''))
                    WHEN 'leader' THEN 0 WHEN 'nhanvien' THEN 1 WHEN 'letan' THEN 2
                    WHEN 'locker' THEN 3 WHEN 'quanly' THEN 4 WHEN 'tapvu' THEN 5 ELSE 6 END,
                 COALESCE(stt,2147483647), COALESCE(full_name,username), username
    """)).mappings().all()
    output = []
    for source in rows:
        row = dict(source)
        if str(row.get("role") or "").strip().lower() not in allowed_roles:
            continue
        payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
        if _employee_status(payload) != "Đang làm việc" or _employee_hidden(payload):
            continue
        row["payload"] = payload
        output.append(row)
    return output


def _employee_summary(row: dict[str, Any]) -> dict[str, str]:
    return {
        "username": str(row.get("username") or ""),
        "full_name": str(row.get("full_name") or row.get("username") or ""),
        "role": str(row.get("role") or "").lower(),
        "role_label": ROLE_LABELS.get(str(row.get("role") or "").lower(), str(row.get("role") or "")),
    }


def _date_parts(value: Any) -> tuple[str, str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "……", "……", "…………"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(raw[:10], fmt)
            return f"{parsed.day:02d}", f"{parsed.month:02d}", str(parsed.year)
        except ValueError:
            continue
    return "……", "……", "…………"


def _display_date(value: Any) -> str:
    if not str(value or "").strip():
        return ""
    day, month, year = _date_parts(value)
    return f"{day}/{month}/{year}"


def _full_profile_address(row: dict[str, Any], payload: dict[str, Any]) -> str:
    detail = str(payload.get("Địa chỉ cụ thể") or payload.get("Địa chỉ chi tiết") or row.get("address") or "").strip()
    ward = str(payload.get("Xã/Phường") or "").strip()
    district = str(payload.get("Quận/Huyện") or "").strip()
    province = str(payload.get("Tỉnh/Thành phố") or "").strip()
    values: list[str] = []
    folded = ""
    for value in (detail, ward, district, province):
        if value and value.casefold() not in folded:
            values.append(value)
            folded = ", ".join(values).casefold()
    return ", ".join(values)


def _identity_ocr(conn, row: dict[str, Any]) -> dict[str, str]:
    _ensure_identity_table(conn)
    records = conn.execute(text("""
        SELECT side, content, COALESCE(ocr_payload,'{}'::jsonb) AS ocr_payload
        FROM vera_employee_identity_document
        WHERE employee_username=:username AND side IN ('front','back')
        ORDER BY side
    """), {"username": row["username"]}).mappings().all()
    combined: dict[str, str] = {}
    for record in records:
        cached = record.get("ocr_payload") if isinstance(record.get("ocr_payload"), dict) else {}
        for key, value in cached.items():
            if value and not combined.get(key):
                combined[key] = str(value)
    missing_address = not combined.get("permanent_address") or not combined.get("place_of_origin")
    if missing_address:
        for record in records:
            detected = _extract_cccd_fields(bytes(record["content"]))
            conn.execute(text("""
                UPDATE vera_employee_identity_document
                SET ocr_payload=CAST(:payload AS jsonb)
                WHERE employee_username=:username AND side=:side
            """), {
                "payload": json.dumps(detected, ensure_ascii=False),
                "username": row["username"],
                "side": record["side"],
            })
            for key, value in detected.items():
                if value and not combined.get(key):
                    combined[key] = str(value)
    return combined


def _contract_employee(conn, row: dict[str, Any]) -> dict[str, str]:
    payload = dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {}
    ocr = _identity_ocr(conn, row)
    permanent_address = str(
        ocr.get("permanent_address")
        or payload.get("Địa chỉ thường trú CCCD")
        or payload.get("Nơi thường trú CCCD")
        or ""
    ).strip()
    birth_place = str(
        ocr.get("place_of_origin")
        or payload.get("Quê quán CCCD")
        or payload.get("Nơi sinh")
        or payload.get("Tỉnh/Thành phố")
        or ""
    ).strip()
    cccd_number = str(payload.get("Số CCCD") or ocr.get("cccd_number") or "").strip()
    issue_date = str(payload.get("Ngày cấp CCCD") or ocr.get("cccd_issue_date") or "").strip()
    issue_place = str(payload.get("Nơi cấp CCCD") or ocr.get("cccd_issue_place") or "").strip()
    return {
        "username": str(row.get("username") or ""),
        "employee_name": str(row.get("full_name") or "").strip(),
        "birth_date": str(row.get("birth_date") or ""),
        "birth_place": birth_place,
        "permanent_address": permanent_address,
        "cccd_number": cccd_number,
        "cccd_issue_date": _display_date(issue_date),
        "cccd_issue_place": issue_place,
        "role": str(row.get("role") or "").lower(),
    }


REQUIRED_EMPLOYEE_FIELDS: tuple[tuple[str, str], ...] = (
    ("employee_name", "Họ và tên đầy đủ"),
    ("birth_date", "Ngày sinh"),
    ("birth_place", "Nơi sinh/Tỉnh, thành phố"),
    ("permanent_address", "Địa chỉ thường trú từ CCCD"),
    ("cccd_number", "Số CCCD"),
    ("cccd_issue_date", "Ngày cấp CCCD"),
    ("cccd_issue_place", "Nơi cấp CCCD"),
)


def _missing_contract_fields(employee: dict[str, str]) -> list[str]:
    return [label for key, label in REQUIRED_EMPLOYEE_FIELDS if not str(employee.get(key) or "").strip()]


def _ensure_complete_contract_profiles(employees: list[dict[str, str]]) -> None:
    incomplete: list[tuple[str, list[str]]] = []
    for employee in employees:
        missing = _missing_contract_fields(employee)
        if missing:
            name = employee.get("employee_name") or employee.get("username") or "Không rõ nhân viên"
            incomplete.append((name, missing))
    if not incomplete:
        return
    details = "; ".join(f"{name}: {', '.join(fields)}" for name, fields in incomplete[:20])
    if len(incomplete) > 20:
        details += f"; và {len(incomplete) - 20} nhân viên khác"
    raise HTTPException(
        422,
        "Không thể xuất PDF vì hồ sơ người lao động còn thiếu thông tin. "
        f"Vui lòng bổ sung: {details}.",
    )


def _pdf_fonts() -> tuple[str, str]:
    candidates = (
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts/DejaVuSans.ttf"), Path("/opt/codex/runtimes/codex-primary-runtime/dependencies/native/poppler/poppler/fonts/DejaVuSans-Bold.ttf")),
    )
    regular, bold = next(((a, b) for a, b in candidates if a.exists() and b.exists()), (None, None))
    if regular and bold:
        if "VeraContract" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("VeraContract", str(regular)))
        if "VeraContractBold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("VeraContractBold", str(bold)))
        return "VeraContract", "VeraContractBold"
    return "Helvetica", "Helvetica-Bold"


def _replace_placeholders(source: str, values: dict[str, str]) -> str:
    rendered = str(source or "")
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value or ""))
    return rendered


def _contract_pdf(
    employee: dict[str, str],
    settings: dict[str, str],
    contract_type: str = "ktv",
) -> bytes:
    config = _contract_config(contract_type)
    regular, bold = _pdf_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="contract_center_bold", fontName=bold, fontSize=10.2, leading=13, alignment=TA_CENTER, spaceAfter=2))
    styles.add(ParagraphStyle(name="contract_title", fontName=bold, fontSize=15, leading=19, alignment=TA_CENTER, spaceBefore=5, spaceAfter=8))
    styles.add(ParagraphStyle(name="contract_body", fontName=regular, fontSize=9, leading=12, alignment=TA_JUSTIFY, firstLineIndent=8 * mm, spaceAfter=3))
    styles.add(ParagraphStyle(name="contract_line", fontName=regular, fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=1.5))
    styles.add(ParagraphStyle(name="contract_heading", fontName=bold, fontSize=9.3, leading=12.2, alignment=TA_LEFT, spaceBefore=2, spaceAfter=2))
    styles.add(ParagraphStyle(name="contract_signature", fontName=bold, fontSize=9, leading=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="contract_signature_note", fontName=regular, fontSize=8.5, leading=11, alignment=TA_CENTER))

    sign_value = settings.get("signing_date") or date.today().isoformat()
    sign_day, sign_month, sign_year = _date_parts(sign_value)
    birth_day, birth_month, birth_year = _date_parts(employee.get("birth_date"))
    salary = " ".join(part for part in (settings.get("salary_amount"), settings.get("salary_unit")) if part).strip()
    placeholders = {
        **settings,
        **employee,
        "salary": salary,
        "birth_day": birth_day,
        "birth_month": birth_month,
        "birth_year": birth_year,
        "sign_day": sign_day,
        "sign_month": sign_month,
        "sign_year": sign_year,
    }

    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=13 * mm, bottomMargin=14 * mm,
        title=f"{config['label']} - {employee['employee_name']}",
        author=settings.get("business_name") or "HỘ KINH DOANH VERA",
    )
    story: list[Any] = [
        Paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", styles["contract_center_bold"]),
        Paragraph("Độc lập – Tự do – Hạnh phúc", styles["contract_center_bold"]),
        Paragraph("*****", styles["contract_center_bold"]),
        Paragraph(escape(config["document_title"]), styles["contract_title"]),
        Paragraph(
            f"Hôm nay, ngày {sign_day} tháng {sign_month} năm {sign_year}, tại {escape(settings.get('signing_place') or '………………')}, chúng tôi gồm:",
            styles["contract_body"],
        ),
        Paragraph(f"BÊN SỬ DỤNG LAO ĐỘNG: <b>{escape(settings.get('business_name') or '')}</b>", styles["contract_heading"]),
        Paragraph(f"Đại diện: <b>{escape(settings.get('representative_name') or '')}</b> &nbsp;&nbsp;&nbsp; Chức vụ: {escape(settings.get('representative_title') or '')}", styles["contract_line"]),
        Paragraph(f"Địa chỉ: {escape(settings.get('business_address') or '')}", styles["contract_line"]),
        Spacer(1, 2 * mm),
        Paragraph("VÀ MỘT BÊN LÀ NGƯỜI LAO ĐỘNG:", styles["contract_heading"]),
        Paragraph(f"Ông/Bà: <b>{escape(employee['employee_name'])}</b>", styles["contract_line"]),
        Paragraph(f"Sinh ngày: {birth_day} tháng {birth_month} năm {birth_year} &nbsp;&nbsp;&nbsp; Tại: {escape(employee['birth_place'])}", styles["contract_line"]),
        Paragraph(f"Địa chỉ thường trú: {escape(employee['permanent_address'])}", styles["contract_line"]),
        Paragraph(f"Số CCCD: {escape(employee['cccd_number'])} &nbsp;&nbsp;&nbsp; cấp ngày {escape(employee['cccd_issue_date'])}", styles["contract_line"]),
        Paragraph(f"Nơi cấp: {escape(employee['cccd_issue_place'])}", styles["contract_line"]),
        Spacer(1, 2 * mm),
        Paragraph("Hai bên thỏa thuận ký kết hợp đồng lao động và cam kết thực hiện các điều khoản sau:", styles["contract_body"]),
    ]

    body = _replace_placeholders(settings.get("template_content") or DEFAULT_TEMPLATE_CONTENT, placeholders)
    for line in body.splitlines():
        clean = line.strip()
        if not clean:
            story.append(Spacer(1, 1.2 * mm))
            continue
        escaped = escape(clean)
        if re.match(r"^(Điều\s+\d+|\d+\.)", clean, flags=re.IGNORECASE):
            style = styles["contract_heading"]
        elif clean.startswith("-"):
            escaped = "• " + escape(clean[1:].strip())
            style = styles["contract_line"]
        else:
            style = styles["contract_body"]
        story.append(Paragraph(escaped, style))

    story.extend([
        Spacer(1, 4 * mm),
        Paragraph(
            f"Hợp đồng được ký ngày {sign_day}/{sign_month}/{sign_year} tại {escape(settings.get('signing_place') or '………………')}.",
            styles["contract_body"],
        ),
        Spacer(1, 7 * mm),
    ])
    signatures = Table([
        [Paragraph("NGƯỜI LAO ĐỘNG", styles["contract_signature"]), Paragraph("ĐẠI DIỆN NGƯỜI SỬ DỤNG LAO ĐỘNG", styles["contract_signature"])],
        [Paragraph("(Ký và ghi rõ họ tên)", styles["contract_signature_note"]), Paragraph("(Ký và ghi rõ họ tên)", styles["contract_signature_note"])],
        [Spacer(1, 23 * mm), Spacer(1, 23 * mm)],
        [Paragraph(escape(employee["employee_name"]), styles["contract_signature"]), Paragraph(escape(settings.get("representative_name") or ""), styles["contract_signature"])],
    ], colWidths=[88 * mm, 88 * mm])
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(signatures)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(colors.HexColor("#68766F"))
        canvas.drawString(17 * mm, 7 * mm, f"{config['label']} · {employee['employee_name']}")
        canvas.drawRightString(A4[0] - 17 * mm, 7 * mm, f"Trang {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _merge_contract_pdfs(
    items: list[tuple[dict[str, str], dict[str, str]]],
    contract_type: str = "ktv",
) -> bytes:
    writer = PdfWriter()
    for employee, settings in items:
        reader = PdfReader(BytesIO(_contract_pdf(employee, settings, contract_type)))
        for page in reader.pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def install_contract_1_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity: Callable[..., Any],
    require_feature: Callable[[Any, Any, str], None],
    feature_allowed: Callable[[Any, Any, str], bool],
    norm: Callable[[Any], str],
    identity_type: type,
) -> None:
    if getattr(app.state, "contract_1_routes_installed", False):
        return

    @app.get("/v2/contracts/1")
    def contract_1_overview(
        contract_type: ContractType = "ktv",
        ident: identity_type = Depends(current_identity),
    ):
        config = _contract_config(contract_type)
        eligible_roles = tuple(config["roles"])
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "contract_1_view")
            settings, revision = _settings(conn, contract_type)
            can_export_self = feature_allowed(conn, ident, "contract_1_export_self")
            can_export_bulk = feature_allowed(conn, ident, "contract_1_export_bulk")
            can_edit_template = feature_allowed(conn, ident, "contract_1_template_edit")
            can_edit_settings = feature_allowed(conn, ident, "contract_1_settings_edit")
            rows = _eligible_employee_rows(conn, eligible_roles)
            if not can_export_bulk:
                own_key = norm(getattr(ident, "employee_username", ""))
                rows = [row for row in rows if norm(row.get("username")) == own_key]
            return {
                "ok": True,
                "release": CONTRACT_RELEASE,
                "contract_type": contract_type,
                "contract_label": config["label"],
                "contract_types": [
                    {
                        "value": key,
                        "label": item["label"],
                        "roles": list(item["roles"]),
                    }
                    for key, item in CONTRACT_TYPE_CONFIGS.items()
                ],
                "settings": settings,
                "revision": revision,
                "employees": [_employee_summary(row) for row in rows],
                "roles": [{"value": role, "label": ROLE_LABELS[role]} for role in eligible_roles],
                "permissions": {
                    "can_export_self": can_export_self,
                    "can_export_bulk": can_export_bulk,
                    "can_edit_template": can_edit_template,
                    "can_edit_settings": can_edit_settings,
                },
            }

    @app.put("/v2/contracts/1/settings")
    def save_contract_1_settings(body: ContractSettingsUpdate, ident: identity_type = Depends(current_identity)):
        config = _contract_config(body.contract_type)
        updates = body.model_dump(exclude={"contract_type", "expected_revision"}, exclude_none=True)
        if not updates:
            raise HTTPException(400, "Chưa có thay đổi cài đặt hợp đồng.")
        with engine_instance().begin() as conn:
            current, revision = _settings(conn, body.contract_type)
            changed_template = "template_content" in updates and str(updates["template_content"]) != current["template_content"]
            changed_general = any(field in updates and str(updates[field]) != current[field] for field in GENERAL_SETTING_FIELDS)
            if changed_template:
                require_feature(conn, ident, "contract_1_template_edit")
            if changed_general:
                require_feature(conn, ident, "contract_1_settings_edit")
            if not changed_template and not changed_general:
                return {"ok": True, "message": "Nội dung hợp đồng không thay đổi.", "settings": current, "revision": revision}
            if body.expected_revision is not None and body.expected_revision != revision:
                raise HTTPException(409, "Cài đặt hợp đồng đã được người khác cập nhật. Vui lòng làm mới rồi lưu lại.")
            saved = {**current, **{key: str(value) for key, value in updates.items()}}
            if not saved["template_content"].strip():
                raise HTTPException(400, "Nội dung mẫu hợp đồng không được để trống.")
            conn.execute(text("""
                INSERT INTO vera_app_setting(
                    category, setting_key, value_json, source, updated_by,
                    revision, created_at, updated_at
                ) VALUES (
                    :category, :setting_key, CAST(:value_json AS jsonb), 'web_v2', :updated_by,
                    1, NOW(), NOW()
                )
                ON CONFLICT (category, setting_key) DO UPDATE SET
                    value_json=EXCLUDED.value_json,
                    source='web_v2',
                    updated_by=EXCLUDED.updated_by,
                    revision=vera_app_setting.revision+1,
                    updated_at=NOW()
            """), {
                "category": SETTING_CATEGORY,
                "setting_key": config["setting_key"],
                "value_json": json.dumps(saved, ensure_ascii=False),
                "updated_by": str(getattr(ident, "employee_username", "") or ""),
            })
            return {
                "ok": True,
                "message": f"Đã lưu nội dung và cài đặt {config['label']}.",
                "contract_type": body.contract_type,
                "settings": saved,
                "revision": revision + 1,
            }

    @app.post("/v2/contracts/1/export.pdf")
    def export_contract_1_pdf(body: ContractExportRequest, ident: identity_type = Depends(current_identity)):
        config = _contract_config(body.contract_type)
        eligible_roles = tuple(config["roles"])
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "contract_1_view")
            can_bulk = feature_allowed(conn, ident, "contract_1_export_bulk")
            if body.scope in {"selected", "individual"}:
                requested_usernames = body.usernames or ([body.username] if body.username else [])
                if not requested_usernames:
                    requested_usernames = [str(getattr(ident, "employee_username", "") or "")]
                requested_keys = {norm(item) for item in requested_usernames if norm(item)}
                own_key = norm(getattr(ident, "employee_username", ""))
                if requested_keys == {own_key}:
                    require_feature(conn, ident, "contract_1_export_self")
                elif not can_bulk:
                    raise HTTPException(403, "Bạn chỉ được xuất hợp đồng của chính mình.")
                else:
                    require_feature(conn, ident, "contract_1_export_bulk")
            else:
                require_feature(conn, ident, "contract_1_export_bulk")

            rows = _eligible_employee_rows(conn, eligible_roles)
            if body.scope in {"selected", "individual"}:
                requested_usernames = body.usernames or ([body.username] if body.username else [])
                if not requested_usernames:
                    requested_usernames = [str(getattr(ident, "employee_username", "") or "")]
                requested_keys = {norm(item) for item in requested_usernames if norm(item)}
                rows = [row for row in rows if norm(row.get("username")) in requested_keys]
            elif body.scope == "department":
                if body.role not in eligible_roles:
                    role_names = " hoặc ".join(ROLE_LABELS[role] for role in eligible_roles)
                    raise HTTPException(400, f"Vui lòng chọn bộ phận {role_names}.")
                rows = [row for row in rows if str(row.get("role") or "").lower() == body.role]
            if not rows:
                raise HTTPException(404, "Không có nhân viên phù hợp để xuất hợp đồng.")

            settings, _revision = _settings(conn, body.contract_type)
            employees = [_contract_employee(conn, row) for row in rows]
            _ensure_complete_contract_profiles(employees)
            content = _merge_contract_pdfs(
                [(employee, settings) for employee in employees],
                body.contract_type,
            )

        file_slug = config["file_slug"]
        if len(employees) == 1:
            safe = re.sub(r"[^\w.-]+", "_", employees[0]["employee_name"], flags=re.UNICODE).strip("_") or "Nhan_Vien"
            filename = f"{file_slug}_{safe}.pdf"
        elif body.scope == "department":
            filename = f"{file_slug}_{ROLE_LABELS.get(body.role or '', body.role or 'Bo_Phan')}_{len(employees)}.pdf"
        else:
            filename = f"{file_slug}_Da_Chon_{len(employees)}.pdf" if body.scope in {"selected", "individual"} else f"{file_slug}_Tat_Ca_{len(employees)}.pdf"
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                "Cache-Control": "private, no-store, max-age=0",
                "X-Content-Type-Options": "nosniff",
                "X-Contract-Count": str(len(employees)),
            },
        )

    app.state.contract_1_routes_installed = True
    app.state.contract_1_release = CONTRACT_RELEASE


__all__ = [
    "CONTRACT_TYPE_CONFIGS", "DEFAULT_SETTINGS", "DEFAULT_TEMPLATE_CONTENT",
    "LE_TAN_TEMPLATE_CONTENT", "LOCKER_TEMPLATE_CONTENT", "QUAN_LY_TEMPLATE_CONTENT",
    "TAP_VU_TEMPLATE_CONTENT", "_contract_pdf", "_merge_contract_pdfs",
    "_missing_contract_fields", "_ensure_complete_contract_profiles",
    "install_contract_1_routes",
]
