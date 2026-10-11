# Background runtime separation, 11-10-2026

Source-only change. No deployment, production data access, service installation,
credential change, or FaceGate/TimeSoft schedule change was performed.

## Compatible default and optional split

`VERA_SERVICE_ROLE` accepts only `combined`, `api`, or `worker`; unset remains
`combined`. The existing `vera_web_v2_api_v38:app` command therefore continues to
run the same seven background loops. Invalid values fail startup instead of
silently stopping work. Importing worker installers no longer starts threads.

An operator may later opt into:

- API processes: `VERA_SERVICE_ROLE=api`, existing API entrypoint. Routes,
  permissions, revocation checks and the separate authentication pool remain.
- Worker processes: `VERA_SERVICE_ROLE=worker`,
  `uvicorn vera_web_v2_worker:app --host 127.0.0.1 --port <operator-selected-port>`.
  This uses the complete canonical attendance/policy installer chain while
  exposing only runtime health/readiness. No business, login or documentation
  endpoints are exposed by this entrypoint.

Role selection is process-specific. API and worker must use the same business
PostgreSQL database and compatible code release. The worker entrypoint rejects
an explicit conflicting role. Do not put a worker behind the business API load
balancer. Changing the environment alone is not a deployment plan.

## Jobs retained

The supervised job inventory is checked when the canonical application loads:

1. Live Tour projection scheduling
2. Live Tour projection consumption
3. Live Tour queue-alert monitoring
4. Leave-sheet mirroring
5. Leave-quota scans/delivery
6. Unified notification delivery
7. Technical retention checks

FaceGate archive/name/deletion jobs, TimeSoft jobs and daily operations remain
under their current external CLI/timer schedules. They are not started by the
new worker entrypoint. Do not disable those existing schedules when splitting
ASGI jobs. AutoCheck activation/pause/freshness, authoritative Vera shifts,
no-retroactive-fine rules and financial event writers are unchanged.

## Coordination, failover and shutdown

There is no new resident global lock or dedicated coordination connection.
Each loop keeps its existing database coordination: projection jobs have unique
bucket/event keys and fenced `SKIP LOCKED` claims; quota scans and queue-alert
checks have short transaction locks; retention has its existing due check and
session lock, using its caller's connection. That retention lock spans commits:
a direct PostgreSQL connection or verified session-affine pooler is required.
A transaction-mode pooler cannot preserve its lock ownership and is not supported
for worker/replica cutover. Do not infer topology from a hostname/port, a successful
health request, or one repeated backend PID. Verify the actual connection route
and pooler mode with the operator before declaring `VERA_WORKER_DB_MODE=direct`
or `session`. The unchanged retention implementation does not itself prove this
property. With that prerequisite and the retained queue guards, replicas can
coordinate without a separate Redis/queue service. More replicas are not assumed faster;
include every API/worker and external job in the configured connection budget.

Leave mirroring now recovers abandoned claims after ten minutes and fences
completion/retry by the precise claim timestamp. The token is renewed and
committed immediately before each outbound Sheets step, including the update,
so a nearly expired owner does not initiate a write with an old lease. A stale
owner detected at renewal cannot begin the next remote step, complete or release
a newer claim. A remote write already in flight or an OS pause after renewal
cannot be fenced inside Google Sheets. A private Sheets session
sets connect/read timeouts to 5/30 seconds, uses a separate no-retry auth transport
with 5/10-second connect/read timeouts and at most one 401 refresh retry, and
applies the Google transport's 45-second overall request budget. That transport budget checks
elapsed time around underlying requests; it is not a remote-server cancellation
guarantee. Shared API client timeout settings are unchanged. Each retry updates the existing source row for the
same record UID; it does not insert another financial/leave event. Notification
claims are refreshed before each bounded send and both completion and saved
subscription progress are fenced. Existing event/recipient/channel unique keys
remain. External delivery is at-least-once: a crash after a remote success but
before PostgreSQL records success can retry that delivery. This does not promise
exactly-once push delivery, and it does not create another financial event.

All network work remains outside queue/business transactions. No new pooled
connection is acquired while a business transaction or Live Tour lock is held.

ASGI lifespan validates all queue prerequisites before any thread starts. A
single supervisor starts the registered loops and signals all of them together
on shutdown, waiting up to a shared 30-second join deadline. In-flight jobs may
finish normally. A timed-out loop makes the runtime unready; its durable claims
are not cleared, stolen or reassigned during shutdown. Process exit and existing
lease expiry permit recovery. A delayed heartbeat cannot restore a draining
runtime to ready. Graceful termination must allow this drain window plus bounded
database operations before an operator forces process exit.

## Health and safe rollout

`/v2/runtime/health` is local liveness/loop responsiveness. A crashed or stalled
registered loop makes it return 503. `/v2/runtime/ready` additionally reads a
committed heartbeat from a healthy combined/worker instance with the complete
job inventory, no older than 30 seconds. API-only instances return 503 readiness
when no such worker exists. Combined/worker local readiness and a ready worker
heartbeat also require the operator-confirmed direct/session-affine database
mode. API-only readiness relies on that eligible worker heartbeat; the API may
use a different database connection route because it does not run these loops.
This is not a claim that every other API operation supports transaction pooling:
for example, the existing tour-leave-sync endpoint also depends on a session lock
across workbook I/O. Verify those paths separately before changing API topology.

`VERA_WORKER_DB_MODE` accepts `unknown` (the default), `direct`, `session`, or
`transaction`. Explicit worker mode fails startup for unknown/transaction mode.
For compatibility, unset/combined deployments keep their existing seven jobs
running, but the **new** runtime readiness endpoint returns 503 until affinity
is verified and configured. This does not change `/v2/health` or
`/v2/auth/health`. Do not start using runtime readiness for rollout before this
verification. Process settings override the shared managed file when API and
worker routes differ. This declaration is an operator safety gate, not automatic
topology detection.

Heartbeats contain only technical identifiers, use
short transactions, and never replace auth or business health checks. The
additive `vera_worker_runtime` table is installed by the schema gate and has a
serialized startup fallback for existing deployments. It contains no employee,
customer, credential or financial data. Old heartbeat rows age out after one day.

A healthy loop does not establish successful job outcomes or current device
evidence. Continue checking projection queue lag/failures and actual FaceGate
freshness, as well as `/v2/auth/health`, `/v2/health`, deployed commit and the
relevant business readback. This source change does not update an operator's
load-balancer readiness configuration automatically.

Suggested authorized rollout sequence:

1. Keep combined mode during the first source deployment and verify all health
   checks, queue outcomes and a representative authenticated business operation.
2. Verify the real direct/session-affine database route and set
   `VERA_WORKER_DB_MODE=direct` or `session` only after that verification.
   Start the separate worker with the same release/database. Verify its runtime
   readiness and job progress while combined mode still provides continuity.
3. Change API processes to `api` only after the worker is ready. Confirm their
   runtime readiness, all ordinary health checks and business readback.
4. Observe queue lag, retries, worker heartbeat, device freshness, request latency
   and total database connections. Keep the existing external schedules active.
The separate auth pool isolates database admission only; authentication and
business HTTP handlers still share server thread capacity. Database saturation
tests alone do not establish end-to-end login availability under HTTP overload.

Rollback: restore the API role to `combined` first and verify jobs and readiness,
then drain/stop the dedicated worker. The heartbeat schema is additive and can
remain. Never truncate job queues, clear another process's claims, alter financial
rows, or drop new technical tables as a shortcut to rollback. Rolling back to
older code retains its prior concurrency/lease limitations.

## Verification

Synthetic PostgreSQL tests cover separate processes competing for one committed
job, projection scheduling deduplication, abandoned leave-claim recovery, stale
owners, network calls with zero checked-out connections, independent replica
shutdown, expired/incomplete heartbeat readiness and notification ownership.
Unit tests cover all roles, default compatibility, inventory completeness,
startup failure, stalled/crashed loops, bounded drain, prior lifespan state and
worker-only routing. A fresh-process test imports the actual canonical API and
worker entrypoints with external HTTP/DNS blocked and forbids background thread
startup during import; it runs real registration, schema preparation and lifespan
against isolated PostgreSQL with synthetic per-loop work callbacks. The existing
admin-audit installer still performs schema DDL during canonical import, so that
import requires the selected database; this change does not claim a pool-free
canonical import or move unrelated audit initialization. Existing attendance, auth, penalty notification, retention,
Live Tour and notification regressions remain required. Production throughput,
service supervision, routing and remote-delivery behavior require an authorized
rollout; no production performance claim is made here.
