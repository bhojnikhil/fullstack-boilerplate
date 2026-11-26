"""Rate-limit rules for workspace endpoints (see app.core.ratelimit)."""

from datetime import timedelta

from app.core.ratelimit import Rule

WORKSPACE_CREATE_PER_ACCOUNT = Rule("workspace_create_account", 10, timedelta(hours=1))
INVITE_PER_ACCOUNT = Rule("invite_account", 20, timedelta(hours=1))
INVITE_PER_WORKSPACE = Rule("invite_workspace", 50, timedelta(days=1))
INVITE_PER_IP = Rule("invite_ip", 50, timedelta(hours=1))
INVITE_ACCEPT_PER_IP = Rule("invite_accept_ip", 30, timedelta(minutes=15))
INVITE_ACCEPT_PER_ACCOUNT = Rule("invite_accept_account", 20, timedelta(minutes=15))
