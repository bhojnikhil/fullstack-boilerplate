# 0012 Expo push, S3 presigned URLs, mobile version gate and Sentry

Status: Accepted

## Decisions

**Push.** `devices` holds one row per Expo push token (unique), with the owning user,
platform, app version and `last_seen_at`. `POST /v1/devices` upserts: registering a token
that exists moves it to the signed-in user (two people sharing one phone: sign-out,
sign-in): the previous owner's row is deleted, not duplicated, so they stop receiving, and
a `device_token_reassigned` audit event records the move (new and previous user ids; never
the token). The trade-off: anyone who holds a valid session and knows another device's
token can take over that device's pushes, but an Expo token is an unguessable device
identifier, not a credential, and the takeover only redirects notifications this API sends.
`DELETE /v1/devices` takes the token in the body and removes it only for its owner;
unknown tokens are a no-op `204`. Client contract: call it before signing out, so the
next person on the phone starts clean. `send_push` jobs resolve a
user's devices, call the Expo Push API (chunks of 100, no connection held during the
call), prune tokens rejected with `DeviceNotRegistered` immediately and store ticket ids.
A periodic job exchanges tickets older than 15 minutes for receipts (chunks of 1000),
deletes devices whose receipt says `DeviceNotRegistered`, and gives up on missing receipts
after Expo's 24 hour retention. Expo being unreachable or answering 429/5xx fails the job,
so it retries. Push content is limited to what the queue stores safely: title up to 100
and body up to 500 characters, and `data` with only the keys `type`, `screen`, `id`, `url`,
string/integer/boolean values, at most 512 bytes (anything else raises `PushPayloadError`
when enqueuing). Per-device errors, in tickets and in receipts, are classified: 
`DeviceNotRegistered` deletes the device; `MessageRateExceeded` (and unreadable answers)
queue a retry for just that device with backoff, up to 5 attempts (receipt-level retries
use the message stored with the ticket for at most 24 hours); anything else
(`MessageTooBig`, `InvalidCredentials`, `MismatchSenderId`, ...) is logged by error code
and count, without tokens, and dropped. Tokens and message text are never logged. `PUSH_BACKEND` is `log` (default;
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
`android` and whose `X-App-Version` is below the minimum, missing or malformed (builds that predate the
header must update too). Web and unidentified clients are never gated, and neither are
`/v1/meta` and the probes. It is a courtesy for old builds, not authentication. Only the numeric `major.minor.patch` is compared; a
`-suffix` is ignored. The default minimum `0.0.0` gates nobody.

**Sentry.** `sentry-sdk` 3.x, initialised in the API and the worker only when `SENTRY_DSN`
is set (otherwise it is not even imported). Release (`SENTRY_RELEASE`, default
`api@<version>`), environment (`ENV`) and a `service` tag are set. Sentry 3 replaced
`send_default_pii` with `data_collection`: user info, cookies, headers, request bodies,
query strings, DB query data and local variables are all switched off, breadcrumbs are
disabled, and a `before_send` hook removes any `request`, `user`, `extra` and frame `vars`
that remain. Exception messages can echo personal data (a database error with its
parameters, a provider error with an address), so by default only the exception type is
sent; `SENTRY_INCLUDE_EXCEPTION_MESSAGES=true` sends them after redacting addresses,
bearer/JWT tokens, URL query strings and long hex/base64-like strings. Log messages are
always redacted. Redaction is pattern-based and best effort.
`SENTRY_TRACES_SAMPLE_RATE` defaults to 0.
