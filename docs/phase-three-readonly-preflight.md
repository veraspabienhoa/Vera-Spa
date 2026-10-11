# Bounded phase-three activation inspection

The manual **Phase Three Read-only VPS Preflight** workflow gathers evidence for
an operator decision. It does not activate invoice numbering, split workers,
install a service, stop a writer, deploy code, change configuration/data, or
create credentials. Its successful exit is **not** a production-readiness claim.

## Reviewed source and target

Dispatch only on `main`, supplying its full reviewed SHA in `expected_main_sha`.
The workflow checks both the requested source and current remote main before and
after inspection. Its short-lived GitHub token has `contents: read` only. Existing
production environment and the deployment's four SSH secrets are reused without
creating a new login or changing host permissions.

The inspected application is separately pinned to the already reviewed release
`02ef3641edf1dfaf12ab048c725df03c4397af3e`. A diagnostic-only commit does not require
redeploying the app. If the active symlink or a recognized API/worker process is
on another release, database inspection is skipped and the result explicitly
reports `target_release_moved`. Do not deploy or widen the target automatically.
Review the new target first if production changed.

## Safety boundary

The runner sends two fixed reviewed Python sources through SSH standard input.
The target executes them in isolated Python mode with bytecode writing disabled;
no diagnostic files are installed on the VPS. There is no arbitrary command,
SQL, path, service, database, or action input. SSH host verification is mandatory.
Runner SSH material is deleted at job end. No application/API/worker modules are
imported, including maintenance helpers that can install schema during import.

Every database connection uses NullPool and a read-only repeatable-read
transaction with short connection, statement, lock and idle-transaction limits.
Queries are fixed SELECT statements. History inspection is bounded; exceeding a
row, byte or time limit is unknown, never a passing parity result. Customer,
employee, invoice, raw-number and credential values never appear in output.

The remote program has a 110-second alarm, the remote command a 125-second limit,
the transport a 140-second limit, and the workflow a five-minute limit. Individual
host commands have three-second limits. File/command reads and the final response
have explicit byte ceilings. Exceptions and SSH stderr are discarded rather than
printing a traceback, connection URL, SQL, parameter, script body or log body.

## What findings mean

- Runtime inventory recognizes known command tokens and inspects allowlisted
  service fields and readable current-user/system cron sources. It does not claim
  complete coverage of descendants, other users, containers, external hosts,
  cloud schedulers or every possible writer. Cron token matches are hints, not
  execution evidence.
- The host-owned deployment script's hash and recognized token flags are reported.
  Token presence does not establish correct locking or worker lifecycle handling;
  script content is never logged or executed.
- Configurations are current managed-file values overlaid on each process's initial
  environment using the production precedence. They are not a readback of live
  engine state. Only numeric allowlisted settings and fixed mode enums are emitted.
  Budget arithmetic is labeled arithmetic-only; actual pool-instance coverage,
  runtime bounds and concurrent-user capacity remain unverified.
- PostgreSQL session affinity always requires provider/pooler configuration evidence.
  Hostnames, ports, successful connections, declared mode and backend PID repetition
  cannot prove it. The diagnostic makes no affinity claim.
- Process identities/start times/releases, current symlink, managed configuration
  and deployment-script fingerprints are compared before/after. A changed
  observation discards database findings. A stable observation still is not an
  exclusive lock: some deployment workflows use different concurrency groups.
- Findings contain technical storage/receipt modes, schema/guard flags,
  normalization/counter/parity gates, heartbeat/queue counts and database capacity.
  A read-only snapshot is not a maintenance rehearsal or an authenticated business
  operation. Financial correctness and attendance freshness need their approved
  post-activation checks.

## Decision after inspection

Keep both activations off until every required prerequisite is established.
Activate the number registry before the worker split. The existing storage
maintenance workflow stops only the API and cannot establish all-writers-stopped.
An approved activation plan must inventory and stop every writer, preserve an
appropriate private backup, use the registry-aware release, perform atomic
activation, verify parity/guards, and restart matching writers. Managed settings
must remain available while API processes are stopped.

Worker isolation additionally requires proven direct/session-affine routing, a
complete connection budget including overlap, supervised service/deploy lifecycle,
and actual worker progress/readiness before changing the API role. Keep external
FaceGate/TimeSoft/daily/retention/watchdog schedules under their existing policy.

Do not promise a downtime duration from counts alone. A provisional supervised
15–30-minute window is a planning allowance only after the unknown gates have been
closed and the bounded migration has been rehearsed. The activation CLI's
60-second statement deadline is not an overall maintenance deadline. Obtain the
owner's maintenance approval separately before any service or database change.
