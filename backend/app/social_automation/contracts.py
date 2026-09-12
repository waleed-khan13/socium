from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError


class AuthState(StrEnum):
    AUTHENTICATED = "connected"
    NOT_AUTHENTICATED = "session_expired"
    VERIFICATION_REQUIRED = "requires_verification"
    UNKNOWN = "unknown"


class BrowserError(AppError):
    def __init__(self, code: str, message: str, *, uncertain: bool = False) -> None:
        super().__init__(message, 409)
        self.code = code
        self.uncertain = uncertain


@dataclass(frozen=True)
class Authentication:
    state: AuthState
    identity: str | None = None


@dataclass(frozen=True)
class BrowserResult:
    remote_id: str
    remote_url: str


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(pattern="^linkedin$")
    name: str = Field(min_length=1, max_length=160)
    acknowledge_policy_risk: bool


class BrowserAdapter(Protocol):
    platform: str
    version: str
    login_url: str

    async def authenticate(self, page: Any) -> Authentication: ...
    def validate(self, post: dict[str, Any], media: dict[str, Any] | None) -> None: ...
    async def publish(
        self,
        page: Any,
        post: dict[str, Any],
        media: dict[str, Any] | None,
        before_click: Callable[[], None],
    ) -> BrowserResult: ...
