from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from app.approval_actions import apply_remote_approval_action
from app.errors import AppError, ExternalServiceError
from app.services.telegram import (
    answer_callback,
    get_updates,
    send_approval_request,
    send_status_message,
    update_approval_message,
)
from app.store import (
    create_approval_action,
    fail_approval_delivery,
    pending_approval_action_count,
    process_telegram_update,
    record_approval_sent,
    telegram_runtime,
)


class TelegramPoller:
    def __init__(self, poll_timeout: int) -> None:
        self.poll_timeout = poll_timeout
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active = False
        self._status = "stopped"
        self._last_error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "active": self._active,
            "status": self._status,
            "lastError": self._last_error,
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.create_task(self._run(), name="telegram-local-poller")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._active = False
        self._status = "stopped"
        self._loop = None

    async def refresh(self) -> None:
        await self.stop()
        self._status = "starting"
        self.start()

    def wake(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._wake.set)
        else:
            self._wake.set()

    async def _wait_for_work(self) -> None:
        await self._wake.wait()

    async def _run(self) -> None:
        backoff = 2
        try:
            while True:
                self._wake.clear()
                runtime = telegram_runtime()
                if not runtime["polling_enabled"]:
                    self._active = False
                    self._status = "stopped"
                    self._last_error = None
                    await self._wait_for_work()
                    continue
                token = str(runtime["bot_token"])
                proxy_url = str(runtime.get("proxy_url") or "")
                if not token or not runtime["chat_id"]:
                    self._active = False
                    self._status = "configuration_required"
                    self._last_error = "Telegram token and chat ID are required."
                    await self._wait_for_work()
                    continue
                if pending_approval_action_count("telegram") == 0:
                    self._active = False
                    self._status = "idle"
                    self._last_error = None
                    await self._wait_for_work()
                    continue

                self._active = True
                self._status = "listening"
                try:
                    updates = await get_updates(
                        token,
                        int(runtime["last_update_id"]) + 1,
                        self.poll_timeout,
                        proxy_url,
                    )
                    action_error: str | None = None
                    for update in updates:
                        callback = process_telegram_update(update)
                        if callback is None:
                            continue
                        callback_id = callback["callbackId"]
                        if callback.get("error"):
                            await answer_callback(token, callback_id, callback["error"], proxy_url)
                            continue
                        action = callback["action"]
                        if action in {"regenerate", "regenerate_post", "regenerate_image"}:
                            await answer_callback(
                                token,
                                callback_id,
                                "Regenerating this revision locally…",
                                proxy_url,
                            )
                        try:
                            result = await apply_remote_approval_action(
                                callback["actionId"], action, "telegram"  # type: ignore[arg-type]
                            )
                            if result.regenerated:
                                approval = create_approval_action(
                                    result.post["id"], result.post["revision"], "telegram"
                                )
                                try:
                                    message_id = await send_approval_request(
                                        token,
                                        str(runtime["chat_id"]),
                                        result.post,
                                        approval["id"],
                                        proxy_url,
                                    )
                                    record_approval_sent(approval["id"], message_id)
                                except ExternalServiceError as error:
                                    fail_approval_delivery(approval["id"], error.message)
                                    action_error = (
                                        "Draft regenerated, but its new Telegram approval could not be sent."
                                    )
                            else:
                                await answer_callback(token, callback_id, result.message, proxy_url)
                            if callback.get("chatId") and callback.get("messageId"):
                                try:
                                    await update_approval_message(
                                        token,
                                        callback["chatId"],
                                        callback["messageId"],
                                        callback.get("messageText", ""),
                                        action_error or result.message,
                                        proxy_url,
                                        bool(callback.get("hasPhoto")),
                                    )
                                except ExternalServiceError:
                                    try:
                                        await send_status_message(
                                            token,
                                            str(runtime["chat_id"]),
                                            action_error or result.message,
                                            proxy_url,
                                        )
                                    except ExternalServiceError:
                                        pass
                        except AppError as error:
                            if action not in {"regenerate", "regenerate_post", "regenerate_image"}:
                                await answer_callback(token, callback_id, error.message, proxy_url)
                            else:
                                try:
                                    await send_status_message(
                                        token,
                                        str(runtime["chat_id"]),
                                        f"Socium could not regenerate this draft: {error.message}",
                                        proxy_url,
                                    )
                                except ExternalServiceError:
                                    pass
                            action_error = error.message
                        except Exception as error:  # noqa: BLE001 - return safe action feedback.
                            message = error.message if hasattr(error, "message") else "Approval action failed."
                            if action not in {"regenerate", "regenerate_post", "regenerate_image"}:
                                await answer_callback(token, callback_id, str(message), proxy_url)
                            action_error = str(message)
                    self._last_error = action_error
                    backoff = 2
                except ExternalServiceError as error:
                    self._active = False
                    self._status = "retrying"
                    self._last_error = error.message
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
                except Exception:  # noqa: BLE001 - the long-running local worker must recover safely.
                    self._active = False
                    self._status = "retrying"
                    self._last_error = "Local Telegram polling hit an unexpected error."
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
        except asyncio.CancelledError:
            self._active = False
            self._status = "stopped"
            raise
