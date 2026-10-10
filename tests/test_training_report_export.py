"""Real rendering regressions for the complete training-report export."""
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
import math

from PIL import Image
from pypdf import PdfReader
import pytest

import vera_web_v2_training_report_export as export


def synthetic_report(long_notes=False):
    note = ("Kỹ thuật viên cần luyện tập thao tác đúng quy trình, giữ vệ sinh và giao tiếp nhẹ nhàng. " * 95 if long_notes else "Đã thực hành đúng kỹ thuật, cần giữ nhịp ổn định.")
    progress = []
    for index, grade in enumerate(("C", "B", "A")):
        progress.append({
            "id": f"training-{index}", "training_date": date(2026, 10, index + 1),
            "start_time": "09:00:00", "end_time": "10:30:00", "topic": f"Buổi thực hành {index + 1}: Chăm sóc và phục hồi",
            "skill_grade": grade, "skill_score": index + 3, "learning_attitude": "Tốt",
            "trainer_username": "leader01", "evaluator_name": "Nguyễn Thị Hương", "evaluator_role": "leader",
            "strengths": "Lắng nghe và tiếp thu góp ý tốt.", "improvements": "Luyện đều tay ở vùng vai gáy.",
            "notes": note + (" TAIL_JOURNAL_COMPLETE" if index == 2 else ""),
            "status": "completed", "created_at": "2026-10-01T20:30:45Z",
        })
    evaluations = [{"cycle_id": "cycle-1", "cycle_name": "Đợt đánh giá tháng 10", "end_date": date(2026, 10, 5),
                    "craft": 4.5, "communication": 4, "attitude": 5, "conduct": 3.75}]
    detail = {"id": "evaluation-1", "cycle_id": "cycle-1", "cycle_name": "Đợt đánh giá tháng 10",
              "start_date": "2026-10-01", "end_date": "2026-10-05", "evaluator_username": "manager01", "evaluator_name": "Đỗ Ngọc Hà",
              "evaluator_role": "quanly", "status": "submitted", "submitted_at": "2026-10-05T17:30:00+00:00",
              "craft_score": 5, "communication_score": 4, "attitude_score": 5, "discipline_score": 4,
              "appearance_score": 3, "hygiene_score": 5, "attendance_score": None,
              "strengths": "Thao tác chắc chắn, tiến bộ rõ rệt.", "improvements": "Giữ đúng thời gian từng bước.",
              "comments": note + " TAIL_EVALUATION_COMPLETE"}
    history = [{"type": "daily", "date": item["training_date"], "id": item["id"], "title": item["topic"],
                "evaluator_name": item["evaluator_name"], "evaluator_role": "leader", "rating": "good",
                "rating_label": "Tốt", "detail": item} for item in progress]
    history.append({"type": "comprehensive", "date": detail["end_date"], "id": detail["id"],
                    "title": "TAIL_HISTORY_COMPLETE", "evaluator_name": detail["evaluator_name"],
                    "evaluator_role": "quanly", "rating": "excellent", "rating_label": "Xuất sắc", "detail": detail})
    return {"employee_username": "ktv01", "employee": {"username": "ktv01", "full_name": "Trần Thị Thảo",
            "department": "Chăm sóc sức khỏe", "role": "employee"}, "date_from": date(2026, 10, 1),
            "date_to": "2026-10-10", "filters": {"evaluator_role": "all", "rating": "all", "q": ""},
            "progress": progress, "evaluations": evaluations, "latest_radar": evaluations[-1],
            "evaluation_details": [detail], "history": history, "history_total": len(history)}


def _pdf_text(blob):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(blob)).pages)


def _model_text(pages):
    return "\n".join(command[1] for page in pages for command in page if command[0] == "text")


def test_full_pdf_is_a4_embeds_vietnamese_fonts_and_preserves_every_field(tmp_path):
    report = synthetic_report(long_notes=True)
    original = deepcopy(report)
    blob = export.render_training_report(report, "pdf")
    assert report == original
    path = tmp_path / "training-report.pdf"
    path.write_bytes(blob)
    reader = PdfReader(path)
    assert len(reader.pages) >= 6
    text = _pdf_text(blob)
    for marker in ["Trần Thị Thảo", "Nhật ký đào tạo đầy đủ", "Nguyễn Thị Hương", "Đỗ Ngọc Hà",
                   "TAIL_JOURNAL_COMPLETE", "TAIL_EVALUATION_COMPLETE", "TAIL_HISTORY_COMPLETE",
                   "Điểm mạnh", "Cần cải thiện", "Ghi chú", "Nhận xét", "Mã buổi", "Mã phiếu", "Mã đợt",
                   "Ngày bắt đầu đợt: 01-10-2026", "Mức tay nghề: A", "Điểm tay nghề: 5/6", "Thái độ học tập: Tốt", "Chuyên cần: Chưa có",
                   "02-10-2026 03:30:45", "06-10-2026 00:30:00", "01-10-2026 đến 10-10-2026"]:
        assert marker in text
    assert "2026-10-" not in text
    assert "Chuyên cần: 0" not in text
    assert len(text) > 33_000
    embedded_fonts = set()
    for index, page in enumerate(reader.pages, 1):
        assert float(page.mediabox.width) == pytest.approx(export.PAGE_WIDTH, abs=.01)
        assert float(page.mediabox.height) == pytest.approx(export.PAGE_HEIGHT, abs=.01)
        assert f"Trang {index}/{len(reader.pages)}" in page.extract_text()
        for resource in page["/Resources"]["/Font"].values():
            font = resource.get_object()
            if "/FontDescriptor" in font:
                assert "/FontFile2" in font["/FontDescriptor"]
                embedded_fonts.add(str(font["/BaseFont"]))
    assert any("DejaVuSans" in name for name in embedded_fonts)
    assert any("Bold" in name for name in embedded_fonts)


def test_png_renders_same_full_pages_including_trailing_long_records(tmp_path, monkeypatch):
    report = synthetic_report(long_notes=True)
    export._fonts()
    pages = export._build_layout(report)
    captured = []
    original_text = export.ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        captured.append(text)
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(export.ImageDraw.ImageDraw, "text", capture_text)
    blob = export.render_training_report(report, "png")
    path = tmp_path / "training-report.png"
    path.write_bytes(blob)
    with Image.open(path) as image:
        assert image.format == "PNG"
        assert image.size == (math.ceil(export.PAGE_WIDTH * export.PNG_SCALE),
                              len(pages) * math.ceil(export.PAGE_HEIGHT * export.PNG_SCALE))
        assert image.width * image.height <= export.MAX_PNG_PIXELS
        # Check actual pixels in every page, including the final history page.
        for index in range(len(pages)):
            page_height = math.ceil(export.PAGE_HEIGHT * export.PNG_SCALE)
            crop = image.crop((65, index * page_height + 135, image.width - 65, (index + 1) * page_height - 95))
            assert crop.convert("L").getextrema()[0] < 180
    for marker in ("TAIL_JOURNAL_COMPLETE", "TAIL_EVALUATION_COMPLETE", "TAIL_HISTORY_COMPLETE"):
        assert marker in "\n".join(captured)
    assert captured == [command[1] for page in pages for command in page if command[0] == "text"]


def test_png_is_rejected_before_allocating_canvas_and_pdf_remains_available(monkeypatch):
    report = synthetic_report()
    monkeypatch.setattr(export, "MAX_PNG_PIXELS", 1_000_000)
    allocated = []
    monkeypatch.setattr(export.Image, "new", lambda *a, **kw: allocated.append(a))
    with pytest.raises(export.ReportExportTooLarge, match="PDF.*bộ lọc"):
        export.render_training_report(report, "png")
    assert allocated == []
    assert export.render_training_report(report, "pdf").startswith(b"%PDF-")


def test_png_height_is_bounded_even_when_pixel_limit_is_high(monkeypatch):
    monkeypatch.setattr(export, "MAX_PNG_PIXELS", 10**12)
    monkeypatch.setattr(export, "MAX_PNG_HEIGHT", 100)
    with pytest.raises(export.ReportExportTooLarge):
        export.render_training_report(synthetic_report(), "png")


def test_missing_font_is_explicit_instead_of_corrupt_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(export, "FONT_ROOTS", (tmp_path,))
    with pytest.raises(export.ReportExportUnavailable, match="DejaVu"):
        export.render_training_report({}, "pdf")
    with pytest.raises(export.ReportExportUnavailable, match="DejaVu"):
        export.render_training_report({}, "png")


@pytest.mark.parametrize("file_format", ["pdf", "png"])
def test_empty_report_renders_without_fabricated_scores(file_format):
    blob = export.render_training_report({"employee_username": "ktv-empty"}, file_format)
    assert blob
    if file_format == "pdf":
        text = _pdf_text(blob)
        assert "Chưa có" in text
        assert "0/5" not in text and "0/6" not in text
    else:
        with Image.open(BytesIO(blob)) as image:
            image.verify()


def test_shared_layout_wraps_unbroken_and_multiline_text_and_keeps_bounds():
    export._fonts()
    report = synthetic_report()
    report["progress"][-1]["notes"] = "Đoạn đầu.\n\n" + "ABC123" * 220 + " UNBROKEN_END"
    pages = export._build_layout(report)
    assert "UNBROKEN_END" in _model_text(pages)
    for page in pages:
        for command in page:
            if command[0] != "text":
                continue
            _, value, x, y, size, bold, _, anchor = command
            width = export._width(value, size, bold)
            left = x - width if anchor == "right" else x - width / 2 if anchor == "center" else x
            assert left >= export.MARGIN - .5
            assert left + width <= export.PAGE_WIDTH - export.MARGIN + .5
            assert y + size < export.PAGE_HEIGHT - 10


def test_all_chart_records_are_plotted_without_an_arbitrary_limit():
    export._fonts()
    report = synthetic_report()
    report["progress"] = [{**report["progress"][0], "id": f"training-{i}", "notes": "", "skill_score": 2} for i in range(61)]
    report["evaluation_details"] = [{**report["evaluation_details"][0], "id": f"evaluation-{i}", "attendance_score": 5} for i in range(43)]
    layout = export._Layout("test")
    export._line_chart(layout, report["progress"], skill=True)
    export._line_chart(layout, report["evaluation_details"])
    dots = [c for page in layout.pages for c in page if c[0] == "circle"]
    assert len(dots) == 61 + 43 * 7
    assert "Bản ghi 49-61 / 61" in _model_text(layout.pages)
    assert "Bản ghi 37-43 / 43" in _model_text(layout.pages)


def test_missing_scores_create_real_gaps_and_no_zero_dots():
    export._fonts()
    layout = export._Layout("test")
    items = [{"training_date": "2026-10-01", "skill_score": value} for value in (3, None, 4, 0, 5)]
    export._line_chart(layout, items, skill=True)
    dots = [c for page in layout.pages for c in page if c[0] == "circle"]
    green_lines = [c for page in layout.pages for c in page if c[0] == "line" and c[-2] == export.GREEN and c[-1] == 1.6]
    assert len(dots) == 3
    assert not green_lines
    assert export._score(float("nan"), 5) is None
    assert export._score(True, 5) is None
    assert export._score(0, 5) is None


def test_partial_radar_does_not_invent_a_score_or_closed_polygon():
    export._fonts()
    layout = export._Layout("test")
    export._radar(layout, {"cycle_name": "Thiếu điểm", "end_date": "2026-10-01", "craft": 4,
                           "communication": None, "attitude": 3, "conduct": 5})
    assert len([c for c in layout.commands if c[0] == "circle"]) == 3
    assert not [c for c in layout.commands if c[0] == "polygon" and c[2] == export.GREEN]
    assert "Chưa có" in _model_text(layout.pages)


def test_date_and_datetime_display_uses_vietnam_boundary():
    assert export._date(date(2024, 2, 29)) == "29-02-2024"
    assert export._date("2026-10-01T19:00:00Z") == "02-10-2026"
    assert export._datetime(datetime(2026, 10, 1, 19, tzinfo=timezone.utc)) == "02-10-2026 02:00:00 (giờ Việt Nam)"


def test_unsupported_format_fails_before_rendering():
    with pytest.raises(ValueError, match="PDF hoặc PNG"):
        export.render_training_report({}, "jpg")


def test_history_chart_uses_seven_raw_scores_and_separates_cycle_averages():
    export._fonts()
    report = synthetic_report()
    # Contradicting aggregates must not replace the submitted raw scores.
    report["evaluations"][0]["craft"] = 1
    layout = export._Layout("test")
    export._line_chart(layout, report["evaluation_details"])
    text = _model_text(layout.pages)
    for _, label in export.SCORE_FIELDS:
        assert label in text
    assert "Tác phong" not in text
    dots = [c for page in layout.pages for c in page if c[0] == "circle"]
    assert len(dots) == 6  # Seven criteria, one genuinely missing attendance score.
    full_text = _model_text(export._build_layout(report))
    assert "Điểm trung bình tổng hợp theo đợt" in full_text
    assert "Bảy tiêu chí của từng phiếu đã nộp" in full_text
