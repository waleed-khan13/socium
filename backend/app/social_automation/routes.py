from collections.abc import Callable

from fastapi import APIRouter

from app.social_automation.browser import browser_installed, driver_available
from app.social_automation.contracts import AccountCreate
from app.social_automation.manager import disconnect
from app.social_automation.store import (
    cancel_operation,
    create_account,
    public_state,
    queue_operation,
    set_preferred,
)


def create_router(wake: Callable[[], None]) -> APIRouter:
    router = APIRouter(prefix="/api/social-browser", tags=["Local browser publishing"])

    @router.get("")
    def state():
        return {
            **public_state(),
            "browserInstalled": browser_installed(),
            "driverAvailable": driver_available(),
            "platforms": [{"id": "linkedin", "status": "experimental", "text": True, "singleImage": True}],
        }

    @router.post("/install", status_code=202)
    def install():
        job = queue_operation("social.browser.install")
        wake()
        return {"ok": True, "job": job}

    @router.post("/accounts", status_code=201)
    def create(payload: AccountCreate):
        return {"ok": True, "account": create_account(payload)}

    @router.post("/accounts/{account_id}/connect", status_code=202)
    def connect(account_id: str):
        job = queue_operation("social.connect", account_id)
        wake()
        return {"ok": True, "job": job}

    @router.post("/accounts/{account_id}/verify", status_code=202)
    def verify(account_id: str):
        job = queue_operation("social.verify", account_id)
        wake()
        return {"ok": True, "job": job}

    @router.post("/accounts/{account_id}/prefer")
    def prefer(account_id: str):
        set_preferred(account_id)
        return {"ok": True}

    @router.delete("/accounts/{account_id}")
    def remove(account_id: str):
        disconnect(account_id)
        return {"ok": True, "message": "Local browser session removed. Publishing history is preserved."}

    @router.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        cancel_operation(job_id)
        wake()
        return {"ok": True}

    return router
