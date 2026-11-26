"""Email templates: a subject, a plain-text body and an HTML fragment per template.

Files use ``string.Template`` placeholders (``$name``); a missing value raises. Values
are HTML-escaped before they are put into the HTML part. Every template also gets
``$app_name``.
"""

import html
from collections.abc import Mapping
from enum import StrEnum
from functools import cache
from pathlib import Path
from string import Template as Text

from app.core.config import Settings

DIRECTORY = Path(__file__).parent


class Template(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    EMAIL_CHANGE = "email_change"
    EMAIL_CHANGE_REQUESTED = "email_change_requested"
    GOOGLE_LINKED = "google_linked"
    EMAIL_CHANGED = "email_changed"
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_EXISTS = "account_exists"
    ACCOUNT_DELETED = "account_deleted"
    WORKSPACE_INVITATION = "workspace_invitation"


SUBJECTS = {
    Template.VERIFY_EMAIL: "Confirm your email address for $app_name",
    Template.RESET_PASSWORD: "Reset your $app_name password",
    Template.EMAIL_CHANGE: "Confirm your new email address for $app_name",
    Template.EMAIL_CHANGE_REQUESTED: "Email change requested for $app_name",
    Template.GOOGLE_LINKED: "Google sign-in linked to $app_name",
    Template.EMAIL_CHANGED: "Your $app_name email address was changed",
    Template.PASSWORD_CHANGED: "Your $app_name password was changed",
    Template.ACCOUNT_EXISTS: "You already have a $app_name account",
    Template.ACCOUNT_DELETED: "Your $app_name account was deleted",
    Template.WORKSPACE_INVITATION: "You are invited to join a workspace on $app_name",
}


@cache
def load(name: str) -> Text:
    return Text((DIRECTORY / name).read_text(encoding="utf-8"))


def render(
    template: Template, config: Settings, context: Mapping[str, str]
) -> tuple[str, str, str]:
    """Return (subject, text, html)."""
    values = {"app_name": config.app_name, **context}
    subject = Text(SUBJECTS[template]).substitute(values)
    text = load(f"{template}.txt").substitute(values)
    escaped = {key: html.escape(value, quote=True) for key, value in values.items()}
    body = load(f"{template}.html").substitute(escaped)
    document = load("layout.html").substitute(
        subject=html.escape(subject), app_name=escaped["app_name"], body=body
    )
    return subject, text, document
