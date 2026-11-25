# 0011 Postgres job queue, worker and email delivery

Status: Accepted

## Context

Email was sent from an in-process background task after the response. A crash or an SMTP
outage at that moment lost the message, and nothing purged expired sessions, tokens,
idempotency records or rate-limit rows. The app needs durable jobs with retries, and
push notifications need the same machinery. Postgres is already the only stateful
dependency.

## Decision

A `jobs` table with `FOR UPDATE SKIP LOCKED` (`app/jobs`), not procrastinate or Redis.

- **Why not procrastinate.** It would be a good fit, but it brings its own schema and
  migration mechanism, a sync/async split and a PL/pgSQL-heavy design to learn and review,
  for roughly 150 lines of queue code here. The table is one Alembic migration like every
  other table, tests use the same schema fixtures, and the behavior is easy to read. If
  needs outgrow this (priorities, many queues, large volume), swap it behind `enqueue`.
- **Enqueue is part of the caller's transaction.** `enqueue(db, kind, payload)` only adds
  a row to the session, so the job exists if and only if the request commits. A rolled-back
  request sends nothing (tested for email and push).
- **Claiming.** A worker claims the oldest due job in a short transaction
  (`SELECT ... FOR UPDATE SKIP LOCKED`, status `running`, `attempts + 1`, a fresh random
  `lease_token`) and runs the handler outside any transaction or held connection. Success
  deletes the row. Finishing or failing a job is conditional on the lease token
  (`WHERE id = ... AND lease_token = ...`): a worker that outlived its lease cannot delete
  or overwrite the job another worker reclaimed; it logs `job_lease_lost` and changes
  nothing.
- **Retries.** A failure requeues with exponential backoff (15 s doubling to 1 h, +-20%
  jitter) until `max_attempts` (8 for email, 5 for push, 3 for periodic jobs); then the job
  is `dead`: its payload is cleared (it may hold addresses and links) and only the
  exception class name is kept. Unknown job kinds die immediately.
- **At-least-once.** A claim older than `JOB_LOCK_TIMEOUT_SECONDS` (300) counts as lost and
  the job runs again; handlers are cancelled after `JOB_TIMEOUT_SECONDS` (120), which must
  be shorter. A job lost on its last attempt is marked dead, not run again. Email passes the
  job id as the provider idempotency key (Resend honors it; SMTP does not), so a duplicate
  is possible with SMTP.
- **Periodic jobs.** Each worker's scheduler inserts one job per kind per interval with a
  unique `dedupe_key` (`periodic:<kind>:<interval bucket>`), so any number of workers
  schedule each run exactly once with no leader election: receipts every 15 minutes, purge
  every hour. A finished periodic job is not deleted: it stays as a payload-free `done`
  marker, so its key keeps the interval taken until the next bucket (the scheduler polls
  every 30 seconds and must not enqueue the same interval again). Markers are purged with
  the other old jobs.
- **Worker.** `python -m app.jobs` (SIGTERM finishes running jobs, then exits). One pool
  connection per concurrent runner plus one; `WORKER_CONCURRENCY` defaults to 4. Compose
  and the smoke overlay run it as the `worker` service; its health check is a heartbeat
  file touched by the scheduler loop (liveness, like `/health`, not database health).
- **Purge** deletes in batches of 5000 using `ctid ... FOR UPDATE SKIP LOCKED`, so it never
  waits on rows requests hold. Jobs go `JOB_RETENTION_DAYS` (default 3) after creation
  whatever their state (dead, `done` markers, or queued and never delivered), so payloads
  cannot accumulate. Sessions are kept 7 days after expiry or 30 days after
  revocation; refresh tokens go with their sessions (cascade); account tokens 1 day after
  expiry; idempotency records and rate-limit windows when expired.

Account work that must not shape the response (registration, resend, password reset) still
runs in a FastAPI background task after the response, as in ADR 0008, but now enqueues its
emails in the same transaction as its writes instead of sending them.

## Consequences

- Delivery needs a running worker. Without one, mail queues up (visible in `jobs`).
- **Job payloads are sensitive.** An email job holds the recipient and the full rendered
  message, which includes bearer links (verification, password reset, email change);
  a push job holds its title, body and a small allowlisted `data`. They are stored in
  plaintext, live until the job is delivered (minutes, or hours while retrying), and are
  deleted on success, cleared on death and purged after `JOB_RETENTION_DAYS`. Anyone who
  can read the database can already read the account tokens' hashes, sessions and every
  user's data, so this widens the exposure little but not to zero: a read of the jobs table
  during that window yields usable links. Do not enqueue secrets that are not already
  emailed. Follow-up if that is not acceptable: encrypt payloads at rest with a key held
  only by the API and worker (not built).
- Postgres load grows with job volume; this is for transactional volume, not bulk.
- Production email is `smtp` (TLS required, as before) or `resend`; `console` and
  `memory` stay development/test only.
