# 0009 Postgres job queue, worker and email delivery

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
  (`SELECT ... FOR UPDATE SKIP LOCKED`, status `running`, `attempts + 1`) and runs the
  handler outside any transaction or held connection. Success deletes the row.
- **Retries.** A failure requeues with exponential backoff (15 s doubling to 1 h, +-20%
  jitter) until `max_attempts` (8 for email, 5 for push, 3 for periodic jobs); then the job
  is `dead`: its payload is cleared (it may hold addresses and links), only the exception
  class name is kept, and dead jobs are purged after 14 days. Unknown job kinds die
  immediately.
- **At-least-once.** A claim older than `JOB_LOCK_TIMEOUT_SECONDS` (300) counts as lost and
  the job runs again; handlers are cancelled after `JOB_TIMEOUT_SECONDS` (120), which must
  be shorter. A job lost on its last attempt is marked dead, not run again. Email passes the
  job id as the provider idempotency key (Resend honors it; SMTP does not), so a duplicate
  is possible with SMTP.
- **Periodic jobs.** Each worker's scheduler inserts one job per kind per interval with a
  unique `dedupe_key` (`periodic:<kind>:<interval bucket>`), so any number of workers
  schedule each run exactly once with no leader election: receipts every 15 minutes, purge
  every hour.
- **Worker.** `python -m app.jobs` (SIGTERM finishes running jobs, then exits). One pool
  connection per concurrent runner plus one; `WORKER_CONCURRENCY` defaults to 4. Compose
  and the smoke overlay run it as the `worker` service; its health check is a heartbeat
  file touched by the scheduler loop (liveness, like `/health`, not database health).
- **Purge** deletes in batches of 5000 using `ctid ... FOR UPDATE SKIP LOCKED`, so it never
  waits on rows requests hold. Sessions are kept 7 days after expiry or 30 days after
  revocation; refresh tokens go with their sessions (cascade); account tokens 1 day after
  expiry; idempotency records and rate-limit windows when expired.

Account work that must not shape the response (registration, resend, password reset) still
runs in a FastAPI background task after the response, as in ADR 0008, but now enqueues its
emails in the same transaction as its writes instead of sending them.

## Consequences

- Delivery needs a running worker. Without one, mail queues up (visible in `jobs`).
- Payloads can hold personal data and one-time links until delivered; they are deleted
  on success and cleared on death. Do not enqueue secrets that are not already emailed.
- Postgres load grows with job volume; this is for transactional volume, not bulk.
- Production email is `smtp` (TLS required, as before) or `resend`; `console` and
  `memory` stay development/test only.
