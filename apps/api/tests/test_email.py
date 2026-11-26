"""Email templates, backends and request-scoped delivery."""

from email.message import EmailMessage
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.db import RequestSession
from app.core.errors import DomainError, ErrorCode
from app.integrations import email as email_module
from app.integrations.email import (
    ConsoleEmailBackend,
    Email,
    Mail,
    MemoryEmailBackend,
    SmtpEmailBackend,
    build_email_backend,
)
from app.integrations.email.templates import Template, render
from app.modules.items.models import Item
from tests.test_http_contract import assert_error

LINKED = {
    Template.VERIFY_EMAIL,
    Template.RESET_PASSWORD,
    Template.EMAIL_CHANGE,
    Template.PASSWORD_CHANGED,
    Template.WORKSPACE_INVITATION,
}
CONTEXT = {
    "name": "<b>Ann</b> & co",
    "link": "https://web.example/auth/verify-email#token=abc&x=<1>",
    "expires": "24 hours",
    "sign_in_link": "https://web.example/auth/login",
    "reset_link": "https://web.example/auth/forgot-password",
    "inviter": "<b>Ann</b> & co",
    "workspace": "Home & <b>Garden</b>",
    "role": "member",
}


@pytest.mark.parametrize("template", list(Template))
def test_every_template_renders_text_and_escaped_html(template, config):
    subject, text, html = render(template, config, CONTEXT)
    assert config.app_name in subject
    assert "$" not in subject + text + html  # Every placeholder was filled.
    assert "<b>Ann</b> & co" in text
    assert "&lt;b&gt;Ann&lt;/b&gt; &amp; co" in html
    assert "<b>Ann</b>" not in html
    assert html.startswith("<!doctype html>")
    assert f"<title>{subject}</title>" in html
    if template in LINKED:
        assert CONTEXT["link"] in text
        assert "token=abc&amp;x=&lt;1&gt;" in html


def test_missing_values_fail_loudly(config):
    with pytest.raises(KeyError):
        render(Template.VERIFY_EMAIL, config, {"name": "Ann"})


def message(template: Template = Template.VERIFY_EMAIL) -> Email:
    return Email(template, "person@example.com", "Subject", "Text body", "<p>HTML body</p>")


async def test_console_backend_prints_the_message(capsys):
    await ConsoleEmailBackend().send(message())
    output = capsys.readouterr().out
    assert "to person@example.com" in output
    assert "Subject: Subject" in output
    assert "Text body" in output


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout, context=None) -> None:
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[tuple] = []
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append(("quit",))

    def starttls(self, context):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.mark.parametrize(
    ("security", "credentials", "calls", "ssl"),
    [
        ("none", False, [("quit",)], False),
        ("starttls", True, [("starttls",), ("login", "mailer", "s3cret"), ("quit",)], False),
        ("tls", True, [("login", "mailer", "s3cret"), ("quit",)], True),
    ],
)
async def test_smtp_backend(monkeypatch, config, security, credentials, calls, ssl):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTP)
    settings = config.model_copy(
        update={
            "smtp_host": "mail.example",
            "smtp_port": 2525,
            "smtp_security": security,
            "smtp_username": "mailer" if credentials else "",
            "smtp_password": SecretStr("s3cret" if credentials else ""),
            "email_from": "App <no-reply@example.com>",
        }
    )
    await SmtpEmailBackend(settings).send(message())

    [client] = FakeSMTP.instances
    assert (client.host, client.port, client.timeout) == ("mail.example", 2525, 10)
    assert (client.context is not None) is ssl
    assert client.calls == calls
    [sent] = client.sent
    assert sent["From"] == "App <no-reply@example.com>"
    assert sent["To"] == "person@example.com"
    assert sent["Subject"] == "Subject"
    assert sent["Message-ID"]
    assert [part.get_content_type() for part in sent.iter_parts()] == ["text/plain", "text/html"]


def test_backend_selection(config):
    assert isinstance(build_email_backend(config), MemoryEmailBackend)
    smtp = config.model_copy(update={"email_backend": "smtp"})
    assert isinstance(build_email_backend(smtp), SmtpEmailBackend)
    console = config.model_copy(update={"email_backend": "console"})
    assert isinstance(build_email_backend(console), ConsoleEmailBackend)


@pytest.fixture
def mail_routes(app):
    @app.post("/test-mail")
    async def send_mail(db: RequestSession, mail: Mail, outcome: str) -> dict[str, str]:
        mail.send(Template.EMAIL_CHANGED, "person@example.com", name="Ann")
        if outcome == "domain-error":
            raise DomainError(ErrorCode.SESSION_NOT_FOUND)
        if outcome == "commit-error":
            db.add(Item(workspace_id=uuid4(), title="violates the foreign key at commit"))
        return {"status": "ok"}


@pytest.mark.parametrize(
    ("outcome", "status", "sent"),
    [("ok", 200, 1), ("domain-error", 404, 0), ("commit-error", 500, 0)],
)
async def test_mail_is_sent_only_after_a_successful_commit(
    client, outbox, mail_routes, outcome, status, sent
):
    response = await client.post(f"/test-mail?outcome={outcome}")
    assert response.status_code == status
    if status != 200:
        assert_error(response, status, response.json()["error"]["code"])
    assert len(outbox) == sent
