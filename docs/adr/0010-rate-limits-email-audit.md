# 0010 Rate limits, transactional email, audit log and enumeration resistance

**Status** Accepted

**Rate limiting** needs shared state across API instances without adding Redis. A
`RateLimitBackend` has three operations on fixed windows: `hit`, `peek` and `reset`.
The default Postgres backend does one atomic upsert per hit on `rate_limits`, using the
database clock for windows and for `Retry-After`. It runs in its own short transaction,
because a failed sign-in rolls the request back but must still count. An in-memory
backend serves tests and single-process development; the separate limiter pool is small by
design and fails closed when unavailable. Staging and production require
Postgres. Keys are the rule name plus an HMAC of the identifier, so emails and IPs are
not stored. Sign-in also has a progressive lockout per account identifier (the
submitted email, whether or not an account exists): five failures within an hour lock
it for 30 seconds, doubling to 15 minutes. A determined attacker can lock a victim out
for up to 15 minutes at a time; per-IP limits slow that down. Expired rows are not purged
yet.

**Email** goes through an `EmailBackend` (`send(email)`) chosen by `EMAIL_BACKEND`:
console in development, SMTP (stdlib `smtplib` in a worker thread, with STARTTLS or
implicit TLS) and in-memory for tests. Mailpit captures SMTP mail in Compose. Templates
are `string.Template` files with an HTML layout; values are escaped for HTML and a missing
value raises. Services queue messages on a request-scoped `Mailer`. (Superseded in part by
[ADR 0013](0013-postgres-job-queue.md): messages are now durable jobs enqueued in the
request's transaction and sent by the worker with retries, not by a background task;
backends keep the same interface, plus Resend.) Emailed links put tokens in the URL fragment so web servers and
`Referer` headers never see them.

**Audit log.** `audit_events` rows are added to the request's unit of work, so they commit
with the change they describe. Failures that must be recorded (failed sign-in, refresh
token reuse) use a `DomainError` that commits. `user_id` has no foreign key, so events
outlive a deleted account as pseudonymous records. Details hold no tokens, passwords,
email addresses or IPs; digests stand in where correlation helps.

**Enumeration resistance and account claims.** Registration, resend and reset answer
before account-dependent work in a background task. Registration always hashes the
submitted password. Unverified accounts cannot sign in, link credentials or change their
email. Registration stores the pending password hash with a verification token; a later
registration adds a separate link with its own password hash and chosen name. The newest
five links are retained; issuing another evicts the oldest, so repeated registrations
can eventually invalidate an earlier link. Verification requires both the link and the chosen password,
so opening a link from an attacker’s registration cannot activate their credential.
Claiming an unverified account also removes existing sessions, provider links and tokens.
Password reset proves inbox ownership and removes sessions and pending tokens. It removes
Google links from password accounts, while preserving linked identities on passwordless
legacy accounts. Legacy bcrypt and
unknown-account verification can still have different timing; rate limits reduce probing
but do not eliminate that difference. Background work is not durable and can be lost on
process failure.
