# Page position stability

The Live Tour feedback fix is extended to the shared shell and business pages.
Transient notices used to insert content above a table, loading branches removed
the table, and the header refresh changed the entire page's React key. Together
these could move the viewport, reset filters and discard form state.

## Changes

- Shared `StableFeedback` reserves a bounded, scrollable message area, including
  mobile sizing, so progress, success and error messages use the same space.
- `StableDataRegion` keeps existing table and scroll-container nodes mounted
  during refresh. A positioned status layer and `inert` prevent interaction with
  the stale table while it loads. Employee, rules, work schedule, purchase,
  appearance and leave pages use it.
- Leave records are retained only when the loaded identity and date range match
  the requested scope. Changing month hides the previous scope immediately;
  authentication/authorization errors invalidate it. Requests remain month-bound.
- Header refresh dispatches to mounted data loaders instead of changing the page
  key. A synchronous preflight checks all panels before any loader starts; dirty
  forms or busy operations veto refresh. Pending calls cannot overlap, current
  callbacks use current filters, and listeners are removed on navigation.
- Approval changes refresh long-leave overview without remounting its form.
- Initial/return focus in dialogs and programmatic edit/clear focus use
  `preventScroll`. The page keeps its scrollbar gutter and disables automatic
  scroll anchoring. Explicit navigation, Back to Top and keyboard focus traversal
  remain available.

The Face ID card reserves its feedback area with shared CSS. Its existing
identity/password module is unchanged. Automatic approval review blocked
republishing that module because it contains sensitive credential-handling
content; the CSS-only alternative does not publish or modify that module.

## Validation

- The committed frontend CI gate passes locally: 201 tests, lint and production
  build. New rendered tests cover actual App refresh/navigation, deferred purchase
  refresh, all-panel dirty veto, duplicate refresh suppression, latest filters,
  late errors after unmount, persistent table nodes and dialog focus/close safety.
- The leave editor regression covers same-scope loading without row replacement
  and hiding old-month rows during a pending month change.
- Two existing lint warnings and Vite's existing large-chunk warning remain.
- A wider optional test run found five pre-existing failures in clipboard image,
  Live Tour border and revenue TIP source assertions. The same five fail on the
  unchanged parent frontend; those tests are outside the committed CI gate.
- DOM tests use JSDOM. They verify node identity, state, focus options and CSS
  contracts; they do not measure real browser scroll pixels. Desktop/mobile
  visual verification and real production business operations require the live
  browser after deployment.

## Deployment and operator check

Frontend-only changes use the existing automatic web deployment from main.
No VPS backend release or database migration is required.

After deployment, reload the web app once. On employee, leave, purchase and
Live Tour screens, scroll part-way down and save or refresh. Confirm the viewport
and horizontal table position stay steady during loading and success/error
feedback. Open/close an editor, try refresh with unsaved input, and change the
leave month to confirm the previous month's rows are never shown as current.
An intentional filter change or deletion that substantially shortens the page
can still require the browser to clamp the scroll position to the new page end.
