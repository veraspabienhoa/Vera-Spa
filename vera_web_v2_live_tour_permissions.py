"""Independent Live Tour grants, including safe legacy-permission fallback."""

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
    "invoice_date_edit": "live_tour_invoice_date_edit",
    "customers_edit": "live_tour_customers_edit",
    "customers_delete": "live_tour_customers_delete",
    "customer_combo_edit": "live_tour_customer_combo_edit",
    "customer_combo_delete": "live_tour_customer_combo_delete",
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
    "revenue": ("live_tour_reports_view",),
    "tip": ("live_tour_reports_view",),
    "reports": ("live_tour_reports_view",),
    "customers": ("live_tour_customers_view",),
    "pending": ("live_tour_pending_view", "live_tour_invoice_view"),
    "history": ("live_tour_history_view",),
    "breaks": ("live_tour_history_view",),
    # This workbook includes all of these ledgers, so require every read grant.
    "customer_detail": ("live_tour_customers_view", "live_tour_invoice_view",
                        "live_tour_paid_invoice_view", "live_tour_pending_view", "live_tour_reports_view"),
}
