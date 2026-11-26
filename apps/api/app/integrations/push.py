"""Expo push notifications: a provider interface, the Expo HTTP client and fakes.

Tokens and message text are never logged. Sending returns one ticket per message
(in order); the ticket id is later exchanged for a receipt, which says whether the
push service could hand the message to FCM/APNs and whether the device is gone.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

import httpx
import structlog

from app.core.config import Settings, secret_value

log = structlog.get_logger()

EXPO_SEND_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
# Documented Expo limits: 100 messages per send request, 1000 ids per receipts request.
MAX_MESSAGES_PER_REQUEST = 100
MAX_RECEIPTS_PER_REQUEST = 1000
EXPO_TOKEN_PATTERN = re.compile(r"(?:Expo|Exponent)PushToken\[[A-Za-z0-9_-]{1,100}\]")
DEVICE_NOT_REGISTERED = "DeviceNotRegistered"


# How a ticket or receipt error is handled (https://docs.expo.dev/push-notifications/sending-notifications/):
# "gone": the token is dead, delete the device. "retry": transient (rate limited or an
# unreadable answer), send again later to that device only. "permanent": retrying cannot
# help (MessageTooBig, InvalidCredentials, MismatchSenderId, ...): give up and log the code.
RETRYABLE_ERRORS = frozenset({"MessageRateExceeded", "unknown_error"})


def classify_error(error: str) -> Literal["gone", "retry", "permanent"]:
    if error == DEVICE_NOT_REGISTERED:
        return "gone"
    return "retry" if error in RETRYABLE_ERRORS else "permanent"


class PushUnavailableError(Exception):
    """The push service did not accept the request; retry later."""


@dataclass(frozen=True)
class PushMessage:
    to: str
    title: str
    body: str
    data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Ticket:
    """Outcome of handing one message to the push service."""

    # Set when accepted; exchanged for a receipt later.
    id: str | None = None
    # Set when rejected, e.g. DeviceNotRegistered.
    error: str | None = None


@dataclass(frozen=True)
class Receipt:
    ok: bool
    error: str | None = None


class PushBackend(Protocol):
    async def send(self, messages: Sequence[PushMessage]) -> list[Ticket]: ...

    async def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]: ...


class LogPushBackend:
    """Development default: records that a push would have gone out, nothing else."""

    async def send(self, messages: Sequence[PushMessage]) -> list[Ticket]:
        log.info("push_not_sent", reason="PUSH_BACKEND=log", count=len(messages))
        return [Ticket() for _ in messages]

    async def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        return {}


class MemoryPushBackend:
    """Tests: keeps what was sent; ``unregistered`` tokens are rejected like Expo does."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []
        self.unregistered: set[str] = set()
        # token -> ticket error code (e.g. "MessageRateExceeded"), cleared by the test.
        self.ticket_errors: dict[str, str] = {}
        self.receipt_errors: dict[str, str] = {}
        self.fail_with: Exception | None = None
        self._tickets: dict[str, str] = {}

    async def send(self, messages: Sequence[PushMessage]) -> list[Ticket]:
        if self.fail_with is not None:
            raise self.fail_with
        tickets = []
        for message in messages:
            if message.to in self.unregistered:
                tickets.append(Ticket(error=DEVICE_NOT_REGISTERED))
                continue
            if message.to in self.ticket_errors:
                tickets.append(Ticket(error=self.ticket_errors[message.to]))
                continue
            self.sent.append(message)
            ticket_id = f"ticket-{len(self._tickets)}"
            self._tickets[ticket_id] = message.to
            tickets.append(Ticket(id=ticket_id))
        return tickets

    async def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        if self.fail_with is not None:
            raise self.fail_with
        found: dict[str, Receipt] = {}
        for ticket_id in ticket_ids:
            if ticket_id in self.receipt_errors:
                found[ticket_id] = Receipt(ok=False, error=self.receipt_errors[ticket_id])
            elif ticket_id in self._tickets:
                found[ticket_id] = Receipt(ok=True)
        return found


class ExpoPushBackend:
    def __init__(self, config: Settings, client: httpx.AsyncClient | None = None) -> None:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token := secret_value(config.expo_access_token):
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.AsyncClient(
            headers=headers,
            timeout=config.expo_push_timeout_seconds,
            follow_redirects=False,
        )

    async def _post(self, url: str, body: object) -> dict[str, object]:
        try:
            response = await self.client.post(url, json=body)
        except httpx.HTTPError as error:
            raise PushUnavailableError(type(error).__name__) from None
        # 429 and 5xx are transient. Other 4xx mean the request itself is wrong, which
        # retrying cannot fix, but failing loudly (and retrying a few times) is still
        # right: it surfaces a bad access token or a changed API.
        if response.status_code != 200:
            raise PushUnavailableError(f"http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise PushUnavailableError("invalid_json") from None
        if not isinstance(payload, dict):
            raise PushUnavailableError("invalid_response")
        return payload

    async def send(self, messages: Sequence[PushMessage]) -> list[Ticket]:
        tickets: list[Ticket] = []
        for start in range(0, len(messages), MAX_MESSAGES_PER_REQUEST):
            chunk = messages[start : start + MAX_MESSAGES_PER_REQUEST]
            payload = await self._post(
                EXPO_SEND_URL,
                [
                    {
                        "to": m.to,
                        "title": m.title,
                        "body": m.body,
                        "data": m.data,
                        "sound": "default",
                    }
                    for m in chunk
                ],
            )
            data = payload.get("data")
            if not isinstance(data, list) or len(data) != len(chunk):
                raise PushUnavailableError("ticket_count_mismatch")
            tickets.extend(parse_ticket(item) for item in data)
        return tickets

    async def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        found: dict[str, Receipt] = {}
        for start in range(0, len(ticket_ids), MAX_RECEIPTS_PER_REQUEST):
            chunk = list(ticket_ids[start : start + MAX_RECEIPTS_PER_REQUEST])
            payload = await self._post(EXPO_RECEIPTS_URL, {"ids": chunk})
            data = payload.get("data")
            if not isinstance(data, dict):
                raise PushUnavailableError("invalid_response")
            for ticket_id, item in data.items():
                found[ticket_id] = parse_receipt(item)
        return found

    async def aclose(self) -> None:
        await self.client.aclose()


def error_code(item: dict[str, object]) -> str:
    details = item.get("details")
    if isinstance(details, dict) and isinstance(details.get("error"), str):
        return str(details["error"])
    return "unknown_error"


def parse_ticket(item: object) -> Ticket:
    if isinstance(item, dict) and item.get("status") == "ok" and isinstance(item.get("id"), str):
        return Ticket(id=str(item["id"]))
    return Ticket(error=error_code(item) if isinstance(item, dict) else "unknown_error")


def parse_receipt(item: object) -> Receipt:
    if isinstance(item, dict) and item.get("status") == "ok":
        return Receipt(ok=True)
    return Receipt(ok=False, error=error_code(item) if isinstance(item, dict) else "unknown_error")


def build_push_backend(config: Settings) -> PushBackend:
    if config.push_backend == "expo":
        return ExpoPushBackend(config)
    if config.push_backend == "memory":
        return MemoryPushBackend()
    return LogPushBackend()
