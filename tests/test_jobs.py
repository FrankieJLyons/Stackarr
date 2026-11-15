import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from stackarr.jobs import Jobs
from stackarr.store import Conflict, Store


def test_duplicate_operations_share_one_job(tmp_path):
    jobs = Jobs(Store(tmp_path))
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: jobs.enqueue("refresh"), range(10)))
    assert len(set(ids)) == 1
    jobs.cancel(ids[0])
    assert jobs.rows()[0]["state"] == "cancelled"
    with pytest.raises(Conflict):
        jobs.cancel(ids[0])


@pytest.mark.asyncio
async def test_restart_retry_budget_and_no_external_write_kinds(tmp_path):
    store = Store(tmp_path)
    jobs = Jobs(store)
    identity = jobs.enqueue("refresh")

    async def interrupted():
        raise asyncio.CancelledError()

    for attempt in range(3):
        with pytest.raises(asyncio.CancelledError):
            await jobs.run_one({"refresh": interrupted})
        jobs = Jobs(Store(tmp_path))
        row = next(row for row in jobs.rows() if row["id"] == identity)
        assert row["attempts"] == attempt + 1
        assert row["state"] == ("failed" if attempt == 2 else "queued")
    assert not await jobs.run_one({"refresh": interrupted})
    with pytest.raises(ValueError):
        jobs.enqueue("install")


@pytest.mark.asyncio
async def test_results_audit_and_errors_are_sanitized(tmp_path):
    store = Store(tmp_path)
    jobs = Jobs(store)
    identity = jobs.enqueue("refresh")

    async def fail():
        raise ValueError("private password and internal address")

    await jobs.run_one({"refresh": fail})
    assert jobs.rows()[0]["state"] == "failed"
    assert "private password" not in str(jobs.rows()) + str(store.audit_rows())
    assert any(row["app"] == identity and row["event"] == "job.failed" for row in store.audit_rows())

    async def succeed():
        return None

    jobs.enqueue("refresh")
    await jobs.run_one({"refresh": succeed})
    assert jobs.rows()[0]["state"] == "succeeded"
