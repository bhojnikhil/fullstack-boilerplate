# 0004 Async Postgres and request transactions

**Status** Accepted

The starter needs multi-step mutations to succeed or roll back together. It also
needs database tests to exercise the driver, constraints and concurrency behavior
used by the running API.

Use SQLAlchemy's async sessions with psycopg 3. One FastAPI function-scoped session
dependency supplies the request's transaction across the dependency graph. It
commits after response preparation and before the response is sent. An exception
unwinds the transaction, including writes flushed by repositories. The PostgreSQL
test fixtures run Alembic in a new schema for each database test so API commits,
rollbacks and concurrent transactions can run through their normal code paths.

Apply migrations separately with Alembic against a direct connection. The app can
use a Neon pooled connection with psycopg's automatic prepared statements disabled.
Readiness rejects unreachable databases, missing revisions and known revisions
behind the shipped heads. It accepts the shipped heads or revisions unknown to
this image, logging the unknown revision IDs once per distinct set per process.
During a rolling deploy, a new image can advance the database while old instances
are still serving traffic. Requiring an exact head would make those instances
unready before they can be replaced. Use expand/contract migrations. Apply
backward-compatible schema changes before rolling out new code. Remove old schema
elements in a later release after all callers have stopped using them.
Unknown revision IDs cannot distinguish a newer schema from an unrelated one.
Run Alembic from the release being deployed and investigate unexpected warnings.

For authenticated mutations, a PostgreSQL transaction advisory lock serializes
attempts for the same user and idempotency key. A concurrent duplicate gets 409
while the lock is held. The business write and replay record commit atomically.
A response can be replayed for 24 hours with the same method, target, media type
and body bytes. Content-Type parameters are ignored. Failed transactions leave
the key available. The key stays scoped to the authenticated user. Public registration and login keep their existing contracts. Expired
records can be reused and can be deleted by a future periodic cleanup job.
