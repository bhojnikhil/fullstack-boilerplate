# 0007 Sign in with Google by ID token, and account linking

**Status** Accepted

The previous server-side redirect flow never checked `state` (login CSRF), put the JWT
in the redirect URL, requested offline access and stored Google access and refresh
tokens in plaintext. It also linked a Google identity to any account with the same
email, so someone who pre-registered a victim's address kept access after the victim
signed in with Google.

**Flow.** Clients obtain a Google ID token themselves: Google Identity Services on the
web, native Google sign-in on Android and iOS. They post it to `POST /v1/auth/google`.
google-auth's `verify_oauth2_token` checks the signature, issuer, expiry and that the
audience is one of the configured web, Android or iOS client IDs. Google's signing
certificates are fetched with async httpx and cached for the response's `max-age`. An
unknown key ID triggers one early refetch at most once a minute, and the last good
certificates keep working during an outage. No redirect, callback, client secret or
Google access/refresh token is involved, and the stored token columns were dropped.

**Linking rules.**

1. A Google subject that is already linked signs in to its account.
2. Otherwise Google must mark the email as verified, or nothing is created or linked.
3. A new email creates a verified account linked to the Google subject.
4. An existing account is linked automatically only if its own email is verified.
   Otherwise the response is `409 google_link_required`. The person signs in to that
   account and links Google explicitly, or resets its password first: the reset link
   proves control of the inbox, verifies the email and signs out every session,
   including an attacker's.

Explicit linking (`POST /v1/auth/google/link`) needs recent re-authentication, since a
stolen access token must not be able to add a permanent way in. One Google identity per
user. Unlinking also needs recent re-authentication and another sign-in method.
`POST /v1/auth/reauthenticate` accepts a Google ID token only if it belongs to the user's
linked identity and was issued within the re-authentication window.

**Sign in with Apple** (required on iOS when other social sign-ins are offered) is not
implemented. It would follow the same shape: a verifier in `app/integrations` for Apple's
identity tokens (JWKS from `https://appleid.apple.com/auth/keys`, audience = the app's
bundle or services ID), a new `OAuthProvider` value, and a service like
`app/modules/auth/google.py` applying the same linking rules. Apple may return a private
relay email and sends the name only on first sign-in, so the service should store the
name then and treat relay addresses as verified only when Apple says so.
