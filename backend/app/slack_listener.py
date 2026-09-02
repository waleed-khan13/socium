from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.approval_actions import apply_remote_approval_action
from app.connector_store import connector_runtimes
from app.errors import AppError, ExternalServiceError
from app.services.slack import open_socket_url, send_approval_message, send_decision_feedback
from app.store import (
    create_approval_action,
    fail_approval_delivery,
    pending_approval_action_count,
    record_approval_sent,
)


@dataclass(frozen=True, slots=True)
class SlackInteractionResult:
    channel_id: str
    user_id: str
    message: str
    action_id: str = ""
    action: str = ""


def _payload_id(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def process_slack_interaction(
    payload: dict[str, Any],
    expected_channel_id: str,
) -> SlackInteractionResult | None:
    if payload.get("type") != "block_actions":
        return None
    channel_id = _payload_id(payload, "channel")
    user_id = _payload_id(payload, "user")
    actions = payload.get("actions")
    if not channel_id or not user_id or not isinstance(actions, list):
        return None
    action = next(
        (
            item
            for item in actions
            if isinstance(item, dict)
            and item.get("action_id")
            in {
                "socium_approve",
                "socium_regenerate",
                "socium_regenerate_post",
                "socium_regenerate_image",
                "socium_edit",
                "socium_skip",
            }
        ),
        None,
    )
    if action is None:
        return None
    if channel_id != expected_channel_id:
        return SlackInteractionResult(
            channel_id=channel_id,
            user_id=user_id,
            message="This channel is not authorized for Socium approvals.",
        )

    raw_value = str(action.get("value") or "")
    parts = raw_value.split(":")
    if len(parts) != 3 or parts[0] != "sa" or parts[1] not in {"a", "r", "p", "i", "e", "s"}:
        return SlackInteractionResult(channel_id, user_id, "Unknown Socium approval action.")
    action_names = {
        "a": "approve",
        "r": "regenerate_post",
        "p": "regenerate_post",
        "i": "regenerate_image",
        "e": "edit",
        "s": "skip",
    }
    return SlackInteractionResult(
        channel_id,
        user_id,
        "",
        action_id=parts[2],
        action=action_names[parts[1]],
    )


class SlackSocketListener:
    def __init__(self, enabled: bool = True, broker_url: str = "") -> None:
        self.enabled = enabled
        self.broker_url = broker_url.rstrip("/")
        self._supervisor: asyncio.Task[None] | None = None
        self._workers: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._statuses: dict[str, dict[str, Any]] = {}
        self._status_lock = Lock()
        self._wake_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def statuses(self) -> dict[str, dict[str, Any]]:
        with self._status_lock:
            return {account_id: dict(status) for account_id, status in self._statuses.items()}

    def start(self) -> None:
        if not self.enabled:
            return
        if self._supervisor is None or self._supervisor.done():
            self._loop = asyncio.get_running_loop()
            self._supervisor = asyncio.create_task(
                self._run_supervisor(),
                name="slack-socket-supervisor",
            )

    def wake(self) -> None:
        if self.enabled and self._loop is not None:
            self._loop.call_soon_threadsafe(self._wake_event.set)

    async def stop(self) -> None:
        supervisor, self._supervisor = self._supervisor, None
        if supervisor is not None:
            supervisor.cancel()
            with suppress(asyncio.CancelledError):
                await supervisor
        workers = [task for _, task in self._workers.values()]
        self._workers.clear()
        for task in workers:
            task.cancel()
        for task in workers:
            with suppress(asyncio.CancelledError):
                await task
        with self._status_lock:
            for status in self._statuses.values():
                status.update({"active": False, "status": "stopped"})
        self._loop = None

    async def _run_supervisor(self) -> None:
        while True:
            self._wake_event.clear()
            self._sync_workers()
            await self._wake_event.wait()

    def _sync_workers(self) -> None:
        available_items = connector_runtimes("slack", verified_only=True)
        available = {item["id"]: item for item in available_items}
        runtimes = (
            {available_items[0]["id"]: available_items[0]}
            if available_items and pending_approval_action_count("slack") > 0
            else {}
        )
        for account_id, (fingerprint, task) in list(self._workers.items()):
            runtime = runtimes.get(account_id)
            next_fingerprint = str(runtime.get("updated_at") or "") if runtime else ""
            if task.done() or runtime is None or fingerprint != next_fingerprint:
                if not task.done():
                    task.cancel()
                self._workers.pop(account_id, None)
                self._set_status(account_id, False, "idle" if account_id in available else "stopped", None)

        for account_id, runtime in runtimes.items():
            if account_id in self._workers:
                continue
            fingerprint = str(runtime.get("updated_at") or "")
            self._set_status(account_id, False, "starting", None)
            task = asyncio.create_task(
                self._listen(runtime),
                name=f"slack-socket-{account_id[:8]}",
            )
            task.add_done_callback(lambda _task: self._wake_event.set())
            self._workers[account_id] = (fingerprint, task)

        active_ids = set(runtimes)
        with self._status_lock:
            for account_id in set(self._statuses) - active_ids - set(self._workers):
                self._statuses.pop(account_id, None)
        if not runtimes:
            for account_id in available:
                self._set_status(account_id, False, "idle", None)

    async def _listen(self, runtime: dict[str, Any]) -> None:
        account_id = str(runtime["id"])
        secrets = runtime["secrets"]
        config = runtime["config"]
        bot_token = str(secrets.get("bot_token") or "")
        app_token = str(secrets.get("app_token") or "")
        channel_id = str(config.get("approval_channel_id") or "")
        if str(config.get("transport") or "") == "broker-relay":
            await self._listen_relay(runtime, bot_token, channel_id)
            return
        backoff = 2
        try:
            while True:
                self._set_status(account_id, False, "connecting", None)
                try:
                    socket_url = await open_socket_url(app_token)
                    async with connect(
                        socket_url,
                        open_timeout=10,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=1_000_000,
                    ) as websocket:
                        self._set_status(account_id, True, "listening", None)
                        backoff = 2
                        async for raw_message in websocket:
                            reconnect = await self._handle_envelope(
                                websocket,
                                raw_message,
                                bot_token,
                                channel_id,
                                account_id,
                            )
                            if reconnect:
                                break
                except asyncio.CancelledError:
                    raise
                except ExternalServiceError as error:
                    self._set_status(account_id, False, "retrying", error.message)
                except (ConnectionClosed, OSError):
                    self._set_status(
                        account_id,
                        False,
                        "retrying",
                        "Slack Socket Mode connection closed; retrying locally.",
                    )
                except Exception:  # noqa: BLE001 - keep the long-running local listener recoverable.
                    self._set_status(
                        account_id,
                        False,
                        "retrying",
                        "Slack approval listener hit an unexpected error.",
                    )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        except asyncio.CancelledError:
            self._set_status(account_id, False, "stopped", None)
            raise

    async def _handle_envelope(
        self,
        websocket: ClientConnection,
        raw_message: str | bytes,
        bot_token: str,
        expected_channel_id: str,
        account_id: str,
    ) -> bool:
        try:
            envelope = json.loads(raw_message)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(envelope, dict):
            return False
        envelope_id = envelope.get("envelope_id")
        if isinstance(envelope_id, str) and envelope_id:
            await websocket.send(json.dumps({"envelope_id": envelope_id}))
        if envelope.get("type") == "disconnect":
            return True
        payload = envelope.get("payload")
        if envelope.get("type") != "interactive" or not isinstance(payload, dict):
            return False
        result = process_slack_interaction(payload, expected_channel_id)
        if result is None:
            return False
        await self._apply_interaction(result, bot_token, expected_channel_id, account_id)
        self._wake_event.set()
        return False

    async def _listen_relay(
        self,
        runtime: dict[str, Any],
        bot_token: str,
        expected_channel_id: str,
    ) -> None:
        account_id = str(runtime["id"])
        relay_token = str(runtime["secrets"].get("relay_token") or "")
        if not self.broker_url or not relay_token:
            self._set_status(account_id, False, "retrying", "Slack one-click relay is not configured.")
            return
        backoff = 2
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                while True:
                    self._set_status(account_id, True, "listening", None)
                    try:
                        response = await client.post(
                            f"{self.broker_url}/v1/slack/actions/poll",
                            json={"relayToken": relay_token},
                        )
                        payload = response.json()
                        if not response.is_success or not isinstance(payload, dict):
                            raise ExternalServiceError("Slack approval relay rejected the local listener.")
                        action = payload.get("action")
                        if not isinstance(action, dict):
                            await asyncio.sleep(3)
                            backoff = 2
                            continue
                        interaction = action.get("payload")
                        result = (
                            process_slack_interaction(interaction, expected_channel_id)
                            if isinstance(interaction, dict)
                            else None
                        )
                        if result is not None:
                            await self._apply_interaction(
                                result,
                                bot_token,
                                expected_channel_id,
                                account_id,
                                relay_token,
                            )
                        acknowledged = await client.post(
                            f"{self.broker_url}/v1/slack/actions/ack",
                            json={
                                "relayToken": relay_token,
                                "actionId": action.get("id"),
                                "leaseToken": action.get("leaseToken"),
                            },
                        )
                        if not acknowledged.is_success:
                            raise ExternalServiceError("Slack approval relay acknowledgement failed.")
                        # Reconcile worker lifecycle only after the durable relay action is
                        # acknowledged. Approve/skip may remove the final pending action and
                        # otherwise cause the supervisor to cancel this worker before ACK.
                        self._wake_event.set()
                        backoff = 2
                    except asyncio.CancelledError:
                        raise
                    except (httpx.HTTPError, ValueError, ExternalServiceError) as error:
                        message = error.message if isinstance(error, ExternalServiceError) else "Slack approval relay is temporarily unavailable."
                        self._set_status(account_id, False, "retrying", message)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30)
        except asyncio.CancelledError:
            self._set_status(account_id, False, "stopped", None)
            raise

    async def _apply_interaction(
        self,
        result: SlackInteractionResult,
        bot_token: str,
        expected_channel_id: str,
        account_id: str,
        relay_token: str = "",
    ) -> None:
        broker_url = self.broker_url if relay_token else ""
        if result.action_id:
            try:
                if result.action in {"regenerate", "regenerate_post", "regenerate_image"}:
                    await send_decision_feedback(
                        bot_token,
                        result.channel_id,
                        result.user_id,
                        "Regeneration started. Socium is creating a fresh revision now.",
                        broker_url=broker_url,
                        relay_token=relay_token,
                    )
                applied = await apply_remote_approval_action(
                    result.action_id,
                    result.action,  # type: ignore[arg-type]
                    "slack",
                )
                result = SlackInteractionResult(
                    result.channel_id,
                    result.user_id,
                    applied.message,
                )
                if applied.regenerated:
                    approval = create_approval_action(
                        applied.post["id"], applied.post["revision"], "slack"
                    )
                    try:
                        message_ts = await send_approval_message(
                            bot_token,
                            expected_channel_id,
                            applied.post,
                            approval["id"],
                            broker_url=broker_url,
                            relay_token=relay_token,
                        )
                        record_approval_sent(approval["id"], message_ts)
                    except ExternalServiceError as error:
                        fail_approval_delivery(approval["id"], error.message)
                        result = SlackInteractionResult(
                            result.channel_id,
                            result.user_id,
                            f"{applied.message} The new Slack approval message could not be sent.",
                        )
            except AppError as error:
                result = SlackInteractionResult(result.channel_id, result.user_id, error.message)
        try:
            await send_decision_feedback(
                bot_token,
                result.channel_id,
                result.user_id,
                result.message,
                broker_url=broker_url,
                relay_token=relay_token,
            )
        except ExternalServiceError as error:
            self._set_status(account_id, True, "listening", error.message)
        else:
            self._set_status(account_id, True, "listening", None)

    def _set_status(
        self,
        account_id: str,
        active: bool,
        status: str,
        last_error: str | None,
    ) -> None:
        with self._status_lock:
            self._statuses[account_id] = {
                "active": active,
                "status": status,
                "lastError": last_error,
            }
