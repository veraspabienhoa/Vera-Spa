# Live Tour report render recovery

The reported action is the **Báo cáo button inside Live Tour**. The screenshots
show `PAGE_RENDER · live-tour`; they contain neither an exception stack nor a
loaded asset revision. The exact production exception remains unverified.
Public application/build-info reads from the investigation environment returned
403; no authenticated production data was read or changed.

## Confirmed source defects

- After a successful collection read, an empty/partial aggregate object still
  reached `toLocaleString` in the summary. Missing aggregates could also silently
  substitute page-local sums. The full mounted page reproduced the screenshot's
  generic boundary. Current and oldest available API sources emit complete
  numeric aggregates, including real zeros for empty reports, so malformed
  aggregates are not assumed to be the user's production cause.
- Synthetic data passed through the real current API route with HTTP 200 and
  complete totals can retain object-valued employee/service labels or malformed
  invoice-number metadata. These reach React object-child or non-iterable errors
  in the real report panel and filters. Null optional fields render normally.

## Changes

- Validate report collection pagination, whole-filter aggregates and renderable
  row shapes before making a result ready. Bound nested invoice metadata checks.
- Keep the board available, show `REPORT_DATA_INVALID`, and allow an explicit
  read-only retry. Do not replace unavailable totals with zeros, page totals,
  previous responses or board data. Treat explicit empty row arrays as empty.
- Apply permission reductions accompanying invalid data under the existing
  current-request guard; canceled responses cannot restore data or permissions.
- Remove the summary's implicit page-local fallback. Preserve actual numeric
  zero aggregates and nullable optional labels.
- Show only a fixed render-error category and the revision embedded in the
  loaded JavaScript. Never show or transmit raw exception text, stacks, customer
  values, credentials or private URLs. A newer deployed manifest is not claimed
  to be the loaded build.

No financial calculations, ledger records, backend authorization, production
deployment or database migrations are changed. This addresses confirmed source
exceptions and supplies safe evidence for any remaining production exception;
it does not establish that production contained any particular malformed field.

## Verification

Mounted tests use the real page, filters, details loader, report panel, summary
and error boundary. They cover initial/loading/hydrated states; Admin, quanly
and letan; legacy and versioned permission metadata; malformed and empty data;
retry; paging/filter changes; leaving/reopening; cancellation and revocation.
Diagnostics tests verify loaded-build provenance and absence of raw private
exception content. Full regression, lint and build results are recorded in the PR.
