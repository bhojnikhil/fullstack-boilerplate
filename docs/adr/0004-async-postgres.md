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
Readiness requires a reachable database with the same revision heads as the
shipped migration files.

For authenticated mutations, a PostgreSQL transaction advisory lock serializes
attempts for the same user and idempotency key. A concurrent duplicate gets 409
while the lock is held. The business write and replay record commit atomically.
A response can be replayed for 24 hours with the same request bytes, and failed
transactions leave the key available. The key stays scoped to the authenticated
user. Public registration and login keep their existing contracts. Expired
records can be reused and can be deleted by a future periodic cleanup job.
