"""Audited paid-invoice corrections. Never hard-delete the original evidence."""
from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException


def change_paid_invoice(state, action, payload, actor, now, *, money, payment_values, canonical_method, available_combo, iso, max_money):
    deleting = action == "paid_invoice_delete"
    allowed = {"invoice_id", "reason"} if deleting else {"invoice_id", "reason", "note", "entries", "discount", "tip", "payment_method"}
    if set(payload) - allowed:
        raise HTTPException(400, "Không được đổi khách hàng, dịch vụ, ngày hoặc mã hóa đơn đã thanh toán; hãy hủy và lập lại nếu cần.")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise HTTPException(400, "Nhập lý do sửa/hủy hóa đơn (tối đa 1000 ký tự).")
    working = deepcopy(state)
    invoice = next((row for row in working["invoices"] if row.get("id") == payload.get("invoice_id")), None)
    if invoice is None:
        raise HTTPException(404, "Không tìm thấy hóa đơn đã thanh toán còn hiệu lực.")
    before = deepcopy(invoice)
    reports = [row for row in working["reports"] if row.get("invoice_id") == invoice["id"]]
    usage = [row for row in working["combo_usage"] if row.get("invoice_id") == invoice["id"]]
    if not invoice.get("entries") or len(reports) != len(invoice["entries"]):
        raise HTTPException(409, "Hóa đơn và báo cáo chưa khớp; cần đối soát trước khi sửa/hủy.")
    reports_before, usage_before = deepcopy(reports), deepcopy(usage)
    purchase_id = invoice.get("purchased_combo_id") or invoice.get("combo_purchase_id")
    customer = next((row for row in working["customers"] if row.get("id") == invoice.get("customer_id")), None)
    purchase = next((row for row in (customer or {}).get("combo_purchases", []) if row.get("id") == purchase_id), None) if purchase_id else None
    if purchase_id and purchase is None:
        raise HTTPException(409, "Không tìm thấy combo gốc để đối soát hóa đơn. Chưa có dữ liệu nào bị thay đổi.")
    purchase_before = deepcopy(purchase)
    if deleting:
        if invoice.get("purchased_combo_id"):
            reserved = available_combo(working, customer["id"], purchase)["booking_reserved"]
            has_usage = any(row.get("combo_purchase_id") == purchase_id for row in working["combo_usage"])
            open_entries = working["employees"] + [entry for row in working["pending"] for entry in row.get("entries", [])]
            bound_booking = any(row.get("combo_purchase_id") == purchase_id for row in open_entries)
            if int(purchase.get("used") or 0) or reserved or has_usage or bound_booking:
                raise HTTPException(409, "Combo đã sử dụng hoặc đang giữ chỗ. Hãy xử lý các lượt dùng/booking liên quan trước khi hủy hóa đơn bán combo.")
            customer["combo_purchases"].remove(purchase)
            purchase = None
        elif purchase_id:
            units = invoice.get("combo_units")
            if (type(units) is not int or units <= 0 or len(usage) != 1
                    or usage[0].get("units") != units or usage[0].get("combo_purchase_id") != purchase_id
                    or usage[0].get("customer_id") != invoice.get("customer_id")):
                raise HTTPException(409, "Lịch sử trừ vé không khớp hóa đơn; chưa thể hoàn vé an toàn.")
            if int(purchase.get("used") or 0) < units or int(purchase.get("remaining") or 0) + units > int(purchase.get("total") or 0):
                raise HTTPException(409, "Số dư vé không khớp để hoàn vé an toàn.")
            plan = invoice.get("combo_component_debits") or []
            if "component_balances" in purchase:
                if not plan or plan != usage[0].get("component_debits") or sum(row["units"] for row in plan) != units:
                    raise HTTPException(409, "Thiếu lịch sử trừ lượt từng dịch vụ; chưa thể hoàn combo an toàn.")
                seen = set()
                for debit in plan:
                    balance = next((row for row in purchase["component_balances"] if row["service_id"] == debit["service_id"]), None)
                    amount = debit.get("units")
                    if (balance is None or debit["service_id"] in seen or type(amount) is not int or amount <= 0
                            or balance["used"] < amount or balance["remaining"] + amount > balance["total"]):
                        raise HTTPException(409, "Số lượt dịch vụ không khớp để hoàn combo an toàn.")
                    seen.add(debit["service_id"])
                    balance["used"] -= amount
                    balance["remaining"] += amount
            purchase["used"] -= units
            purchase["remaining"] += units
            purchase["updated_at"] = iso(now)
        working["invoices"].remove(invoice)
        working["reports"] = [row for row in working["reports"] if row.get("invoice_id") != invoice["id"]]
        working["combo_usage"] = [row for row in working["combo_usage"] if row.get("invoice_id") != invoice["id"]]
        after = None
    else:
        edits = payload.get("entries", [])
        if not isinstance(edits, list) or len(edits) > len(invoice["entries"]):
            raise HTTPException(400, "Danh sách giá dịch vụ không hợp lệ.")
        seen = set()
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {"index", "price"}:
                raise HTTPException(400, "Chỉ được sửa giá dòng dịch vụ của hóa đơn đã thanh toán.")
            index = edit["index"]
            if type(index) is not int or not 0 <= index < len(invoice["entries"]) or index in seen:
                raise HTTPException(400, "Dòng hóa đơn không tồn tại hoặc bị trùng.")
            seen.add(index)
            invoice["entries"][index].update(price=money(edit["price"], label="Giá dịch vụ"), price_source="paid_correction")
        subtotal = money(sum(int(row.get("price") or 0) for row in invoice["entries"]), label="Tạm tính")
        discount, tip, _ = payment_values(working, {"discount": payload.get("discount", invoice.get("discount", 0)), "tip": payload.get("tip", invoice.get("tip", 0))}, subtotal, money, max_money)
        method = canonical_method(payload.get("payment_method", invoice.get("payment_method")), quick=True)
        if (method == "COMBO") != (invoice.get("payment_method") == "COMBO"):
            raise HTTPException(400, "Không đổi qua lại COMBO trên hóa đơn đã thanh toán. Hãy hủy hóa đơn và lập lại để đối soát vé.")
        covered = invoice.get("combo_units_source") == "server_purchase_components"
        if covered and discount:
            raise HTTPException(400, "Lượt combo đã trả tiền khi mua, không giảm giá thêm khi dùng lượt.")
        total = money(tip if covered else subtotal - discount + tip, label="Tổng thanh toán")
        if "note" in payload:
            if not isinstance(payload["note"], str) or len(payload["note"]) > 2000:
                raise HTTPException(400, "Ghi chú không hợp lệ hoặc vượt quá 2000 ký tự.")
            invoice["note"] = payload["note"].strip()
        if "discount" in payload:
            invoice.update(discount_mode="amount", discount_percent=None)
        if "tip" in payload:
            invoice["tip_cards"] = []
        invoice.update(subtotal=subtotal, discount=discount, tip=tip, total=total, payment_method=method,
                       updated_at=iso(now), updated_by=actor)
        if covered:
            invoice["combo_covered_amount"] = subtotal
        if invoice.get("purchased_combo_id"):
            purchase.update(price=subtotal - discount, updated_at=iso(now))
        for index, report in enumerate(reports):
            report.update(total=total // len(reports) + (index < total % len(reports)),
                          tip=tip // len(reports) + (index < tip % len(reports)),
                          payment_method=method, note=invoice.get("note", ""), updated_at=iso(now), updated_by=actor)
        after = deepcopy(invoice)
    change = {"id": str(uuid4()), "invoice_id": before["id"], "action": action, "actor": actor,
              "at": iso(now), "reason": reason.strip(), "before": before, "after": after,
              "reports_before": reports_before, "usage_before": usage_before,
              "purchase_before": purchase_before, "purchase_after": deepcopy(purchase)}
    working.setdefault("invoice_changes", []).append(change)
    state.clear()
    state.update(working)
    return {"invoice": after, "invoice_id": before["id"], "change_id": change["id"], "voided": deleting}
