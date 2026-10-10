"""Reference-card PDF regressions, independent of the unchanged PNG model."""
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import re

from pypdf import PdfReader

import vera_web_v2_training_report_export as export
import vera_web_v2_training_report_pdf as template
from test_training_report_export import synthetic_report, _model_text, _pdf_text


def reference_report():
    progress = []
    for day, start, end, title, trainer, grade, score in (
        (30, "14:45", "16:05", "Test tay nghề", "Mỹ Duyên", "B", 4),
        (23, "13:30", "14:30", "Đào tạo hằng ngày", "Quỳnh Phương", "C", 3),
    ):
        progress.append({"id": day, "training_date": date(2026, 9, day), "start_time": start,
                         "end_time": end, "topic": title, "trainer_username": trainer,
                         "evaluator_name": trainer, "skill_grade": grade, "skill_score": score,
                         "learning_attitude": "Tốt", "strengths": "Chịu khó học" if day == 30 else None,
                         "notes": "Được duyệt qua vip" if day == 30 else None})
    return {"employee": {"full_name": "Thảo Linh"}, "employee_username": "linh",
            "progress": progress, "history": [{"type": "daily", "id": item["id"],
            "date": item["training_date"], "title": item["topic"], "evaluator_name": item["evaluator_name"],
            "rating_label": "Tốt" if item["skill_grade"] == "B" else "Trung bình", "detail": item} for item in progress]}


def assert_bounds(pages):
    for page in pages:
        for command in page:
            kind, *args = command
            if kind == "text":
                value, x, y, size, bold, _, anchor = args
                width = export._width(value, size, bold)
                left = x - width if anchor == "right" else x - width / 2 if anchor == "center" else x
                assert left >= template.MARGIN - .5, command
                assert left + width <= export.PAGE_WIDTH - template.MARGIN + .5, command
                assert y >= template.TOP - .1, command
                assert y + size <= (export.PAGE_HEIGHT - 8 if value.startswith("Trang ") else template.BOTTOM), command
            elif kind in {"rect", "roundrect"}:
                x, y, width, height = args[:4]
                assert x >= template.MARGIN - .5 and x + width <= export.PAGE_WIDTH - template.MARGIN + .5, command
                assert y >= template.TOP - .1 and y + height <= template.BOTTOM + .1, command
            elif kind == "line":
                x1, y1, x2, y2 = args[:4]
                assert min(x1, x2) >= template.MARGIN - .5, command
                assert max(x1, x2) <= export.PAGE_WIDTH - template.MARGIN + .5, command
                assert min(y1, y2) >= template.TOP - .1 and max(y1, y2) <= template.BOTTOM + .1, command
            elif kind == "circle":
                x, y, radius = args[:3]
                assert x - radius >= template.MARGIN and x + radius <= export.PAGE_WIDTH - template.MARGIN, command
                assert y - radius >= template.TOP and y + radius <= template.BOTTOM, command
            elif kind == "polygon":
                assert all(template.MARGIN <= x <= export.PAGE_WIDTH - template.MARGIN and template.TOP <= y <= template.BOTTOM for x, y in args[0]), command


def test_reference_sample_is_one_a4_page_with_card_order_palette_and_display_name():
    report = reference_report()
    export._fonts()
    pages = template.build_pdf_layout(report)
    assert len(pages) == 1
    text = _model_text(pages)
    titles = ("Nhật ký đào tạo · Thảo Linh", "Lịch sử Đào tạo & Đánh giá (2)",
              "Tiến độ kỹ năng", "Năng lực kỳ gần nhất", "Biểu đồ đánh giá")
    assert [text.index(title) for title in titles] == sorted(text.index(title) for title in titles)
    assert "2 ngày · 2 buổi · 2,33 giờ" in text
    assert "14:45-16:05 · 1,33 giờ" in text
    assert "Chưa có đủ dữ liệu năng lực trong khoảng đã chọn." in text
    assert "Chưa có đợt đánh giá tổng hợp trong khoảng đã chọn." in text
    assert len([c for c in pages[0] if c[0] == "roundrect" and c[-2] == "#ffffff"]) == 5
    assert len([c for c in pages[0] if c[0] == "roundrect" and c[-2] == template.HISTORY_BLUE]) == 2
    assert len([c for c in pages[0] if c[0] == "rect" and c[-1] == template.GOLD_WASH]) == 4
    assert_bounds(pages)
    reader = PdfReader(BytesIO(export.render_training_report(report, "pdf")))
    assert len(reader.pages) == 1


def test_full_notes_reflow_in_table_and_history_without_clipping_or_mutation():
    report = synthetic_report(long_notes=True)
    report["progress"][0]["notes"] += "\n\n" + "ABC123" * 220 + " UNBROKEN_END"
    original = deepcopy(report)
    export._fonts()
    pages = template.build_pdf_layout(report)
    assert report == original
    text = _model_text(pages)
    assert len(pages) > 6
    for marker in ("TAIL_JOURNAL_COMPLETE", "TAIL_EVALUATION_COMPLETE", "TAIL_HISTORY_COMPLETE", "UNBROKEN_END"):
        assert marker in text
    # Remove repeated page/table headings and left-column date/hour labels
    # before checking the complete uninterrupted source-note text.
    body_xs = (template.X + template.CONTENT_WIDTH * .40 + 5, template.X + 78)
    bodies = "\n".join(c[1] for page in pages for c in page if c[0] == "text"
                       and any(abs(c[2] - x) < .01 for x in body_xs)
                       and c[1] != "NỘI DUNG VÀ ĐÁNH GIÁ TỪNG BUỔI")
    compact = re.sub(r"\s+", "", bodies)
    for item in report["progress"]:
        # A long session note appears once in its journal and once in history.
        assert compact.count(re.sub(r"\s+", "", item["notes"])) >= 2
    assert "Nhật ký đào tạo (tiếp)" in text
    assert "Lịch sử Đào tạo & Đánh giá (tiếp)" in text
    assert_bounds(pages)


def test_day_totals_group_sessions_and_unknown_times_are_never_fabricated():
    report = reference_report()
    report["progress"][1]["training_date"] = report["progress"][0]["training_date"]
    report["progress"][1]["end_time"] = None
    export._fonts()
    text = _model_text(template.build_pdf_layout(report))
    assert "1 ngày · 2 buổi · 1,33 giờ · 1 buổi chưa có giờ" in text
    assert "13:30-Chưa có · Chưa có giờ" in text
    assert template._hours({"start_time": "10:30", "end_time": "09:00"}) is None
    assert template._hours({"start_time": "09:00", "end_time": "09:00"}) is None


def test_history_is_date_sorted_and_recovers_all_source_records_from_partial_history():
    report = synthetic_report()
    report["history"] = report["history"][1:2]
    items = template._history_items(report)
    assert len(items) == 4
    assert [str(item["date"]) for item in items] == ["2026-10-05", "2026-10-03", "2026-10-02", "2026-10-01"]
    assert len({(item["type"], item["id"]) for item in items}) == 4
    export._fonts()
    text = _model_text(template.build_pdf_layout(report))
    assert "TAIL_EVALUATION_COMPLETE" in text
    assert "TAIL_JOURNAL_COMPLETE" in text


def test_pdf_chart_chunks_preserve_every_point_and_all_seven_raw_criteria():
    report = synthetic_report()
    progress = [{**report["progress"][0], "id": f"training-{i}", "training_date": date(2026, 1, 1) + timedelta(days=i), "skill_score": 2} for i in range(61)]
    details = [{**report["evaluation_details"][0], "id": f"evaluation-{i}", "end_date": date(2026, 1, 1) + timedelta(days=i), "attendance_score": 5} for i in range(43)]
    export._fonts()
    layout = template._CardLayout()
    template._chart_pair(layout, progress, None)
    template._evaluation_chart(layout, {"evaluation_details": details})
    pages = layout.finish()
    dots = [c for page in pages for c in page if c[0] == "circle"]
    assert len(dots) == 61 + 43 * 7
    text = _model_text(pages)
    assert "Buổi 61-61/61" in text
    assert "Phiếu 37-43/43" in text
    for _, label in export.SCORE_FIELDS:
        assert label in text
    assert_bounds(pages)


def test_pdf_missing_scores_keep_gaps_and_partial_radar_stays_open():
    export._fonts()
    layout = template._CardLayout()
    template._plot(layout, [{"training_date": "2026-10-01", "skill_score": v} for v in (3, None, 4, 0, 5)], 40, 40, 230, skill=True)
    assert len([c for c in layout.commands if c[0] == "circle"]) == 3
    assert not [c for c in layout.commands if c[0] == "line" and c[-2] == export.GOLD and c[-1] == 1.4]
    layout = template._CardLayout()
    template._radar(layout, {"craft": 4, "communication": None, "attitude": 3, "conduct": 5}, 40, 40, 230)
    assert len([c for c in layout.commands if c[0] == "circle"]) == 3
    assert not [c for c in layout.commands if c[0] == "polygon" and c[2] == export.GREEN]
    assert "Chưa có" in _model_text(layout.pages)


def test_pdf_long_headers_and_aggregate_text_reflow_without_clipping():
    report = reference_report()
    report["employee"]["full_name"] = "Tên nhân viên rất dài " * 350
    report["evaluations"] = [{"cycle_name": "Tên đợt đánh giá " * 160 + f" CYCLE_{i}", "end_date": "2026-10-01", "craft": 3} for i in range(8)]
    export._fonts()
    pages = template.build_pdf_layout(report)
    text = _model_text(pages)
    for index in range(8):
        assert f"CYCLE_{index}" in text
    assert_bounds(pages)


def test_selected_scope_and_comprehensive_gold_are_preserved_without_admin_sections():
    report = synthetic_report()
    report["filters"] = {"evaluator_role": "quanly", "rating": "excellent", "q": "chăm sóc vai gáy"}
    export._fonts()
    pages = template.build_pdf_layout(report)
    text = _model_text(pages)
    for marker in ("Khoảng: 01-10-2026 đến 10-10-2026", "Người đánh giá: Quản lý",
                   "Xếp loại: Xuất sắc", "Từ khóa: chăm sóc vai gáy"):
        assert marker in text
    assert any(c[0] == "roundrect" and c[-2] == template.EVALUATION_GOLD for page in pages for c in page)
    assert "Tài khoản" not in text and "Mã phiếu" not in text
    assert_bounds(pages)
    reader = PdfReader(BytesIO(export.render_training_report(report, "pdf")))
    assert reader.metadata.title == "Báo cáo đào tạo - Trần Thị Thảo"
    default = _model_text(template.build_pdf_layout(reference_report()))
    assert "Khoảng:" not in default and "Từ khóa:" not in default
