# HC payroll mobile layout · 11-10-2026

## Requested presentation changes

- On phones, keep the month field inside its panel. Give calculation its own
  full-width row, keep open/recalculate side by side, and retain the separate
  full-width delete action.
- Align the advance ledger's three period presets in equal columns and its
  show/refresh buttons in two equal columns. Custom dates use full-width rows.
- In the employee salary-source table, show the system name first and the full
  name below. Keep all three columns in the available width, with complete
  names, department labels and source labels wrapping rather than clipping.

## Implementation boundaries

The generic payroll fitter forces max-content table width and nowrap cells.
This table already bypasses zoom; scoped width, fixed-layout and wrapping rules
now override those shared declarations. Source columns use 34% / 20% / 46%.
Native grouped radios, labels, focus outlines and 44px label targets remain.
Radio padding is reset so shared input padding cannot enlarge the 18px control.
The native month field has shrinkable grid and WebKit value-box containment.

Only presentation and regression coverage change. Payroll source selection,
calculation, fine/late-wage handling, revisions, backend capability gates,
permissions, API routes and saved records retain their existing behavior.
No deployment, production settings or payroll data changes are part of this PR.

## Verification and remaining limitation

The supplied images were inspected before implementation. DOM coverage checks
system/full-name order, long names and custom HR departments, full option labels,
label activation, focus, mutually exclusive selection and filtering without writes.
Parsed CSS contracts cover 320, 360, 375, 390, 430, 1024 and 1440px, including
shared fitter precedence, wrapping, radio sizing and mobile-only control layout.
Existing payroll and advance-ledger behavioral regressions are retained.

CSS contracts and DOM tests are not rendered geometry. Real-browser screenshots,
scroll-width measurements and native iOS month rendering were not verified:
browser execution in this environment had previously been denied. The denial
was respected. Existing ancestor overflow clipping is not evidence of fitting.
Before claiming pixel verification, check the stated phone widths in a permitted
browser, including long text, custom dates, radio keyboard navigation and focus.
