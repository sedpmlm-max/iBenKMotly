"""
Version check — GET /api/version and X-Version header management.
Returns 426 VERSION_MISMATCH if outdated.
"""
import httpx
from bot.config import API_BASE, SKILL_VERSION
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def check_version(client: httpx.AsyncClient) -> str:
    """Fetch current server version. Returns version string."""
    try:
        resp = await client.get(f"{API_BASE}/version")
        if resp.status_code == 200:
            data = resp.json()
            server_version = data.get("data", {}).get("version", SKILL_VERSION)
            if server_version != SKILL_VERSION:
                log.warning("Server version %s != local %s", server_version, SKILL_VERSION)
            return server_version
    except Exception as e:
        log.warning("Version check failed: %s", e)
    return SKILL_VERSION


def get_version_header() -> dict:
    """Return X-Version header dict."""
    return {"X-Version": SKILL_VERSION}
