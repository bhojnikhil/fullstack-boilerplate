# ADR 0018: API conventions

Status: Accepted

**Context.** Web, mobile and generated clients depend on behaviour that is easy to vary
module by module. v2 fixes it once so new modules copy it instead of re-deciding.

**Decision.**

- Errors are `{"error": {"code", "message", "details"}}`. Clients branch on `code` and, where
  present, `details.reason`, never on `message` (messages are for people and may change).
  Example: `account_deletion_blocked` with `details.reason == "sole_workspace_owner"`.
- Services raise `DomainError`; only the exception handlers know about HTTP.
- One transaction per request through `RequestSession`; repositories flush, never commit.
  Jobs and idempotency records are written in that transaction.
- Instants are `timestamptz` in UTC; calendar dates are `date`, interpreted in the
  workspace timezone. Money is integer minor units plus an ISO 4217 code. No floats.
- Lists use opaque keyset cursors (`limit` max 100, `next_cursor` null on the last page).
- Mutations accept `Idempotency-Key`; replays last 24 hours.
- Tenant data is reached only through `TenantRepository` with a workspace id, behind RLS
  ([ADR 0016](0016-workspaces-and-rls.md)); non-members get 404.
- The OpenAPI schema is the contract; `make gen-client` output is committed and checked
  for drift ([ADR 0012](0012-api-client.md)).

**Consequences.** New modules are reviewable against a short checklist (README "Adding a
new domain module"). Changing a public error `code` is a breaking change for clients.
