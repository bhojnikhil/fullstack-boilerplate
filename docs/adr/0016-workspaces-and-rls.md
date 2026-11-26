# 0016 Workspaces, roles, invitations and row-level security

**Status** Accepted

**Tenancy model.** A workspace is the tenant. Users belong to workspaces through
`memberships` with one role: `owner`, `admin` or `member`. Domain data (the example
`items`) carries a `workspace_id`; tenant repositories (`app.core.tenancy.TenantRepository`)
cannot be built without it, so there is no "all workspaces" query helper.

**Signup does not create a workspace.** A new account has none; `GET /v1/workspaces`
returns an empty page and clients run an onboarding step (create a workspace or accept an
invitation). Creating one silently would give every invited user an unused personal
workspace and hide the "join or create" decision from the product. Existing items are the
exception: migration 0005 gives each user who had items a personal workspace
("Personal", USD, UTC) and moves the items into it.

**Selecting the workspace.** Domain routes take `X-Workspace-Id`; workspace-management
routes use `/v1/workspaces/{workspace_id}/...`. Both resolve through one membership check
(`WorkspaceContext(user, workspace, role)`). A missing workspace, someone else's workspace
and a malformed id give the same `404 workspace_not_found` (one query, same code path), so
existence is not revealed. A member lacking a role gets `403 insufficient_role`
(`require_role("admin")`), because members already know the workspace exists. Slugs are
globally unique and a taken one answers 409; they are not secrets.

**Permissions.** See the table in `app/modules/workspaces/service.py`. Owner-only:
role changes, ownership transfer, workspace deletion (the last two need a recent
sign-in). Admins manage invitations and plain members. Only the owner invites or removes
admins. The owner cannot leave or be removed; ownership moves by transfer.

**One owner.** Enforced three ways: the service checks under a workspace row lock; a
partial unique index allows one `owner` membership per workspace; and `workspaces`
points at its owner's membership with a deferred composite foreign key
`(id, owner_id, owner_role='owner') -> memberships(workspace_id, user_id, role)`. A
workspace therefore cannot commit without an owner, and a hand-over must change the
membership roles and `owner_id` together (tested with raw SQL).

**Row-level security.** `workspaces`, `memberships`, `invitations` and `items` have RLS
enabled and **forced**, with policies reading three per-transaction settings:
`app.user_id` (set by authentication), `app.workspace_id` (set only after membership is
proven, when a workspace is being created, or while an invitation is accepted) and
`app.invitation_hash` (the digest of the invitation being accepted, the only way to see an
invitation without belonging to its workspace). The settings are applied with
`set_config(..., true)` (`SET LOCAL`) at the start of every transaction the session
begins (`app.core.rls`), so a commit mid-request does not lose them, and a transaction
that sets nothing sees no tenant rows. The membership check sets `app.workspace_id` in the same statement that finds the
membership, so the setting exists only for members, but the policies do not rely on that:
every policy also requires that `app.user_id` belongs to the row's workspace
(`app_is_member()`), so a transaction naming someone else's workspace sees and changes
nothing. Unset, empty and (as an error) malformed settings fail closed. A membership
subquery inside the memberships policy is rejected by PostgreSQL as recursive, so
`app_is_member` is a `SECURITY DEFINER` function (pinned search path, executable by the app
role only) that reads memberships as the owner through one policy, `memberships_owner`,
that applies to the owner role alone. This is the one place FORCE does not bind the
owner; `/ready` therefore also refuses a connection by the role that owns the tables.
Bootstrap paths are narrow: a workspace can be inserted (and read back) by the user named as
its owner while its id is the active workspace, and its owner membership inserted with
role `owner` for that workspace; joining is an insert of the user's own membership with the
role of a usable invitation whose digest is in `app.invitation_hash`. The workspace row
lock taken while joining is allowed by the same invitation, but changes are not. `items`
also requires the user's membership. Roles (admin vs member) are enforced by the service,
not by RLS.

**Re-authorization under the lock.** A request authorizes against committed state, then may
wait for the workspace lock while another request removes or demotes the caller or moves
ownership. Every mutating operation therefore locks the workspace row and then reloads the
caller's membership, requiring the operation's minimum role from that fresh row
(`WorkspaceService.locked`), before it does anything; decisions (for example who may
remove an admin) use the fresh role. Tests interleave real requests to cover it.

**Database roles.** The API connects as a non-owner login role (`app_user`,
`DATABASE_URL`); migrations and test seeding run as the owner (`MIGRATION_DATABASE_URL`).
Migration 0005 creates the role as `NOLOGIN` when it does not exist (needs CREATEROLE),
refuses a role that is a superuser or has `BYPASSRLS`, grants table access and sets
default privileges for later tables. `scripts/db/bootstrap-app-role.sql` creates the
login role with a password (Compose does it on first start, `make db-bootstrap` on an
existing volume, CI before the tests); on a managed host create the role with its tools
and run `ALTER ROLE ... LOGIN PASSWORD` instead. `/ready` returns 503 in staging and
production when the connected role bypasses RLS. Foreign-key cascades (deleting a
workspace or user) run as the table owner without RLS by design. Behind a pooler, the
transaction-scoped settings need transaction pooling (pgBouncer transaction mode and
Neon's pooler both keep a transaction on one connection).

**Invitations.** 256-bit random tokens, stored as SHA-256, single use, expiring
(`INVITATION_EXPIRE_DAYS`, default 7). An email invitation is emailed through the
existing email interface and only the address's verified account can accept; a link
invitation (no email) returns the token once for a link or QR code. Every unusable token
(unknown, expired, revoked, used, wrong address) answers the same
`404 invalid_invitation`. Accept locks the user, the workspace, then the invitation row,
the same order as every other membership change, so concurrent accepts, revocations,
deletions and transfers wait instead of deadlocking. The create-invitation endpoint does not
use `Idempotency-Key` replay, because a stored response would keep a link token in clear text.
Accepting does not use replay either: a stored 200 would outlive the membership. It is
idempotent by state instead (the member who joined with the token gets the workspace again
while still a member, 404 `invalid_invitation` afterwards).
Audit events carry ids, roles and reasons only, no emails or names.

An email invitation is delivered through the job queue (ADR 0013), so its payload holds the
link, including the token, until the job succeeds (then it is deleted) or the retention purge
removes it (`job_retention_days`, stale and dead jobs alike; tested). Shareable link
invitations are never queued: the token is returned once to the admin and nowhere else.
Accepted trade-off: someone with read access to the job table can use a pending emailed
link for its short life; database read access is already close to full compromise and the
link is meant to be shared. Encrypting job payloads at rest is a future option, not built.

**Account deletion.** The hook blocks (`409 account_deletion_blocked`,
`details.reason = "sole_workspace_owner"`) while the user owns a workspace with other
members, and deletes workspaces where they are the only member. Items they authored in
other workspaces stay, with no author.
