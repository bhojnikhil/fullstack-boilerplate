"""Push devices: registration API, sending through jobs, pruning, receipts."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.audit import AuditEvent
from app.core.logging import configure_logging
from app.integrations.push import DEVICE_NOT_REGISTERED, PushUnavailableError, classify_error
from app.jobs.models import Job
from app.jobs.worker import drain, run_one
from app.modules.devices.models import Device, PushTicket
from app.modules.devices.service import (
    PushPayloadError,
    enqueue_push,
    process_receipts,
    send_push,
)
from tests.conftest import bearer, create_user, sign_in

TOKEN = "ExponentPushToken[abcdefghijklmnopqrstuv]"
OTHER_TOKEN = "ExpoPushToken[0123456789ABCDEFGHIJKL]"
BODY = {"expo_push_token": TOKEN, "platform": "ios", "app_version": "1.4.0"}


async def devices(session_factory) -> list[Device]:
    async with session_factory() as db:
        return list((await db.execute(select(Device).order_by(Device.created_at))).scalars())


async def test_registration_requires_authentication(client):
    assert (await client.post("/v1/devices", json=BODY)).status_code in {401, 403}
    assert (
        await client.request("DELETE", "/v1/devices", json={"expo_push_token": TOKEN})
    ).status_code in {401, 403}


async def test_register_creates_and_refreshes_one_row_per_token(
    client, auth_headers, test_user, session_factory
):
    first = await client.post("/v1/devices", json=BODY, headers=auth_headers)
    assert first.status_code == 200
    body = first.json()
    assert body["platform"] == "ios" and body["app_version"] == "1.4.0"
    assert "expo_push_token" not in body and "user_id" not in body

    second = await client.post(
        "/v1/devices",
        json={**BODY, "app_version": "1.5.0", "platform": "android"},
        headers=auth_headers,
    )
    assert second.json()["id"] == body["id"]
    assert second.json()["app_version"] == "1.5.0"
    assert second.json()["last_seen_at"] >= body["last_seen_at"]
    [device] = await devices(session_factory)
    assert (device.user_id, device.platform, device.app_version) == (
        test_user.id,
        "android",
        "1.5.0",
    )


async def test_a_token_moves_to_the_user_who_signs_in_on_the_device(
    client, auth_headers, test_user, session_factory, config, job_context
):
    other = await create_user(session_factory, email="other@example.com")
    other_headers = bearer(await sign_in(session_factory, config, other))
    first = await client.post("/v1/devices", json=BODY, headers=auth_headers)
    await client.post("/v1/devices", json=BODY, headers=other_headers)

    # One row, owned by the new user; the previous registration is gone, not duplicated.
    [device] = await devices(session_factory)
    assert device.user_id == other.id
    assert str(device.id) != first.json()["id"]

    # The move is audited without the token.
    async with session_factory() as db:
        [event] = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.event == "device_token_reassigned")
            )
        ).scalars()
    assert event.user_id == other.id
    assert event.details["previous_user_id"] == str(test_user.id)
    assert TOKEN not in str(event.details)

    # The previous owner no longer receives pushes; the new one does.
    assert await send_push(session_factory, job_context.push, test_user.id, "t", "b", {}) == 0
    assert await send_push(session_factory, job_context.push, other.id, "t", "b", {}) == 1


async def test_refreshing_your_own_token_is_not_a_reassignment(
    client, auth_headers, session_factory
):
    await client.post("/v1/devices", json=BODY, headers=auth_headers)
    await client.post("/v1/devices", json=BODY, headers=auth_headers)
    async with session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event == "device_token_reassigned")
            )
            == 0
        )


async def test_unregister_removes_only_the_callers_token(
    client, auth_headers, session_factory, config
):
    other = await create_user(session_factory, email="other@example.com")
    other_headers = bearer(await sign_in(session_factory, config, other))
    await client.post("/v1/devices", json=BODY, headers=auth_headers)

    # Someone else cannot remove it; unknown tokens are not an error either.
    unregister = {"expo_push_token": TOKEN}
    assert (
        await client.request("DELETE", "/v1/devices", json=unregister, headers=other_headers)
    ).status_code == 204
    assert len(await devices(session_factory)) == 1

    assert (
        await client.request("DELETE", "/v1/devices", json=unregister, headers=auth_headers)
    ).status_code == 204
    assert await devices(session_factory) == []
    assert (
        await client.request("DELETE", "/v1/devices", json=unregister, headers=auth_headers)
    ).status_code == 204


@pytest.mark.parametrize(
    "override",
    [
        {"expo_push_token": "not-a-token"},
        {"expo_push_token": "ExponentPushToken[]"},
        {"expo_push_token": "ExponentPushToken[a b]"},
        {"platform": "web"},
        {"app_version": ""},
        {"app_version": "1 2"},
        {"app_version": "x" * 33},
        {"extra": "field"},
    ],
)
async def test_invalid_registrations_are_rejected(client, auth_headers, override, session_factory):
    response = await client.post("/v1/devices", json={**BODY, **override}, headers=auth_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"]
    assert await devices(session_factory) == []


async def test_deleting_the_account_row_removes_devices(
    client, auth_headers, test_user, session_factory
):
    await client.post("/v1/devices", json=BODY, headers=auth_headers)
    async with session_factory.begin() as db:
        await db.delete(await db.get(type(test_user), test_user.id))
    assert await devices(session_factory) == []


async def register_two(client, auth_headers):
    await client.post("/v1/devices", json=BODY, headers=auth_headers)
    await client.post(
        "/v1/devices",
        json={**BODY, "expo_push_token": OTHER_TOKEN, "platform": "android"},
        headers=auth_headers,
    )


async def test_push_jobs_send_to_every_device_and_record_tickets(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    async with session_factory.begin() as db:
        enqueue_push(db, test_user.id, "Hello", "World", {"screen": "items"})
    assert await drain(job_context) == 1
    sent = job_context.push.sent
    assert {m.to for m in sent} == {TOKEN, OTHER_TOKEN}
    assert {(m.title, m.body, tuple(m.data.items())) for m in sent} == {
        ("Hello", "World", (("screen", "items"),))
    }
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PushTicket)) == 2


async def test_a_rolled_back_request_sends_no_push(test_user, session_factory, job_context):
    async with session_factory() as db:
        enqueue_push(db, test_user.id, "t", "b")
        await db.flush()
        await db.rollback()
    assert await drain(job_context) == 0
    assert job_context.push.sent == []


async def test_users_without_devices_send_nothing(test_user, session_factory, job_context):
    async with session_factory.begin() as db:
        enqueue_push(db, test_user.id, "t", "b")
    assert await drain(job_context) == 1
    assert job_context.push.sent == []


async def test_unregistered_tokens_are_pruned_when_sending(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    job_context.push.unregistered.add(TOKEN)
    assert await send_push(session_factory, job_context.push, test_user.id, "t", "b", {}) == 1
    [device] = await devices(session_factory)
    assert device.expo_push_token == OTHER_TOKEN


async def test_provider_outages_retry_the_job(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    async with session_factory.begin() as db:
        enqueue_push(db, test_user.id, "t", "b")
    job_context.push.fail_with = PushUnavailableError("http_503")
    await run_one(job_context)
    async with session_factory() as db:
        job_status = await db.scalar(select(func.count()).select_from(PushTicket))
    assert job_status == 0 and job_context.push.sent == []
    from app.jobs.models import Job

    async with session_factory.begin() as db:
        row = (await db.execute(select(Job))).scalar_one()
        assert (row.status, row.attempts, row.last_error) == ("queued", 1, "PushUnavailableError")
        row.run_at = func.now()
    job_context.push.fail_with = None
    await run_one(job_context)
    assert len(job_context.push.sent) == 2


async def age_tickets(session_factory, age: timedelta) -> None:
    async with session_factory.begin() as db:
        await db.execute(update(PushTicket).values(created_at=func.now() - age))


async def test_receipts_prune_devices_that_are_gone(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    await send_push(session_factory, job_context.push, test_user.id, "t", "b", {})
    async with session_factory() as db:
        gone_ticket = await db.scalar(
            select(PushTicket.ticket_id).join(Device).where(Device.expo_push_token == TOKEN)
        )
    job_context.push.receipt_errors[gone_ticket] = DEVICE_NOT_REGISTERED

    # Too fresh: Expo needs time before receipts exist.
    assert await process_receipts(session_factory, job_context.push) == 0
    await age_tickets(session_factory, timedelta(minutes=16))
    assert await process_receipts(session_factory, job_context.push) == 1
    [device] = await devices(session_factory)
    assert device.expo_push_token == OTHER_TOKEN
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PushTicket)) == 0


async def test_other_receipt_errors_keep_the_device_and_missing_receipts_wait(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    await send_push(session_factory, job_context.push, test_user.id, "t", "b", {})
    async with session_factory() as db:
        ids = list(await db.scalars(select(PushTicket.ticket_id).order_by(PushTicket.ticket_id)))
    job_context.push.receipt_errors[ids[0]] = "MessageRateExceeded"
    job_context.push._tickets.pop(ids[1])  # Expo has no receipt (yet) for this one
    await age_tickets(session_factory, timedelta(hours=1))
    assert await process_receipts(session_factory, job_context.push) == 0
    assert len(await devices(session_factory)) == 2
    async with session_factory() as db:
        assert list(await db.scalars(select(PushTicket.ticket_id))) == [ids[1]]
    # After Expo's 24 hour retention the ticket is given up on.
    await age_tickets(session_factory, timedelta(hours=25))
    await process_receipts(session_factory, job_context.push)
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PushTicket)) == 0


async def test_receipt_job_runs_from_the_queue(session_factory, job_context):
    from app.jobs.worker import schedule_periodic

    await schedule_periodic(session_factory)
    assert await drain(job_context) == 2


async def test_sending_to_an_unknown_user_is_a_noop(session_factory, job_context):
    assert await send_push(session_factory, job_context.push, uuid4(), "t", "b", {}) == 0


@pytest.mark.parametrize(
    ("title", "body", "data"),
    [
        ("", "b", {}),
        ("t" * 101, "b", {}),
        ("t", "", {}),
        ("t", "b" * 501, {}),
        ("t", "b", {"password": "x"}),
        ("t", "b", {"screen": {"nested": 1}}),
        ("t", "b", {"screen": ["a"]}),
        ("t", "b", {"url": "x" * 600}),
    ],
)
async def test_push_content_outside_the_allowlist_is_rejected(
    test_user, session_factory, title, body, data
):
    async with session_factory() as db:
        with pytest.raises(PushPayloadError):
            enqueue_push(db, test_user.id, title, body, data)
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Job)) == 0


async def test_allowed_push_data_is_accepted(test_user, session_factory):
    async with session_factory.begin() as db:
        enqueue_push(db, test_user.id, "t", "b", {"type": "item", "screen": "items", "id": 7})


def test_error_classes():
    assert classify_error("DeviceNotRegistered") == "gone"
    assert classify_error("MessageRateExceeded") == "retry"
    assert classify_error("unknown_error") == "retry"
    for permanent in ("MessageTooBig", "InvalidCredentials", "MismatchSenderId", "Whatever"):
        assert classify_error(permanent) == "permanent"


async def queued_pushes(session_factory) -> list[Job]:
    async with session_factory() as db:
        return list(
            (
                await db.execute(
                    select(Job).where(Job.kind == "send_push").order_by(Job.created_at)
                )
            ).scalars()
        )


async def test_rate_limited_devices_are_retried_alone_with_backoff(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    job_context.push.ticket_errors[TOKEN] = "MessageRateExceeded"
    assert (
        await send_push(session_factory, job_context.push, test_user.id, "T", "B", {"id": 1}) == 1
    )
    [retry] = await queued_pushes(session_factory)
    async with session_factory() as db:
        [affected] = [d for d in await devices(session_factory) if d.expo_push_token == TOKEN]
        due = await db.scalar(select(Job.run_at > func.now()).where(Job.id == retry.id))
    assert retry.payload["device_ids"] == [str(affected.id)]
    assert retry.payload["attempt"] == 1
    assert (retry.payload["title"], retry.payload["data"]) == ("T", {"id": 1})
    assert due is True  # backed off, not immediate

    # Once the limit clears, only the affected device gets the retry.
    job_context.push.ticket_errors.clear()
    job_context.push.sent.clear()
    async with session_factory.begin() as db:
        await db.execute(update(Job).values(run_at=func.now()))
    await run_one(job_context)
    assert [m.to for m in job_context.push.sent] == [TOKEN]
    assert len(await devices(session_factory)) == 2


async def test_retries_stop_after_the_attempt_limit(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    job_context.push.ticket_errors[TOKEN] = "MessageRateExceeded"
    await send_push(session_factory, job_context.push, test_user.id, "T", "B", {}, attempt=4)
    assert await queued_pushes(session_factory) == []


@pytest.mark.parametrize("error", ["MessageTooBig", "InvalidCredentials", "MismatchSenderId"])
async def test_permanent_ticket_errors_are_dropped_and_logged_without_tokens(
    client, auth_headers, test_user, session_factory, job_context, error, capsys
):
    configure_logging("test")
    await register_two(client, auth_headers)
    job_context.push.ticket_errors[TOKEN] = error
    await send_push(session_factory, job_context.push, test_user.id, "Secret title", "B", {})
    assert await queued_pushes(session_factory) == []
    assert len(await devices(session_factory)) == 2  # the token is not at fault
    output = capsys.readouterr().err
    assert "push_permanent_error" in output and error in output
    assert TOKEN not in output and "Secret title" not in output


async def test_receipt_errors_are_handled_by_class(
    client, auth_headers, test_user, session_factory, job_context
):
    await register_two(client, auth_headers)
    third = "ExponentPushToken[zzzzzzzzzzzzzzzzzzzzzz]"
    await client.post("/v1/devices", json={**BODY, "expo_push_token": third}, headers=auth_headers)
    await send_push(session_factory, job_context.push, test_user.id, "T", "B", {"id": 2})
    async with session_factory() as db:
        rows = await db.execute(
            select(Device.expo_push_token, PushTicket.ticket_id).join(
                PushTicket, PushTicket.device_id == Device.id
            )
        )
        by_token = dict(rows.all())
    job_context.push.receipt_errors[by_token[TOKEN]] = "MessageRateExceeded"
    job_context.push.receipt_errors[by_token[OTHER_TOKEN]] = "MessageTooBig"
    await age_tickets(session_factory, timedelta(minutes=16))
    assert await process_receipts(session_factory, job_context.push) == 0
    # Transient: queued for that device alone, from the stored message. Permanent: dropped.
    [retry] = await queued_pushes(session_factory)
    assert (retry.payload["title"], retry.payload["data"], retry.payload["attempt"]) == (
        "T",
        {"id": 2},
        1,
    )
    [rate_limited] = [d for d in await devices(session_factory) if d.expo_push_token == TOKEN]
    assert retry.payload["device_ids"] == [str(rate_limited.id)]
    assert len(await devices(session_factory)) == 3
    async with session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PushTicket)) == 0
