"""Transactional email: templates, a provider interface and queued sending.

Services call ``Mailer.send``, which renders the message and enqueues a ``send_email``
job in the request's own transaction: the job exists only if the request commits, so a
rolled-back request sends nothing. The worker delivers it with retries and backoff
(docs/adr/0009-postgres-job-queue.md). Backends share one ``send`` interface; delivery
is at-least-once, so providers get a stable idempotency key per job where they support
one.
"""

import smtplib
import ssl
import sys
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Annotated, Protocol

import httpx
import structlog
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings, secret_value
from app.core.db import RequestSession
from app.integrations.email.templates import Template, render
from app.jobs.queue import enqueue

log = structlog.get_logger()


@dataclass(frozen=True)
class Email:
    template: Template
    to: str
    subject: str
    text: str
    html: str


class EmailDeliveryError(Exception):
    """The provider did not accept the message. Carries no message text or addresses."""


class EmailBackend(Protocol):
    async def send(self, email: Email, *, key: str | None = None) -> None:
        """Deliver ``email``. ``key`` is stable across retries of the same job."""


class ConsoleEmailBackend:
    """Development only: prints messages, including their links, to stdout."""

    async def send(self, email: Email, *, key: str | None = None) -> None:
        sys.stdout.write(
            f"\n----- email ({email.template}) to {email.to} -----\n"
            f"Subject: {email.subject}\n\n{email.text}\n"
            "----- end of email -----\n"
        )
        sys.stdout.flush()


class MemoryEmailBackend:
    """Keeps messages in a list. Tests read ``outbox``."""

    def __init__(self) -> None:
        self.outbox: list[Email] = []

    async def send(self, email: Email, *, key: str | None = None) -> None:
        self.outbox.append(email)


class SmtpEmailBackend:
    def __init__(self, config: Settings) -> None:
        self.config = config

    async def send(self, email: Email, *, key: str | None = None) -> None:
        await run_in_threadpool(self._send, email)

    def _send(self, email: Email) -> None:
        config = self.config
        message = EmailMessage()
        message["From"] = config.email_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Message-ID"] = make_msgid()
        message.set_content(email.text)
        message.add_alternative(email.html, subtype="html")

        context = ssl.create_default_context()
        client = (
            smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=config.smtp_timeout_seconds,
                context=context,
            )
            if config.smtp_security == "tls"
            else smtplib.SMTP(
                config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds
            )
        )
        with client:
            if config.smtp_security == "starttls":
                client.starttls(context=context)
            if config.smtp_username:
                client.login(config.smtp_username, config.smtp_password.get_secret_value())
            client.send_message(message)


class ResendEmailBackend:
    """Resend's HTTP API (https://resend.com/docs/api-reference/emails/send-email)."""

    URL = "https://api.resend.com/emails"

    def __init__(self, config: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.client = client or httpx.AsyncClient(
            timeout=config.resend_timeout_seconds, follow_redirects=False
        )

    async def send(self, email: Email, *, key: str | None = None) -> None:
        headers = {"Authorization": f"Bearer {secret_value(self.config.resend_api_key)}"}
        if key:
            headers["Idempotency-Key"] = key
        body = {
            "from": self.config.email_from,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text,
            "html": email.html,
        }
        try:
            response = await self.client.post(self.URL, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise EmailDeliveryError(type(error).__name__) from None
        if response.status_code >= 300:
            raise EmailDeliveryError(f"http_{response.status_code}")

    async def aclose(self) -> None:
        await self.client.aclose()


def build_email_backend(config: Settings) -> EmailBackend:
    if config.email_backend == "resend":
        return ResendEmailBackend(config)
    if config.email_backend == "smtp":
        return SmtpEmailBackend(config)
    if config.email_backend == "memory":
        return MemoryEmailBackend()
    return ConsoleEmailBackend()


SEND_EMAIL = "send_email"


def email_payload(email: Email) -> dict[str, object]:
    return {**asdict(email), "template": str(email.template)}


def email_from_payload(payload: dict[str, object]) -> Email:
    return Email(
        Template(str(payload["template"])),
        str(payload["to"]),
        str(payload["subject"]),
        str(payload["text"]),
        str(payload["html"]),
    )


def enqueue_email(db: AsyncSession, email: Email) -> None:
    enqueue(db, SEND_EMAIL, email_payload(email), max_attempts=8)


class MailSender(Protocol):
    def send(self, template: Template, to: str, **context: str) -> None: ...


class CollectedMail:
    """Renders and collects messages; the owner enqueues them in its own transaction."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.emails: list[Email] = []

    def send(self, template: Template, to: str, **context: str) -> None:
        subject, text, html = render(template, self.config, context)
        self.emails.append(Email(template, to, subject, text, html))

    def flush(self, db: AsyncSession) -> None:
        for email in self.emails:
            enqueue_email(db, email)
        self.emails.clear()


class Mailer:
    """Request-scoped sender: jobs are added to the request's session and commit with it."""

    def __init__(self, db: AsyncSession, config: Settings) -> None:
        self.db = db
        self.config = config

    def send(self, template: Template, to: str, **context: str) -> None:
        subject, text, html = render(template, self.config, context)
        enqueue_email(self.db, Email(template, to, subject, text, html))


def get_mailer(db: RequestSession, config: Annotated[Settings, Depends(get_settings)]) -> Mailer:
    return Mailer(db, config)


Mail = Annotated[Mailer, Depends(get_mailer)]
