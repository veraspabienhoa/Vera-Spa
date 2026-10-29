# 29-10-2026 — Manual revenue entry date scope

Admin can configure the existing Nhập doanh thu - chi phí permission by role
or account: 3, 5, 7, custom positive whole days (1–36500), or all dates.
A limited window includes today and N−1 preceding Vietnam calendar dates;
future dates are outside a limited window. All dates has no date restriction.
Admin remains unrestricted. Existing unconfigured accounts keep their prior
all-date scope, and the create permission remains independently required.

The scope is stored in the canonical feature_permissions JSON under
revenue_entry_windows, with the existing revision check, transaction and lock.
Explicit account settings (including all dates) override the role; resetting
account inheritance removes the account scope. Older clients and unrelated
page saves preserve the stored scope. Scope values are validated as strict
integers or null. Only Admin can write permission settings.

Revenue summary/period-report responses expose the effective bounds for the
entry form. POST /v2/revenue/entry rereads canonical scope on its caller's
connection before duplicate lookup or any financial write, including duplicate
confirmation. The date scope does not grant edit/delete/import permissions,
change report filters, or affect the separate Quảng Ngãi ledger.

Source changes only. No production permission grants, financial data changes,
merge or deployment performed as part of this implementation.
