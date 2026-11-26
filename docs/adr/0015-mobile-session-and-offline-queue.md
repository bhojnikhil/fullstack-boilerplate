# 0013: Mobile session binding and the offline mutation queue

## Context

The mobile app signs in with a bearer access token plus a rotating refresh token
([ADR 0008](0008-auth-tokens-and-sessions.md)), shares the transport in
`packages/api-client` ([ADR 0012](0012-api-client.md)), and must keep working offline for
item creates and edits. The foundation already fixed three rules: tokens live in one
SecureStore record, the query cache is persisted only for queries that opt in, and
mutations are never persisted.

## Decision

**Session.** `src/lib/session.ts` is the only owner of the tokens. Its state carries the
account id (`sub`) and session id (`sid`) read from the access token (unverified; the API
verifies every request). A request is sent as one session, and a refresh is requested _for
that session_. Refresh is single-flight, and the result is adopted only if nothing changed
while it was in flight (an epoch counter) and the new token has the same `sid`. A refresh
that lands on another session is never adopted and signs the device out. If the session
changed while a refresh was out (sign-out then sign-in as someone else), the api-client
refuses to replay the pending request (`SessionChangedError`). A refresh token the server
rejects (401/403) ends the session; network errors, 429 and 5xx keep it. Storage writes and
state changes happen in one serialized step, so a late refresh cannot overwrite another
account's tokens.

**Queue.** Item creates and edits are written to a persisted queue first and then sent, so
there is one code path online and offline. The queue is a closed set of mutation kinds with
plain item fields, in AsyncStorage under a per-account key. It never holds credentials: sign-in,
sign-up and password changes are never queued, and the TanStack mutation cache stays
unpersisted. Each entry gets an `Idempotency-Key` when it is created and re-sends that
exact key and workspace on every replay, so a replay after a lost response is deduplicated by
the API. Replay is FIFO and stops at the first entry that must be retried (offline, 401, 426,
429, 5xx, idempotency in progress); entries the server will never accept (404, 422, ...) are dropped and
shown to the user. It runs on reconnect, on foreground, after each enqueue and every 30 s while
non-empty. The list shown to the user is the server list with queued entries overlaid.
Deleting is online-only with an optimistic removal that rolls back on error.
Sign-out and account deletion delete the account's queue; entries of other accounts are
pruned on startup.

**Workspaces are provisional.** Phase 5 (workspaces, members, invitations) was not merged
or pushed when this was built, so those endpoints are not in the generated client.
`src/features/workspaces/workspace-api.ts` isolates an assumed contract taken from the spec.
When phase 5 lands, regenerate the client and replace that file with typed calls.

## Consequences

- A queued item edit is merged into a not-yet-sent create; editing an entry currently being
  sent is refused for a moment.
- After a create syncs, the list refetches; the item can briefly flicker.
- Push taps follow only an allowlist of in-app routes from the payload's `data.url`.
- The biometric lock is a convenience gate in the UI, not encryption: tokens stay in the OS
  keystore either way.
