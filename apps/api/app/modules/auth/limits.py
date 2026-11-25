"""Rate-limit rules for authentication endpoints.

"Account" identifiers are the submitted email (or Google subject, or user ID), so
limits and lockouts apply the same way whether or not the account exists.
"""

from datetime import timedelta

from app.core.ratelimit import Rule

LOGIN_PER_IP = Rule("login_ip", 50, timedelta(minutes=15))
LOGIN_PER_ACCOUNT = Rule("login_account", 20, timedelta(minutes=15))
REGISTER_PER_IP = Rule("register_ip", 10, timedelta(hours=1))
REGISTER_PER_ACCOUNT = Rule("register_account", 3, timedelta(hours=1))
GOOGLE_PER_IP = Rule("google_ip", 50, timedelta(minutes=15))
GOOGLE_PER_ACCOUNT = Rule("google_account", 20, timedelta(minutes=15))
PASSWORD_RESET_PER_IP = Rule("password_reset_ip", 10, timedelta(hours=1))
PASSWORD_RESET_PER_ACCOUNT = Rule("password_reset_account", 3, timedelta(hours=1))
VERIFICATION_PER_IP = Rule("verification_ip", 10, timedelta(hours=1))
VERIFICATION_PER_ACCOUNT = Rule("verification_account", 3, timedelta(hours=1))
EMAIL_CHANGE_PER_ACCOUNT = Rule("email_change_account", 3, timedelta(hours=1))
REAUTH_PER_ACCOUNT = Rule("reauth_account", 10, timedelta(minutes=15))

# Progressive lockout scopes (see app.core.ratelimit.lockout_for).
LOGIN_FAILURES = "login"
PASSWORD_CHECK_FAILURES = "password_check"
