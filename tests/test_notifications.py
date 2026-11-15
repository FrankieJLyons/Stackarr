import httpx
import pytest

from stackarr.config import Config
from stackarr.notifications import Notifications
from stackarr.store import Store


def configured(tmp_path):
    store = Store(tmp_path)
    config = Config()
    config.maintenance.notification_url = "https://notify.example/synthetic-secret"
    config.maintenance.notifications_enabled = True
    config.integrations["sonarr"].mode = "install"
    config.integrations["sonarr"].enabled = True
    store.save(config, 1)
    return store


@pytest.mark.asyncio
async def test_bounded_retries_survive_restart_and_redact_failures(tmp_path):
    store = configured(tmp_path)
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ConnectError("secret transport detail")

    notices = Notifications(store, httpx.MockTransport(fail))
    notices.observe("sonarr", "unavailable")
    await notices.deliver(now=100)
    notices = Notifications(Store(tmp_path), httpx.MockTransport(fail))
    notices.observe("sonarr", "unavailable")
    await notices.deliver(now=101)
    assert len(calls) == 1
    await notices.deliver(now=200)
    await notices.deliver(now=400)
    await notices.deliver(now=1000)
    assert len(calls) == 3 and notices.rows()[0]["delivery"] == "failed"
    assert "secret transport detail" not in str(notices.rows()) + str(store.audit_rows())


@pytest.mark.asyncio
async def test_initial_healthy_is_quiet_and_disabling_cancels_pending(tmp_path):
    store = configured(tmp_path)
    notices = Notifications(store)
    notices.observe("sonarr", "ready")
    assert notices.rows() == []
    notices.observe("sonarr", "unavailable")
    revision, config = store.config()
    config.maintenance.notifications_enabled = False
    store.save(config, revision)
    await notices.deliver(now=100)
    assert notices.rows() == []


@pytest.mark.asyncio
async def test_test_message_does_not_include_private_settings(tmp_path):
    store = configured(tmp_path)

    def sent(request):
        assert b"synthetic-secret" not in request.content
        assert b'"state":"test"' in request.content
        return httpx.Response(204)

    notices = Notifications(store, httpx.MockTransport(sent))
    notices.test()
    await notices.deliver(now=100)
    assert notices.rows()[0]["delivery"] == "sent"


@pytest.mark.asyncio
async def test_interrupted_final_attempt_is_not_replayed(tmp_path):
    store = configured(tmp_path)
    notices = Notifications(store)
    notices.test()
    with store.db() as db:
        db.execute("UPDATE notification_outbox SET attempts=3")
    await notices.deliver(now=100)
    assert notices.rows()[0]["delivery"] == "failed"
