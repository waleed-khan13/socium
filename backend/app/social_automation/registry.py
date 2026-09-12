from app.social_automation.contracts import BrowserAdapter, BrowserError
from app.social_automation.linkedin import LinkedInAdapter


def get_adapter(platform: str) -> BrowserAdapter:
    if platform == "linkedin":
        return LinkedInAdapter()
    raise BrowserError("PLATFORM_NOT_SUPPORTED", "This platform does not have a tested browser adapter yet.")
