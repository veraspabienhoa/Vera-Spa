# Booking time entry and leave tab work reduction

The supplied recordings show the Booking arrival-time field and switching
between Registration, Statistics and List in leave registration.

Booking now accepts explicit 24-hour HH:mm text (or four digits such as 0715)
and provides separate hour/minute selectors. Partial and invalid input clears
the parent value and blocks form submission, avoiding stale saved times.
The existing API accepts any valid minute; the browser's old 15-minute step is
removed. No date, timezone, authorization or booking-write semantics change.

Leave registration reuses its Vietnam date formatter and calculates today's
date once for row permission rendering instead of constructing formatters for
each repeated row check. The leave-type compatibility enhancer observes its own
panel instead of resynchronizing on unrelated page changes. Existing drafts,
read sequencing, refreshes, policy checks and API data remain unchanged.

Local microbenchmark (3,000 formats): approximately 179 ms before, 4 ms after.
This is not an end-to-end production latency measurement. Production database,
network latency and runtime remain unverified. No deployment performed.
