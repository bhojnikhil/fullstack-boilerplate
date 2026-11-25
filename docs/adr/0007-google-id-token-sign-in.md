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

**Linking rules.** A linked Google subject can sign in unless its link is unconfirmed
or removed. Automatic linking to a verified local account requires an authoritative
Google address: Gmail or a Workspace hosted domain matching the email domain. A third-party address cannot create an account or auto-link an existing one; link
explicitly after local sign-in.
Legacy links on password accounts are unconfirmed until recovery or explicit relinking.
Unlinking revokes sessions created through that identity and blocks automatic relinking.
A different subject also cannot replace the tombstone automatically. An explicit link
can replace it; because only one provider row is retained per user, that replacement
removes the old subject’s tombstone.
Explicit linking and unlinking require recent authentication, and unlinking requires
another sign-in method. Google authentication time is taken from the ID token's `iat`,
including for reauthentication.

**Sign in with Apple** (required on iOS when other social sign-ins are offered) is not
implemented. It would follow the same shape: a verifier in `app/integrations` for Apple's
identity tokens (JWKS from `https://appleid.apple.com/auth/keys`, audience = the app's
bundle or services ID), a new `OAuthProvider` value, and a service like
`app/modules/auth/google.py` applying the same linking rules. Apple may return a private
relay email and sends the name only on first sign-in, so the service should store the
name then and treat relay addresses as verified only when Apple says so.
