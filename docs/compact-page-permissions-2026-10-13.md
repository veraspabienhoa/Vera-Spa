# Compact page permission menu — 13-10-2026

Each Admin page has one Phân quyền launcher in its visible main heading. Its
modal contains the page-level edit/list choices and the currently mounted,
visible tab's scoped edit/list choices. Tab components register scope metadata
without rendering additional controls. Live Tour has no launcher or scope
controls. Non-Admin and mandatory-password-change users still see no controls.

The shared launcher follows lazy-loaded and replaced headings with a local
MutationObserver. A dedicated portal host keeps the button beside title text,
reattaches after title text updates and cleans up on navigation/unmount. No
heading yields no detached toolbar. Heading text can wrap beside the compact
button on mobile. The menu is keyed by page/account and closes on navigation.

Only the selected edit/list dialog reads the permission API. The existing
scoped writes, dependencies, revision checks, capability acknowledgements and
Admin checks remain unchanged. No account permissions, backend or production
data were modified. Source change only; deployment has not been verified.
