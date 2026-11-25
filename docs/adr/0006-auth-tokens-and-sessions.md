# 0006 Auth tokens, sessions and web/mobile token transport

**Status** Accepted

The previous API issued 7-day JWTs that nothing could revoke, so signing out did not
end a session. The API now serves a web app and, later, mobile apps, which store tokens
differently.

**Sessions and tokens.** Every sign-in creates an `auth_sessions` row for one device.
Access tokens are 15-minute HMAC JWTs carrying `sub`, `sid`, `iss`, `aud`, `iat`, `exp`
and a random `jti`, with the RFC 9068 header type `at+jwt` so other JWTs are refused.
Validation tolerates 30 seconds of clock difference between instances.
Each authenticated request also loads the session, so revocation is immediate; the user
row was already loaded per request, and the session check joins into the same query.
Refresh tokens are 256-bit random strings stored as SHA-256 digests in `refresh_tokens`.
A refresh locks the token and session rows (`SELECT ... FOR UPDATE`), marks the token
used and issues a new one. A used token presented again means two parties hold the
session's tokens, so the session is revoked and `refresh_token_reused` is audited; the
revocation commits even though the response is an error. Sessions slide by 30 days on
each refresh, up to 90 days after sign-in.

There is no grace window for a lost refresh response or for two tabs refreshing at once:
a window would let a stolen token be replayed undetected. Clients must serialize
refreshes (single flight on mobile; the web client uses the Web Locks API across tabs).
A lost response signs that device out.

`JWT_SECRET_KEY` signs access tokens and is separate from `SECRET_KEY`, which keys the
server-side HMACs (IP digests, CSRF tokens, rate-limit and audit identifiers). Either can
be rotated alone: rotating the JWT key costs every client one refresh; rotating
`SECRET_KEY` changes web sessions' CSRF tokens (signing those users out) and resets
rate-limit windows. `SECRET_KEY` is
required outside development and `JWT_SECRET_KEY` in staging and production; the
repository's published values are rejected for both, even with surrounding whitespace.

**Web transport.** With `X-Platform: web`, sign-in sets the refresh token as an `HttpOnly`,
`Secure`, `SameSite=Strict` cookie scoped to `/v1/auth/refresh`, the only endpoint that
reads cookies, and returns a CSRF token in the body. A refresh with the cookie must come
from an `Origin` in `CORS_ORIGINS` and send `X-CSRF-Token`; the header must equal a
second cookie and the HMAC of the session ID (a signed double submit). Custom headers
also force a CORS preflight. The access token stays in memory, so script injection cannot
read a long-lived credential from storage. Web sign-in endpoints check `Origin` too
(login CSRF). A failed CSRF check does not clear cookies, so another site cannot sign
the user out. The cookie is host-only on the API host: the web app and API must be
same-site.

**Mobile transport.** Other clients get the refresh token in the body and send it back
in the body, so no ambient credential exists and CSRF does not apply. They keep tokens in
secure storage.

**Passwords** use argon2id through pwdlib with OWASP's minimum parameters (19 MiB,
2 iterations, 1 lane), at most four hashes at a time to bound memory. bcrypt hashes from
the previous release are verified (truncated to 72 bytes, as bcrypt 4 did) and replaced
at the next successful sign-in. New passwords are 12 to 128 characters with no
composition rules; a Have I Been Pwned check is available but off by default.

**Re-authentication.** Sessions record `authenticated_at` (sign-in or
`POST /v1/auth/reauthenticate`). Account deletion, email changes and Google linking
require it to be within `REAUTHENTICATION_MAX_AGE_MINUTES`. Password changes require the
current password instead.
