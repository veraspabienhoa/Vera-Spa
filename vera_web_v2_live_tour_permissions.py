"""Independent Live Tour grants, including safe legacy-permission fallback."""

# Policy v1 preserves existing readable date ranges until a role or account
# explicitly configures an individual date grant. These are read capabilities:
# a true date flag never bypasses the section's effective read permissions.
DATE_FILTER_POLICY_VERSION = 1
DATE_FILTER_PRESETS = {
    "all": "Tất cả",
    "today": "Hôm nay",
    "yesterday": "Hôm qua",
    "week": "Tuần này",
    "last_week": "Tuần trước",
    "month": "Tháng này",
    "last_month": "Tháng trước",
    "custom": "Tùy chỉnh",
}
DATE_FILTER_SECTIONS = {
    "pending": "Hóa đơn chờ thanh toán",
    "invoices": "Hóa đơn đã thanh toán",
    "reports": "Báo cáo",
    "history": "Lịch sử & sao lưu",
}
DATE_FILTER_FEATURES = {
    f"live_tour_{section}_date_{preset}": f"{label} · Lọc ngày · {preset_label}"
    for section, label in DATE_FILTER_SECTIONS.items()
    for preset, preset_label in DATE_FILTER_PRESETS.items()
}
DATE_FILTER_DEPENDENCIES = {
    # Board/collection routes retain their own live_tour_view guards. Direct
    # section exports have always worked with section grants alone.
    f"live_tour_{section}_date_{preset}": set(parents)
    for section, parents in {
        "pending": ("live_tour_pending_view", "live_tour_invoice_view"),
        "invoices": ("live_tour_paid_invoice_view",),
        # Standalone Reports has never required the Live Tour board grant.
        "reports": ("live_tour_reports_view",),
        # Backup-only readers have always used the history panel for backup
        # metadata. Preserve that route without granting access to the audit.
        "history": (),
    }.items()
    for preset in DATE_FILTER_PRESETS
}
DATE_FILTER_PARENT_ANY = {
    f"live_tour_history_date_{preset}": ("live_tour_history_view", "live_tour_backup")
    for preset in DATE_FILTER_PRESETS
}

LEGACY_FEATURE_INHERITANCE = {
    "live_tour_booking": "live_tour_operate",
    "live_tour_invoice_view": "live_tour_payment",
    "live_tour_paid_invoice_view": "live_tour_payment",
    "live_tour_pending_view": "live_tour_payment",
    "live_tour_customers_view": "live_tour_payment",
    "live_tour_reports_view": "live_tour_payment",
    "live_tour_history_view": "live_tour_admin",
    "live_tour_backup": "live_tour_admin",
}
# Edit/delete did not exist before: never inherit those destructive privileges.
CAPABILITY_FEATURES = {
    "quick_checkout_backdate": "live_tour_quick_checkout_backdate",
    "booking_outside_shift": "live_tour_booking_outside_shift",
    "start_outside_shift": "live_tour_start_outside_shift",
    "reorder": "live_tour_reorder",
    "invoice_date_edit": "live_tour_invoice_date_edit",
    "customers_edit": "live_tour_customers_edit",
    "customers_delete": "live_tour_customers_delete",
    "customer_combo_edit": "live_tour_customer_combo_edit",
    "customer_combo_delete": "live_tour_customer_combo_delete",
    "combo_import": "live_tour_combo_import",
    "reports_edit": "live_tour_reports_edit",
    "reports_delete": "live_tour_reports_delete",

    "booking": "live_tour_booking",
    "invoice_view": "live_tour_invoice_view",
    "paid_invoice_view": "live_tour_paid_invoice_view",
    "paid_invoice_edit": "live_tour_paid_invoice_edit",
    "paid_invoice_delete": "live_tour_paid_invoice_delete",
    "invoice_edit": "live_tour_invoice_edit",
    "invoice_delete": "live_tour_invoice_delete",
    "pending_view": "live_tour_pending_view",
    "customers_view": "live_tour_customers_view",
    "reports_view": "live_tour_reports_view",
    "history_view": "live_tour_history_view",
    "backup": "live_tour_backup",
}

EXPORT_FEATURES = {
    "paid": ("live_tour_paid_invoice_view",),
    "revenue": ("live_tour_reports_view",),
    "tip": ("live_tour_reports_view",),
    "reports": ("live_tour_reports_view",),
    "performance": ("live_tour_reports_view",),
    "employee": ("live_tour_reports_view",),
    "customers": ("live_tour_customers_view",),
    "pending": ("live_tour_pending_view", "live_tour_invoice_view"),
    "history": ("live_tour_history_view",),
    "breaks": ("live_tour_history_view",),
    # This workbook includes all of these ledgers, so require every read grant.
    "customer_detail": ("live_tour_customers_view", "live_tour_invoice_view",
                        "live_tour_paid_invoice_view", "live_tour_pending_view", "live_tour_reports_view"),
}
