from __future__ import annotations

import asyncio
import gc
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from uuid import uuid4


def _approved_telegram_post(client, topic: str) -> dict:
    generated = client.post(
        "/api/posts/generate",
        json={
            "topic": topic,
            "channel": "telegram",
            "tone": "Clear",
            "objective": "Verify explicit missed-job recovery",
            "notifyTelegram": False,
        },
    )
    assert generated.status_code == 200
    post = generated.json()["post"]
    approved = client.post(
        f"/api/posts/{post['id']}/decision",
        json={"decision": "approve", "revision": post["revision"]},
    )
    assert approved.status_code == 200
    return post


def _missed_publish(client, topic: str) -> tuple[dict, dict]:
    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    post = _approved_telegram_post(client, topic)
    scheduled = client.post(
        f"/api/posts/{post['id']}/schedule",
        json={
            "revision": post["revision"],
            "runAt": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
        },
    )
    assert scheduled.status_code == 200
    assert client.put("/api/scheduler", json={"paused": False}).status_code == 200
    state = client.get("/api/state").json()
    job = next(item for item in state["jobs"] if item["id"] == scheduled.json()["job"]["id"])
    assert job["status"] == "missed"
    assert job["recoveryRequiredAt"]
    assert state["scheduler"]["recoveryPending"] >= 1
    return post, job


def test_missed_publish_requires_run_now_reschedule_or_skip(client, monkeypatch) -> None:
    from app.schemas import GeneratedContent

    async def fake_generate(*_args, **_kwargs):
        return GeneratedContent(
            title="Recovery-safe scheduled post",
            body="This exact revision waits for an explicit local decision.",
            hashtags=["#Socium", "#Recovery"],
            rationale="Exercises Phase 9 missed-job recovery.",
        )

    delivered: list[str] = []

    async def fake_publish(*_args, **_kwargs):
        delivered.append("sent")
        return f"recovery-message-{len(delivered)}"

    monkeypatch.setattr("app.services.provider.generate_content", fake_generate)
    monkeypatch.setattr("app.services.publishing.publish_telegram_post", fake_publish)
    assert client.put(
        "/api/settings/provider",
        json={
            "kind": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "model": "phase-nine-model",
            "apiKey": "phase-nine-test-key",
        },
    ).status_code == 200
    assert client.put(
        "/api/settings/telegram",
        json={"chatId": "12345", "botToken": "123456:phase-nine-token"},
    ).status_code == 200

    run_post, run_job = _missed_publish(client, "Run missed publish now")
    run_now = client.post(f"/api/jobs/{run_job['id']}/recover", json={"decision": "run_now"})
    assert run_now.status_code == 200
    assert run_now.json()["job"]["status"] == "queued"
    # Windows CI and full-suite database contention can delay one scheduler tick.
    deadline = time.monotonic() + 10
    state = run_now.json()["state"]
    while time.monotonic() < deadline:
        state = client.get("/api/state").json()
        current = next(item for item in state["posts"] if item["id"] == run_post["id"])
        if current["status"] == "published":
            break
        time.sleep(0.05)
    assert next(item for item in state["posts"] if item["id"] == run_post["id"])["status"] == "published"
    assert delivered == ["sent"]

    _reschedule_post, reschedule_job = _missed_publish(client, "Reschedule missed publish")
    new_time = datetime.now(UTC) + timedelta(hours=2)
    rescheduled = client.post(
        f"/api/jobs/{reschedule_job['id']}/recover",
        json={"decision": "reschedule", "runAt": new_time.isoformat()},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["job"]["status"] == "queued"
    assert datetime.fromisoformat(rescheduled.json()["job"]["runAt"]) == new_time
    assert delivered == ["sent"]

    from app.database import write_session
    from app.models import LocalJob
    from app.store import initialize_storage

    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    with write_session() as session:
        restart_job = session.get(LocalJob, reschedule_job["id"])
        assert restart_job is not None
        restart_job.run_at = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    initialize_storage()
    restart_state = client.get("/api/state").json()
    restart_job = next(
        item for item in restart_state["jobs"] if item["id"] == reschedule_job["id"]
    )
    assert restart_job["status"] == "missed"
    assert "not running" in restart_job["recoveryReason"]
    assert client.post(
        f"/api/jobs/{restart_job['id']}/recover", json={"decision": "skip"}
    ).status_code == 200

    _skip_post, skip_job = _missed_publish(client, "Skip missed publish")
    skipped = client.post(f"/api/jobs/{skip_job['id']}/recover", json={"decision": "skip"})
    assert skipped.status_code == 200
    assert skipped.json()["job"]["status"] == "skipped"
    assert delivered == ["sent"]
    replay = client.post(f"/api/jobs/{skip_job['id']}/recover", json={"decision": "run_now"})
    assert replay.status_code == 400

    stale_post, stale_job = _missed_publish(client, "Reject stale missed revision")
    edited = client.patch(
        f"/api/posts/{stale_post['id']}",
        json={
            "revision": stale_post["revision"],
            "title": stale_post["title"],
            "body": "A newer revision must invalidate the old missed schedule.",
            "hashtags": stale_post["hashtags"],
        },
    )
    assert edited.status_code == 200
    stale_run = client.post(f"/api/jobs/{stale_job['id']}/recover", json={"decision": "run_now"})
    assert stale_run.status_code == 400
    assert "changed" in stale_run.json()["error"]
    assert client.post(
        f"/api/jobs/{stale_job['id']}/recover", json={"decision": "skip"}
    ).status_code == 200


def test_worker_lease_rejects_stale_owner_and_recovers_expiry(client) -> None:
    from app.database import read_session, write_session
    from app.models import AppMetadata, LocalJob
    from app.store import complete_job, recover_stale_jobs, utc_now

    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    now = utc_now()
    active_id = str(uuid4())
    expired_id = str(uuid4())
    with write_session() as session:
        session.add_all(
            [
                LocalJob(
                    id=active_id,
                    kind="seo.audit",
                    status="running",
                    payload={"url": "https://lease.example"},
                    run_at=now,
                    attempts=1,
                    max_attempts=3,
                    locked_at=now,
                    lease_token="current-lease",
                    lease_expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                    created_at=now,
                    updated_at=now,
                ),
                LocalJob(
                    id=expired_id,
                    kind="seo.audit",
                    status="running",
                    payload={"url": "https://expired.example"},
                    run_at=now,
                    attempts=1,
                    max_attempts=3,
                    locked_at=now,
                    lease_token="expired-lease",
                    lease_expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )

    assert complete_job(active_id, "stale-lease") is False
    with read_session() as session:
        assert session.get(LocalJob, active_id).status == "running"  # type: ignore[union-attr]
    assert complete_job(active_id, "current-lease") is True
    assert recover_stale_jobs(stale_minutes=10) == 1
    with read_session() as session:
        recovered = session.get(LocalJob, expired_id)
        assert recovered is not None
        assert recovered.status == "queued"
        assert recovered.lease_token is None
        assert recovered.lease_expires_at is None
    with write_session() as session:
        recovered = session.get(LocalJob, expired_id)
        assert recovered is not None
        recovered.status = "cancelled"
        metadata = session.get(AppMetadata, "scheduler_paused")
        assert metadata is not None
        metadata.value = "true"


def test_bounded_worker_timeout_enters_exponential_retry(client, monkeypatch) -> None:
    from app.database import read_session, write_session
    from app.models import LocalJob
    from app.scheduler import LocalScheduler
    from app.store import utc_now

    assert client.put("/api/scheduler", json={"paused": True}).status_code == 200
    job_id = str(uuid4())
    now = utc_now()
    with write_session() as session:
        session.add(
            LocalJob(
                id=job_id,
                kind="seo.audit",
                status="running",
                payload={"url": "https://timeout.example"},
                run_at=now,
                attempts=1,
                max_attempts=3,
                locked_at=now,
                lease_token="timeout-lease",
                lease_expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                created_at=now,
                updated_at=now,
            )
        )
    worker = LocalScheduler(
        interval=0.01,
        catch_up_hours=24,
        stale_minutes=10,
        worker_timeout_seconds=0.02,
        lease_seconds=30,
    )

    async def never_finishes(_job):
        await asyncio.sleep(10)

    monkeypatch.setattr(worker, "_execute", never_finishes)
    asyncio.run(
        worker._execute_bounded(
            {"id": job_id, "kind": "seo.audit", "payload": {}, "leaseToken": "timeout-lease"}
        )
    )
    with read_session() as session:
        timed_out = session.get(LocalJob, job_id)
        assert timed_out is not None
        assert timed_out.status == "retrying"
        assert timed_out.lease_token is None
        assert "safety timeout" in str(timed_out.last_error)
        assert datetime.fromisoformat(timed_out.run_at) > datetime.now(UTC)
    with write_session() as session:
        timed_out = session.get(LocalJob, job_id)
        assert timed_out is not None
        timed_out.status = "cancelled"


def test_supervisor_is_single_worker_event_driven_and_stops_crash_loops(monkeypatch) -> None:
    import app.scheduler as scheduler_module

    async def bounded_scenario() -> tuple[int, int, int]:
        jobs = [
            {"id": "job-one", "kind": "test", "payload": {}, "leaseToken": "one"},
            {"id": "job-two", "kind": "test", "payload": {}, "leaseToken": "two"},
        ]
        active = 0
        peak = 0
        completed = 0
        worker = scheduler_module.LocalScheduler(0.01, 24, 10, worker_timeout_seconds=1)

        def claim(_lease_seconds):
            return jobs.pop(0) if jobs else None

        async def execute(_job):
            nonlocal active, peak, completed
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            completed += 1

        monkeypatch.setattr(scheduler_module, "scheduler_paused", lambda: False)
        monkeypatch.setattr(scheduler_module, "recover_stale_jobs", lambda _minutes: 0)
        monkeypatch.setattr(scheduler_module, "claim_due_job", claim)
        monkeypatch.setattr(scheduler_module, "next_job_run_at", lambda: None)
        monkeypatch.setattr(worker, "_execute", execute)
        worker.start()
        await asyncio.sleep(0.12)
        status = worker.status()
        await worker.stop()
        return peak, completed, int(status["workersActive"])

    peak, completed, active = asyncio.run(bounded_scenario())
    assert (peak, completed, active) == (1, 2, 0)

    async def crash_scenario() -> dict:
        worker = scheduler_module.LocalScheduler(0.01, 24, 10, crash_limit=3)
        monkeypatch.setattr(scheduler_module, "scheduler_paused", lambda: False)
        monkeypatch.setattr(scheduler_module, "recover_stale_jobs", lambda _minutes: 0)
        monkeypatch.setattr(scheduler_module, "claim_due_job", lambda _lease: (_ for _ in ()).throw(RuntimeError("database unavailable")))
        worker.start()
        await asyncio.sleep(0.35)
        status = worker.status()
        await worker.stop()
        return status

    crashed = asyncio.run(crash_scenario())
    assert crashed["status"] == "needs_attention"
    assert crashed["resourceMode"] == "needs_attention"
    assert crashed["crashCount"] == 3
    assert "database unavailable" in str(crashed["lastError"])


def test_idle_supervisor_wake_soak_is_coalesced_and_memory_bounded(monkeypatch) -> None:
    import app.scheduler as scheduler_module

    async def scenario() -> tuple[int, int]:
        monkeypatch.setattr(scheduler_module, "scheduler_paused", lambda: False)
        monkeypatch.setattr(scheduler_module, "recover_stale_jobs", lambda _minutes: 0)
        monkeypatch.setattr(scheduler_module, "claim_due_job", lambda _lease: None)
        monkeypatch.setattr(scheduler_module, "next_job_run_at", lambda: None)
        worker = scheduler_module.LocalScheduler(0.01, 24, 10)
        tracemalloc.start()
        worker.start()
        await asyncio.sleep(0.03)
        gc.collect()
        before = tracemalloc.get_traced_memory()[0]
        for _ in range(20_000):
            worker.wake()
        await asyncio.sleep(0.05)
        gc.collect()
        after = tracemalloc.get_traced_memory()[0]
        status = worker.status()
        await worker.stop()
        tracemalloc.stop()
        return int(status["loopIterations"]), after - before

    iterations, memory_growth = asyncio.run(scenario())
    assert iterations <= 3
    assert memory_growth < 1_000_000


def test_wake_signal_is_not_lost_between_state_check_and_idle_wait(monkeypatch) -> None:
    import app.scheduler as scheduler_module

    async def scenario() -> int:
        monkeypatch.setattr(scheduler_module, "scheduler_paused", lambda: False)
        monkeypatch.setattr(scheduler_module, "recover_stale_jobs", lambda _minutes: 0)
        monkeypatch.setattr(scheduler_module, "claim_due_job", lambda _lease: None)
        worker = scheduler_module.LocalScheduler(0.01, 24, 10)
        checks = 0

        def next_deadline():
            nonlocal checks
            checks += 1
            if checks == 1:
                worker.wake()

        monkeypatch.setattr(scheduler_module, "next_job_run_at", next_deadline)
        worker.start()
        await asyncio.sleep(0.05)
        await worker.stop()
        return checks

    assert asyncio.run(scenario()) >= 2


def test_remote_approval_listeners_sleep_without_pending_actions(monkeypatch) -> None:
    import app.poller as poller_module
    import app.slack_listener as slack_module

    telegram_calls = 0
    pending_checks = 0

    async def telegram_scenario() -> dict:
        nonlocal pending_checks, telegram_calls

        async def get_updates(*_args, **_kwargs):
            nonlocal telegram_calls
            telegram_calls += 1
            return []

        monkeypatch.setattr(
            poller_module,
            "telegram_runtime",
            lambda: {
                "polling_enabled": True,
                "bot_token": "123456:test",
                "chat_id": "12345",
                "last_update_id": 0,
            },
        )
        poller = poller_module.TelegramPoller(5)

        def no_pending_action(_transport):
            nonlocal pending_checks
            pending_checks += 1
            if pending_checks == 1:
                poller.wake()
            return 0

        monkeypatch.setattr(poller_module, "pending_approval_action_count", no_pending_action)
        monkeypatch.setattr(poller_module, "get_updates", get_updates)
        poller.start()
        await asyncio.sleep(0.03)
        status = poller.status()
        await poller.stop()
        return status

    telegram_status = asyncio.run(telegram_scenario())
    assert telegram_status["status"] == "idle"
    assert telegram_status["active"] is False
    assert telegram_calls == 0
    assert pending_checks >= 2

    slack_runtimes = [
        {
            "id": "slack-account",
            "updated_at": "2026-08-23T00:00:00Z",
            "config": {"approval_channel_id": "C123"},
            "secrets": {"bot_token": "xoxb-test", "app_token": "xapp-test"},
        },
        {
            "id": "slack-account-two",
            "updated_at": "2026-08-23T00:00:00Z",
            "config": {"approval_channel_id": "C456"},
            "secrets": {"bot_token": "xoxb-test-two", "app_token": "xapp-test-two"},
        },
    ]

    async def slack_scenario() -> tuple[dict, int]:
        monkeypatch.setattr(
            slack_module,
            "connector_runtimes",
            lambda *_args, **_kwargs: slack_runtimes,
        )
        monkeypatch.setattr(slack_module, "pending_approval_action_count", lambda _transport: 0)
        listener = slack_module.SlackSocketListener(enabled=True)
        listener.start()
        await asyncio.sleep(0.03)
        status = listener.statuses()["slack-account"]
        workers = len(listener._workers)
        await listener.stop()
        return status, workers

    slack_status, slack_workers = asyncio.run(slack_scenario())
    assert slack_status == {"active": False, "status": "idle", "lastError": None}
    assert slack_workers == 0

    async def bounded_slack_scenario() -> tuple[int, set[str]]:
        never = asyncio.Event()

        async def wait_for_action(_self, _runtime):
            await never.wait()

        monkeypatch.setattr(slack_module, "pending_approval_action_count", lambda _transport: 1)
        monkeypatch.setattr(slack_module.SlackSocketListener, "_listen", wait_for_action)
        listener = slack_module.SlackSocketListener(enabled=True)
        listener.start()
        await asyncio.sleep(0.03)
        workers = len(listener._workers)
        account_ids = set(listener._workers)
        await listener.stop()
        return workers, account_ids

    slack_workers, slack_account_ids = asyncio.run(bounded_slack_scenario())
    assert slack_workers == 1
    assert slack_account_ids == {"slack-account"}
