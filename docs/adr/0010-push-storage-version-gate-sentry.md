# 0010 Expo push, S3 presigned URLs, mobile version gate and Sentry

Status: Accepted

## Decisions

**Push.** `devices` holds one row per Expo push token (unique), with the owning user,
platform, app version and `last_seen_at`. `POST /v1/devices` upserts: registering a token
that exists moves it to the signed-in user (the same phone, a new account). `DELETE
/v1/devices` takes the token in the body and removes it only for its owner; unknown tokens
are a no-op `204`. The client should call it on sign-out. `send_push` jobs resolve a
user's devices, call the Expo Push API (chunks of 100, no connection held during the
call), prune tokens rejected with `DeviceNotRegistered` immediately and store ticket ids.
A periodic job exchanges tickets older than 15 minutes for receipts (chunks of 1000),
deletes devices whose receipt says `DeviceNotRegistered`, and gives up on missing receipts
after Expo's 24 hour retention. Expo being unreachable or answering 429/5xx fails the job,
so it retries. Tokens and message text are never logged. `PUSH_BACKEND` is `log` (default;
logs counts only), `expo` or `memory`. A retry after a partial failure can send a duplicate.

**Storage.** An `ObjectStorage` interface with presigned PUT/GET URLs. `S3Storage` signs
with AWS Signature Version 4 using the standard library instead of adding boto3 (a large
dependency for two operations); the signer is checked against AWS's published example
signature in the tests. Path-style URLs (`https://endpoint/bucket/key`) work for S3, R2 and
MinIO. The upload URL signs the exact `Content-Type` and `Content-Length` the client
declared, so the store rejects a different type or size; the API rejects types outside
`STORAGE_ALLOWED_CONTENT_TYPES` (exact match, no wildcards), sizes outside
`1..STORAGE_MAX_UPLOAD_BYTES` and unsafe keys before signing. URLs live for
`STORAGE_URL_EXPIRE_SECONDS` (600). No endpoint uses it yet; `MemoryStorage` is the test
double and `STORAGE_BACKEND` defaults to `disabled`.

**Version gate.** `GET /v1/meta` returns `min_supported_app_version` and
`latest_app_version` from `MIN_SUPPORTED_APP_VERSION` / `LATEST_APP_VERSION`. A middleware
answers `426` with code `app_update_required` (and `details.min_supported_app_version`) for
`/v1/*` requests (except `/v1/meta` and CORS preflights) whose `X-Platform` is `ios` or
`android` and whose `X-App-Version` is below the minimum. Web, unidentified clients and
mobile clients with a missing or unparseable version are not gated: it is a courtesy for
old builds, not authentication. Only the numeric `major.minor.patch` is compared; a
`-suffix` is ignored. The default minimum `0.0.0` gates nobody.

**Sentry.** `sentry-sdk` 3.x, initialised in the API and the worker only when `SENTRY_DSN`
is set (otherwise it is not even imported). Release (`SENTRY_RELEASE`, default
`api@<version>`), environment (`ENV`) and a `service` tag are set. Sentry 3 replaced
`send_default_pii` with `data_collection`: user info, cookies, headers, request bodies,
query strings, DB query data and local variables are all switched off, breadcrumbs are
disabled, and a `before_send` hook removes any `request`, `user`, `extra` and frame `vars`
that remain. Exception messages are still sent, so do not put personal data in them.
`SENTRY_TRACES_SAMPLE_RATE` defaults to 0.
