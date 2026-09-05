"""Web V2 -> TourVera leave synchronization with VBA-compatible rules.

The target is a macro-enabled workbook.  We edit worksheet XML directly so the
VBA project, form controls, drawings, external links and every unrelated part
of TourVera.xlsm remain byte-for-byte unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import cmp_to_key
from hashlib import sha256
from io import BytesIO
import json
import os
import posixpath
import re
import unicodedata
from typing import Any, Callable, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from google.auth.transport.requests import AuthorizedSession
from fastapi import Depends, HTTPException
from lxml import etree
from openpyxl.formula.translate import Translator
from pydantic import BaseModel
from sqlalchemy import text

from vera_google_credentials import google_credentials


RELEASE = "tour-leave-sync-2026-09-02.2-cp-only"
TOUR_FILE_ID = (
    os.getenv("VERA_TOUR_FILE_ID", "15nDSicFhEHstxQjGrETuSK8Z7q6cSQyS")
    or "15nDSicFhEHstxQjGrETuSK8Z7q6cSQyS"
).strip()
TOUR_MIME = "application/vnd.ms-excel.sheet.macroenabled.12"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
SOURCE_SHEET = "MainData"
CATALOG_SHEET = "LoaiNghi"
INPUT_SHEET = "Input"
REFERENCE_SHEET = "Nghi"

SOURCE_ACTIONS = {"sync_all", "clear_leave_status", "update_reasons"}
ACTION_LABELS = {
    "sync_all": "Đồng bộ lịch nghỉ hôm nay",
    "clear_leave_status": "Kiểm tra/Xóa trạng thái Nghỉ phép",
    "update_reasons": "Chỉ cập nhật Lịch hẹn (cột C)",
    "late_to_working": "Đi trễ → Đi làm",
    "late_to_leave": "Đi trễ → Nghỉ phép",
    "early_to_leave": "Về sớm → Nghỉ phép",
    "early_to_working": "Về sớm → Đi làm",
    "leave_group_to_leave": "Nhóm nghỉ → Nghỉ phép",
    "support_to_working": "Hỗ trợ → Đi làm",
}
TourAction = Literal[
    "sync_all",
    "clear_leave_status",
    "update_reasons",
    "late_to_working",
    "late_to_leave",
    "early_to_leave",
    "early_to_working",
    "leave_group_to_leave",
    "support_to_working",
]


class TourLeaveSyncRequest(BaseModel):
    action: TourAction


def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).replace("\xa0", " ")
    value = "".join(ch for ch in value if ord(ch) >= 32)
    return value.strip()


def _vn_key(value: Any) -> str:
    raw = unicodedata.normalize("NFD", _clean(value).lower())
    return "".join(ch for ch in raw if unicodedata.category(ch) != "Mn").replace("đ", "d")


def _employee_key(value: Any) -> str:
    raw = _clean(value)
    if raw.endswith("*"):
        raw = raw[:-1].strip()
    return raw.lower()


def _same_date(value: Any, target: date) -> bool:
    if isinstance(value, datetime):
        return value.date() == target
    if isinstance(value, date):
        return value == target
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date() == target
        except (OverflowError, TypeError, ValueError):
            return False
    raw = _clean(value).replace("-", "/").replace(".", "/")
    parts = raw.split("/")
    if len(parts) != 3:
        return False
    try:
        if len(parts[0].strip()) == 4:
            year, month, day = (int(part.strip()) for part in parts)
        else:
            day, month, year = (int(part.strip()) for part in parts)
        return date(year, month, day) == target
    except (TypeError, ValueError):
        return False


def _convert_reason(value: Any) -> str:
    raw = _clean(value)
    key = _vn_key(raw)
    mapping = {
        "nghi co phep": "Nghi phep",
        "nghi cuoi tuan co phep": "Nghi phep",
        "nghi phep": "Nghi phep",
        "nghi khong phep": "Nghi khong phep",
        "nghi cuoi tuan khong phep": "Nghi khong phep CUOI TUAN",
        "nghi khong phep cuoi tuan": "Nghi khong phep CUOI TUAN",
        "nghi phat sinh": "Nghi phat sinh",
        "nghi phep nam": "PHEP NAM",
        "phep nam": "PHEP NAM",
        "di tre co phep": "Di tre CP",
        "di tre cuoi tuan co phep": "Di tre CP",
        "di tre cp": "Di tre CP",
        "di tre khong phep": "Di tre khong phep",
        "di tre cuoi tuan khong phep": "Di tre khong phep CUOI TUAN",
        "di tre khong phep cuoi tuan": "Di tre khong phep CUOI TUAN",
        "di tre phat sinh": "Di tre phat sinh",
        "ve som co phep": "Ve som CP",
        "ve som cuoi tuan co phep": "Ve som CP",
        "ve som cp": "Ve som CP",
        "ve som khong phep": "Ve som khong phep",
        "ve som cuoi tuan khong phep": "Ve som khong phep CUOI TUAN",
        "ve som khong phep cuoi tuan": "Ve som khong phep CUOI TUAN",
        "ve som phat sinh": "Ve som phat sinh",
        "ho tro ca 1 sau 23h di tre 2 tieng": "Ho tro Ca 1 di tre 2 tieng",
        "ho tro ca 1 di tre 2 tieng": "Ho tro Ca 1 di tre 2 tieng",
        "ho tro ca 1 di tre 3 tieng": "Ho tro Ca 1 di tre 3 tieng",
    }
    return mapping.get(key, raw)


def _should_use_leave_status(reason: Any) -> bool:
    return _vn_key(reason) in {
        "nghi co phep",
        "nghi cuoi tuan co phep",
        "nghi phep",
        "nghi khong phep",
        "nghi cuoi tuan khong phep",
        "nghi khong phep cuoi tuan",
        "nghi phat sinh",
        "nghi benh co giay kham hoac duoc quan ly duyet",
        "nghi dam hieu",
        "leader nghi phep theo chinh sach",
        "nghi phep nam",
        "phep nam",
        "nghi phep quay video",
    }


def _canonical_reason(catalog: list[tuple[str, str]], raw_reason: Any) -> str:
    wanted = _clean(raw_reason)
    if not wanted:
        return ""
    key = _vn_key(wanted)
    for candidate, _reason_type in catalog:
        if candidate and _vn_key(candidate) == key:
            return candidate
    return wanted


def _reason_type(catalog: list[tuple[str, str]], raw_reason: Any) -> str:
    wanted = _clean(raw_reason)
    key = _vn_key(wanted)
    if not key:
        return ""
    for candidate, reason_type in catalog:
        if candidate and _vn_key(candidate) == key:
            return _clean(reason_type)
    if key in {
        "nghi phep", "nghi co phep", "nghi cuoi tuan co phep",
        "di tre co phep", "di tre cuoi tuan co phep", "di tre cp",
        "ve som co phep", "ve som cuoi tuan co phep", "ve som cp",
    }:
        return "Co phep"
    if key in {
        "nghi khong phep", "nghi cuoi tuan khong phep", "nghi khong phep cuoi tuan",
        "di tre khong phep", "di tre cuoi tuan khong phep", "di tre khong phep cuoi tuan",
        "ve som khong phep", "ve som cuoi tuan khong phep", "ve som khong phep cuoi tuan",
    }:
        return "Khong phep"
    return ""


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"x": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS, "ct": CONTENT_NS}
CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _column_number(ref: str) -> int:
    match = CELL_REF.match(ref)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - 64
    return number


def _column_letter(number: int) -> str:
    output = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        output = chr(65 + remainder) + output
    return output


class _TourWorkbook:
    def __init__(self, payload: bytes):
        self.original = payload
        self.entries: list[tuple[Any, bytes]] = []
        self.parts: dict[str, bytes] = {}
        with ZipFile(BytesIO(payload), "r") as archive:
            for info in archive.infolist():
                data = archive.read(info.filename)
                self.entries.append((info, data))
                self.parts[info.filename] = data
        if "xl/vbaProject.bin" not in self.parts:
            raise HTTPException(503, "TourVera không còn dự án VBA; dừng cập nhật để bảo vệ file.")

        self.workbook_root = etree.fromstring(self.parts["xl/workbook.xml"])
        self.workbook_rels_root = etree.fromstring(self.parts["xl/_rels/workbook.xml.rels"])
        self.input_path = self._sheet_path(INPUT_SHEET)
        self.reference_path = self._sheet_path(REFERENCE_SHEET)
        self.input_root = etree.fromstring(self.parts[self.input_path])
        self.reference_root = etree.fromstring(self.parts[self.reference_path])
        self.shared_strings = self._read_shared_strings()
        self.changed = False
        self.sorted = False
        self._validate_structure()

    def _sheet_path(self, title: str) -> str:
        sheet = self.workbook_root.xpath(
            ".//x:sheets/x:sheet[@name=$title]", namespaces=NS, title=title
        )
        if not sheet:
            raise HTTPException(503, f"TourVera không có sheet '{title}'.")
        relation_id = sheet[0].get(f"{{{REL_NS}}}id")
        relation = self.workbook_rels_root.xpath(
            ".//p:Relationship[@Id=$relation_id]",
            namespaces=NS,
            relation_id=relation_id,
        )
        if not relation:
            raise HTTPException(503, f"TourVera không ánh xạ được sheet '{title}'.")
        raw_target = str(relation[0].get("Target") or "")
        target = raw_target.lstrip("/")
        if raw_target.startswith("/") or target.startswith("xl/"):
            return posixpath.normpath(target)
        return posixpath.normpath(posixpath.join("xl", target))

    def _read_shared_strings(self) -> list[str]:
        raw = self.parts.get("xl/sharedStrings.xml")
        if not raw:
            return []
        root = etree.fromstring(raw)
        return ["".join(item.itertext()) for item in root.xpath(".//x:si", namespaces=NS)]

    @staticmethod
    def _row(root, row_number: int, create: bool = False):
        rows = root.xpath(
            ".//x:sheetData/x:row[@r=$row]", namespaces=NS, row=str(row_number)
        )
        if rows or not create:
            return rows[0] if rows else None
        sheet_data = root.xpath(".//x:sheetData", namespaces=NS)[0]
        row = etree.Element(f"{{{MAIN_NS}}}row", r=str(row_number))
        inserted = False
        for index, existing in enumerate(sheet_data):
            if int(existing.get("r") or 0) > row_number:
                sheet_data.insert(index, row)
                inserted = True
                break
        if not inserted:
            sheet_data.append(row)
        return row

    @staticmethod
    def _cell(root, row_number: int, column: int, create: bool = False):
        row = _TourWorkbook._row(root, row_number, create=create)
        if row is None:
            return None
        ref = f"{_column_letter(column)}{row_number}"
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            if cell.get("r") == ref:
                return cell
        if not create:
            return None
        cell = etree.Element(f"{{{MAIN_NS}}}c", r=ref)
        inserted = False
        for index, existing in enumerate(row):
            if existing.tag == f"{{{MAIN_NS}}}c" and _column_number(existing.get("r") or "") > column:
                row.insert(index, cell)
                inserted = True
                break
        if not inserted:
            row.append(cell)
        return cell

    def _value(self, root, row_number: int, column: int) -> str:
        cell = self._cell(root, row_number, column)
        if cell is None:
            return ""
        if cell.get("t") == "inlineStr":
            return "".join(cell.itertext())
        value = cell.find(f"{{{MAIN_NS}}}v")
        raw = value.text if value is not None and value.text is not None else ""
        if cell.get("t") == "s":
            try:
                return self.shared_strings[int(raw)]
            except (ValueError, IndexError):
                return ""
        if cell.get("t") == "b":
            return "TRUE" if raw == "1" else "FALSE"
        return raw

    def input_value(self, row: int, column: int) -> str:
        return self._value(self.input_root, row, column)

    def _validate_structure(self) -> None:
        expected = {2: "ten nhan vien", 3: "lich hen", 16: "di lam"}
        for column, wanted in expected.items():
            if _vn_key(self.input_value(20, column)) != wanted:
                raise HTTPException(
                    503,
                    "Cấu trúc TourVera/Input đã thay đổi; yêu cầu B=Tên nhân viên, C=Lịch hẹn, P=Đi làm.",
                )

    def last_input_row(self) -> int:
        last = 20
        for row in self.input_root.xpath(".//x:sheetData/x:row", namespaces=NS):
            number = int(row.get("r") or 0)
            if number >= 21 and _clean(self.input_value(number, 2)):
                last = max(last, number)
        return last

    def set_input_text(self, row: int, column: int, value: str) -> bool:
        # Web V2 is only allowed to write TourVera/Input:
        # C = Ly do nghi, P = Di lam / Nghi phep.
        if column not in {3, 16}:
            raise HTTPException(
                503,
                f"Tu choi ghi TourVera cot {_column_letter(column)}; Web V2 chi duoc ghi cot C va P.",
            )
        if _clean(self.input_value(row, column)) == _clean(value):
            return False
        cell = self._cell(self.input_root, row, column, create=True)
        for child in list(cell):
            if child.tag in {
                f"{{{MAIN_NS}}}f", f"{{{MAIN_NS}}}v", f"{{{MAIN_NS}}}is"
            }:
                cell.remove(child)
        cell.set("t", "inlineStr")
        inline = etree.SubElement(cell, f"{{{MAIN_NS}}}is")
        text_node = etree.SubElement(inline, f"{{{MAIN_NS}}}t")
        if value != value.strip() or "  " in value:
            text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        text_node.text = value
        self.changed = True
        return True

    def _clear_input_contents(self, row: int, column: int) -> None:
        cell = self._cell(self.input_root, row, column)
        if cell is None:
            return
        for child in list(cell):
            if child.tag in {
                f"{{{MAIN_NS}}}f", f"{{{MAIN_NS}}}v", f"{{{MAIN_NS}}}is"
            }:
                cell.remove(child)
        cell.attrib.pop("t", None)
        self.changed = True

    def reference_lists(self) -> dict[int, list[str]]:
        output: dict[int, list[str]] = {}
        for column in (2, 8, 11, 14, 17):
            values = []
            rows = self.reference_root.xpath(".//x:sheetData/x:row", namespaces=NS)
            last = max((int(row.get("r") or 0) for row in rows), default=1)
            for row in range(2, last + 1):
                value = _clean(self._value(self.reference_root, row, column))
                if value:
                    values.append(value)
            output[column] = values
        return output

    def resolve_reason(self, source_reason: str) -> str:
        source_reason = _clean(source_reason)
        source_key = _convert_reason(source_reason) or source_reason
        for values in self.reference_lists().values():
            for candidate in values:
                if _vn_key(candidate) == _vn_key(source_reason):
                    return candidate
                candidate_key = _convert_reason(candidate) or candidate
                if candidate_key.lower() == source_key.lower():
                    return candidate
        return _convert_reason(source_reason) or source_reason

    def _sort_value(self, row: int, column: int):
        raw = _clean(self.input_value(row, column))
        if not raw:
            return (2, "")
        try:
            return (0, float(raw))
        except ValueError:
            return (1, raw.lower())

    def _move_range(self, rows_in_order: list[int], start_column: int, end_column: int) -> None:
        target_rows = list(range(21, 21 + len(rows_in_order)))
        snapshots: dict[int, list[Any]] = {}
        for source_row in target_rows:
            row = self._row(self.input_root, source_row)
            snapshots[source_row] = [
                deepcopy(cell)
                for cell in (row.findall(f"{{{MAIN_NS}}}c") if row is not None else [])
                if start_column <= _column_number(cell.get("r") or "") <= end_column
            ]

        for target_row in target_rows:
            row = self._row(self.input_root, target_row, create=True)
            for cell in list(row.findall(f"{{{MAIN_NS}}}c")):
                if start_column <= _column_number(cell.get("r") or "") <= end_column:
                    row.remove(cell)

        for target_row, source_row in zip(target_rows, rows_in_order):
            row = self._row(self.input_root, target_row, create=True)
            for cell in snapshots[source_row]:
                old_ref = str(cell.get("r") or "")
                column = _column_number(old_ref)
                new_ref = f"{_column_letter(column)}{target_row}"
                cell.set("r", new_ref)
                formula = cell.find(f"{{{MAIN_NS}}}f")
                if formula is not None and formula.text:
                    try:
                        translated = Translator(
                            f"={formula.text}", origin=old_ref
                        ).translate_formula(new_ref)
                        formula.text = translated[1:] if translated.startswith("=") else translated
                    except Exception:
                        pass
                row.append(cell)
            cells = list(row.findall(f"{{{MAIN_NS}}}c"))
            for cell in cells:
                row.remove(cell)
            for cell in sorted(cells, key=lambda item: _column_number(item.get("r") or "")):
                row.append(cell)
        self.changed = True

    def sort_like_vba(self, preliminary_status_descending: bool = False) -> None:
        last = self.last_input_row()
        if last < 21:
            return
        rows = list(range(21, last + 1))
        for row_number in rows:
            row = self._row(self.input_root, row_number)
            if row is not None:
                row.attrib.pop("hidden", None)

        if preliminary_status_descending:
            def compare_status(left: int, right: int) -> int:
                a = _clean(self.input_value(left, 16)).lower()
                b = _clean(self.input_value(right, 16)).lower()
                if not a and not b:
                    return 0
                if not a:
                    return 1
                if not b:
                    return -1
                return -1 if a > b else (1 if a < b else 0)

            preliminary = sorted(rows, key=cmp_to_key(compare_status))
            self._move_range(preliminary, 1, 24)

        def final_key(row: int):
            status = _clean(self.input_value(row, 16)).lower()
            if status == "di lam":
                status_key = (0, "")
            elif status == "nghi phep":
                status_key = (1, "")
            else:
                status_key = (2, status)
            return status_key + self._sort_value(row, 9)

        final_order = sorted(rows, key=final_key)
        self._move_range(final_order, 2, 24)
        self.sorted = True

        # Exact threshold from XoaDongNeuKBeHonTru3 in TourVera's VBA.
        for row in rows:
            cell = self._cell(self.input_root, row, 11)
            value_node = cell.find(f"{{{MAIN_NS}}}v") if cell is not None else None
            try:
                value = float(value_node.text) if value_node is not None else None
            except (TypeError, ValueError):
                value = None
            if value is not None and value < -300000:
                for column in range(4, 9):
                    self._clear_input_contents(row, column)
                self._clear_input_contents(row, 11)

    def values_in_reference_column(self, column: int) -> set[str]:
        return {_clean(value) for value in self.reference_lists().get(column, []) if _clean(value)}

    def _prepare_full_recalculation(self) -> None:
        calc_pr = self.workbook_root.find(f"{{{MAIN_NS}}}calcPr")
        if calc_pr is None:
            calc_pr = etree.SubElement(self.workbook_root, f"{{{MAIN_NS}}}calcPr")
        calc_pr.set("calcMode", "auto")
        calc_pr.set("fullCalcOnLoad", "1")
        calc_pr.set("forceFullCalc", "1")

        for relation in list(self.workbook_rels_root):
            if str(relation.get("Type") or "").endswith("/calcChain"):
                self.workbook_rels_root.remove(relation)
        content_root = etree.fromstring(self.parts["[Content_Types].xml"])
        for override in list(content_root):
            if override.get("PartName") == "/xl/calcChain.xml":
                content_root.remove(override)
        self.parts["[Content_Types].xml"] = etree.tostring(
            content_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        self.parts.pop("xl/calcChain.xml", None)

    def to_bytes(self) -> bytes:
        self.parts[self.input_path] = etree.tostring(
            self.input_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        if self.sorted:
            self._prepare_full_recalculation()
        self.parts["xl/workbook.xml"] = etree.tostring(
            self.workbook_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        self.parts["xl/_rels/workbook.xml.rels"] = etree.tostring(
            self.workbook_rels_root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
            written = set()
            for info, original_data in self.entries:
                if info.filename not in self.parts:
                    continue
                archive.writestr(info, self.parts.get(info.filename, original_data))
                written.add(info.filename)
            for name, data in self.parts.items():
                if name not in written:
                    archive.writestr(name, data)
        return output.getvalue()


def _sheet_rows(worksheet, range_name: str) -> list[list[Any]]:
    values = worksheet.get(range_name, value_render_option="FORMATTED_VALUE")
    if isinstance(values, dict):
        values = values.get("values", [])
    return [list(row) for row in (values or [])]


def _load_source(google_client: Callable[[], Any], sheet_id: str):
    try:
        spreadsheet = google_client().open_by_key(sheet_id)
        main_rows = _sheet_rows(spreadsheet.worksheet(SOURCE_SHEET), "A:D")
        catalog_rows = _sheet_rows(spreadsheet.worksheet(CATALOG_SHEET), "B:C")
    except Exception as exc:
        raise HTTPException(
            503, f"Không đọc được LichNghi_VeraSpa: {type(exc).__name__}: {str(exc)[:240]}"
        ) from exc
    if not main_rows or [_vn_key(value) for value in (main_rows[0] + [""] * 4)[:4]] != [
        "ngay", "thu ngay", "ten nhan vien", "ly do nghi"
    ]:
        raise HTTPException(503, "MainData phải có A=Ngày, B=Thứ ngày, C=Tên nhân viên, D=Lý do nghỉ.")
    if not catalog_rows or [_vn_key(value) for value in (catalog_rows[0] + [""] * 2)[:2]] != [
        "ly do nghi", "loai nghi"
    ]:
        raise HTTPException(503, "LoaiNghi phải có B=Lý do nghỉ và C=Loại nghỉ.")
    catalog = [
        (_clean((row + [""] * 2)[0]), _clean((row + [""] * 2)[1]))
        for row in catalog_rows[1:]
    ]
    return main_rows[1:], catalog


def _today_reasons(
    source_rows: list[list[Any]],
    catalog: list[tuple[str, str]],
    editor: _TourWorkbook,
    target_date: date,
):
    totals = {"source_total": 0, "source_permit": 0, "source_no_permit": 0}
    reasons: dict[str, str] = {}
    for raw_row in source_rows:
        row = (raw_row + [""] * 4)[:4]
        if not _same_date(row[0], target_date):
            continue
        totals["source_total"] += 1
        reason_type = _reason_type(catalog, row[3])
        if _vn_key(reason_type) == "co phep":
            totals["source_permit"] += 1
        elif _vn_key(reason_type) == "khong phep":
            totals["source_no_permit"] += 1
        employee = _employee_key(row[2])
        canonical = _canonical_reason(catalog, row[3])
        if employee and canonical and employee not in reasons:
            reasons[employee] = editor.resolve_reason(canonical)
    totals["source_special"] = (
        totals["source_total"] - totals["source_permit"] - totals["source_no_permit"]
    )
    return reasons, totals


def _apply_action(
    editor: _TourWorkbook,
    action: TourAction,
    target_date: date,
    source_rows: list[list[Any]] | None = None,
    catalog: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "matched": 0,
        "reason_updated": 0,
        "status_updated": 0,
    }
    last_row = editor.last_input_row()

    if action in SOURCE_ACTIONS:
        reasons, totals = _today_reasons(
            source_rows or [], catalog or [], editor, target_date
        )
        stats.update(totals)
        for row in range(21, last_row + 1):
            employee = _employee_key(editor.input_value(row, 2))
            reason = reasons.get(employee, "") if employee else ""
            current_status = _clean(editor.input_value(row, 16))

            if action == "clear_leave_status":
                if current_status.lower() != "nghi phep":
                    continue
                if not reason:
                    if editor.set_input_text(row, 16, "Di lam"):
                        stats["status_updated"] += 1
                    continue
                stats["matched"] += 1
                if not _should_use_leave_status(reason):
                    if editor.set_input_text(row, 16, "Di lam"):
                        stats["status_updated"] += 1
                if editor.set_input_text(row, 3, reason):
                    stats["reason_updated"] += 1
                continue

            if not reason:
                continue
            stats["matched"] += 1
            if editor.set_input_text(row, 3, reason):
                stats["reason_updated"] += 1
            if action == "sync_all" and _should_use_leave_status(reason):
                if current_status.lower() != "nghi phep" and editor.set_input_text(row, 16, "Nghi phep"):
                    stats["status_updated"] += 1

        # Không sort/move dữ liệu TourVera.
        # Web V2 chỉ được thay đổi trực tiếp cột C và P.
        return stats

    mapping = {
        "late_to_working": (8, "Di lam"),
        "late_to_leave": (8, "Nghi phep"),
        "early_to_leave": (11, "Nghi phep"),
        "early_to_working": (11, "Di lam"),
        "support_to_working": (14, "Di lam"),
    }
    if action == "leave_group_to_leave":
        for row in range(21, last_row + 1):
            reason = _clean(editor.input_value(row, 3))
            if reason and _should_use_leave_status(reason):
                stats["matched"] += 1
                if editor.set_input_text(row, 16, "Nghi phep"):
                    stats["status_updated"] += 1
        return stats

    reference_column, status = mapping[action]
    accepted = editor.values_in_reference_column(reference_column)
    for row in range(21, last_row + 1):
        reason = _clean(editor.input_value(row, 3))
        # Application.Match in the VBA is case-insensitive but otherwise exact.
        if reason and any(reason.lower() == item.lower() for item in accepted):
            stats["matched"] += 1
            if editor.set_input_text(row, 16, status):
                stats["status_updated"] += 1
    return stats


def _drive_session() -> AuthorizedSession:
    return AuthorizedSession(google_credentials([DRIVE_SCOPE]))


def _download_tour(session: AuthorizedSession) -> tuple[bytes, str]:
    response = session.get(
        f"https://www.googleapis.com/drive/v3/files/{TOUR_FILE_ID}"
        "?alt=media&supportsAllDrives=true",
        timeout=90,
    )
    if response.status_code != 200:
        raise HTTPException(503, f"Không tải được TourVera (Drive HTTP {response.status_code}).")
    payload = bytes(response.content or b"")
    etag = str(response.headers.get("ETag") or response.headers.get("etag") or "").strip()
    if not payload:
        raise HTTPException(503, "Google Drive trả về TourVera rỗng.")
    if not etag:
        raise HTTPException(503, "Google Drive không trả ETag; dừng để tránh ghi đè TourVera.")
    return payload, etag


def _upload_and_verify(session: AuthorizedSession, payload: bytes, etag: str) -> dict[str, Any]:
    response = session.patch(
        f"https://www.googleapis.com/upload/drive/v3/files/{TOUR_FILE_ID}"
        "?uploadType=media&supportsAllDrives=true&fields=id,name,mimeType,modifiedTime,size,md5Checksum",
        headers={"Content-Type": TOUR_MIME, "If-Match": etag},
        data=payload,
        timeout=120,
    )
    if response.status_code in {409, 412}:
        raise HTTPException(409, "TourVera vừa được thay đổi ở nơi khác. Hãy bấm lại để dùng bản mới nhất.")
    if response.status_code not in {200, 201}:
        detail = str(response.text or "")[:240]
        raise HTTPException(
            503, f"Không ghi được TourVera (Drive HTTP {response.status_code}): {detail}"
        )
    verify = session.get(
        f"https://www.googleapis.com/drive/v3/files/{TOUR_FILE_ID}"
        "?alt=media&supportsAllDrives=true",
        timeout=90,
    )
    if verify.status_code != 200 or sha256(bytes(verify.content or b"")).digest() != sha256(payload).digest():
        raise HTTPException(503, "Đã gửi TourVera nhưng không xác minh được nội dung sau khi ghi.")
    try:
        return dict(response.json() or {})
    except Exception:
        return {}


def install_tour_leave_sync_routes(
    app,
    *,
    engine_instance: Callable[[], Any],
    current_identity,
    require_feature: Callable[..., Any],
    identity_type,
    google_client: Callable[[], Any],
    leave_sheet_id: str,
    vn_tz,
    invalidate_tour_cache: Callable[[], None] | None = None,
) -> None:
    if getattr(app.state, "tour_leave_sync_installed", False):
        return

    @app.get("/v2/tour-leave-sync/health")
    def tour_leave_sync_health():
        return {
            "ok": True,
            "release": RELEASE,
            "source_sheet": SOURCE_SHEET,
            "catalog_sheet": CATALOG_SHEET,
            "target_file": "TourVera.xlsm",
            "preserves_vba": True,
            "concurrency_guard": "drive-etag",
        }

    @app.post("/v2/tour-leave-sync")
    def tour_leave_sync(
        body: TourLeaveSyncRequest,
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            require_feature(conn, ident, "tour_leave_sync")
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:v2:tour_leave_sync'))"))

            source_rows = catalog = None
            if body.action in SOURCE_ACTIONS:
                source_rows, catalog = _load_source(google_client, leave_sheet_id)

            try:
                session = _drive_session()
                original, etag = _download_tour(session)
                editor = _TourWorkbook(original)
                target_date = datetime.now(vn_tz).date()
                stats = _apply_action(
                    editor,
                    body.action,
                    target_date,
                    source_rows=source_rows,
                    catalog=catalog,
                )
                updated = editor.to_bytes()
                metadata = _upload_and_verify(session, updated, etag)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    503, f"Không cập nhật được TourVera: {type(exc).__name__}: {str(exc)[:300]}"
                ) from exc

        if invalidate_tour_cache is not None:
            invalidate_tour_cache()
        changed_count = int(stats.get("reason_updated") or 0) + int(stats.get("status_updated") or 0)
        return {
            "ok": True,
            "release": RELEASE,
            "action": body.action,
            "action_label": ACTION_LABELS[body.action],
            "date": target_date.isoformat(),
            "message": (
                f"Đã chạy {ACTION_LABELS[body.action]} cho ngày {target_date.strftime('%d/%m/%Y')}. "
                f"Thay đổi {changed_count} ô trong TourVera."
            ),
            "stats": stats,
            "target": {
                "name": str(metadata.get("name") or "TourVera.xlsm"),
                "modified_time": str(metadata.get("modifiedTime") or ""),
                "verified": True,
            },
        }

    app.state.tour_leave_sync_installed = True
    app.state.tour_leave_sync_release = RELEASE
