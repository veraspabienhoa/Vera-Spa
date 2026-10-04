# 04-10-2026 — Repeated page error panel: asset lifetime

Public read-only checks at approximately 13:30 Vietnam time found build-info
revision `1194370e820b4192591c2545e5c4337f10952c34` and HTTP 200 for
`/assets/index-B5yrpZvK.js`. The immediately preceding locally built revision
`205b41189449b1c04c3557866569443a2bdca047` referenced
`/assets/index-tjk1S7zC.js` and `DevicePage-DGh0qTuV.js`; both public asset URLs
returned HTTP 404 with text/html. This confirms those older assets are absent,
not the exact JavaScript exception in the user's existing tab. The screenshot
boundary previously combined module failures and rendering exceptions without
classification. Repeating a dynamic import of a removed hashed URL cannot fix it.

Source changes retain prior hashed dependencies for seven days when the previous
release directory is available at build time, and distinguish load failures from
render failures. On load failure only, a bounded no-store build-info check offers
an explicit update preserving the requested page. No automatic reload, data
mutation, auth bypass, or changes to attendance/payroll. Tests cover real Vite
output retention, dependency graphs, expiration timestamps, exclusion of maps,
module classification, version checks and offline behavior. Production retention
path and old-tab navigation must be verified after deployment. This patch is not
proof that every occurrence is an asset failure; PAGE_RENDER needs its own runtime
exception reproduction. No production deployment was performed in this session.
