"""Transactional email: templates, a provider interface and request-scoped sending.

Services call ``Mailer.send``. Messages are delivered by a background task after the
response is sent, which only happens after the request's transaction commits, so
a rolled-back request sends nothing. Sending after the response also keeps
delivery time out of responses that must not reveal whether an account exists.
Phase 6 replaces the background task with a durable job queue; backends keep the
same ``send`` interface.
"""

import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Annotated, Protocol

import structlog
from fastapi import BackgroundTasks, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.integrations.email.templates import Template, render

log = structlog.get_logger()


@dataclass(frozen=True)
class Email:
    template: Template
    to: str
    subject: str
    text: str
    html: str


class EmailBackend(Protocol):
    async def send(self, email: Email) -> None: ...


class ConsoleEmailBackend:
    """Development only: prints messages, including their links, to stdout."""

    async def send(self, email: Email) -> None:
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

    async def send(self, email: Email) -> None:
        self.outbox.append(email)


class SmtpEmailBackend:
    def __init__(self, config: Settings) -> None:
        self.config = config

    async def send(self, email: Email) -> None:
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


def build_email_backend(config: Settings) -> EmailBackend:
    if config.email_backend == "smtp":
        return SmtpEmailBackend(config)
    if config.email_backend == "memory":
        return MemoryEmailBackend()
    return ConsoleEmailBackend()


async def deliver(backend: EmailBackend, email: Email) -> None:
    try:
        await backend.send(email)
    except Exception:
        # The structured traceback omits exception messages, which can contain addresses.
        log.exception("email_delivery_failed", template=email.template)


class MailSender(Protocol):
    def send(self, template: Template, to: str, **context: str) -> None: ...


class CollectedMail:
    """Renders and collects messages; the owner delivers them after its commit."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self.emails: list[Email] = []

    def send(self, template: Template, to: str, **context: str) -> None:
        subject, text, html = render(template, self.config, context)
        self.emails.append(Email(template, to, subject, text, html))


class Mailer:
    def __init__(self, backend: EmailBackend, config: Settings, tasks: BackgroundTasks) -> None:
        self.backend = backend
        self.config = config
        self.tasks = tasks

    def send(self, template: Template, to: str, **context: str) -> None:
        subject, text, html = render(template, self.config, context)
        self.tasks.add_task(deliver, self.backend, Email(template, to, subject, text, html))


def get_mailer(
    request: Request,
    tasks: BackgroundTasks,
    config: Annotated[Settings, Depends(get_settings)],
) -> Mailer:
    return Mailer(request.app.state.email_backend, config, tasks)


Mail = Annotated[Mailer, Depends(get_mailer)]
