"""
Credential file I/O — secure read/write for agent-wallet, owner-wallet, credentials, intake.
All sensitive files stored in dev-agent/ with restricted permissions.
"""
import json
import os
import stat
from pathlib import Path
from typing import Any, Optional

from bot.config import (
    CREDENTIALS_FILE, OWNER_INTAKE_FILE,
    AGENT_WALLET_FILE, OWNER_WALLET_FILE, DEV_AGENT_DIR,
)
from bot.utils.logger import get_logger

log = get_logger(__name__)


def _ensure_dir():
    """Create dev-agent/ directory if missing."""
    DEV_AGENT_DIR.mkdir(parents=True, exist_ok=True)


def _write_secure(path: Path, data: dict):
    """Write JSON file with restricted permissions (owner-only read/write)."""
    _ensure_dir()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass  # Windows may not support chmod fully


def _read_json(path: Path) -> Optional[dict]:
    """Read JSON file, return None if missing or corrupt."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Failed to read {path}: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────────

def is_first_run() -> bool:
    """First-run if credentials.json or owner-intake.json is missing."""
    return not CREDENTIALS_FILE.exists() or not OWNER_INTAKE_FILE.exists()


def load_credentials() -> Optional[dict]:
    return _read_json(CREDENTIALS_FILE)


def save_credentials(data: dict):
    _write_secure(CREDENTIALS_FILE, data)
    log.info("Credentials saved to %s", CREDENTIALS_FILE)


def load_owner_intake() -> Optional[dict]:
    return _read_json(OWNER_INTAKE_FILE)


def save_owner_intake(data: dict):
    _write_secure(OWNER_INTAKE_FILE, data)
    log.info("Owner intake saved to %s", OWNER_INTAKE_FILE)


def load_agent_wallet() -> Optional[dict]:
    return _read_json(AGENT_WALLET_FILE)


def save_agent_wallet(address: str, private_key: str):
    _write_secure(AGENT_WALLET_FILE, {
        "address": address,
        "privateKey": private_key,
    })
    log.info("Agent wallet saved to %s", AGENT_WALLET_FILE)


def load_owner_wallet() -> Optional[dict]:
    return _read_json(OWNER_WALLET_FILE)


def save_owner_wallet(address: str, private_key: str):
    _write_secure(OWNER_WALLET_FILE, {
        "address": address,
        "privateKey": private_key,
    })
    log.info("Owner wallet saved to %s", OWNER_WALLET_FILE)


def get_api_key() -> str:
    """Resolve API key from env → credentials file."""
    from bot.config import API_KEY
    if API_KEY:
        return API_KEY
    creds = load_credentials()
    return creds.get("api_key", "") if creds else ""


def get_agent_private_key() -> str:
    """Resolve agent PK from env → wallet file."""
    from bot.config import AGENT_PRIVATE_KEY
    if AGENT_PRIVATE_KEY:
        return AGENT_PRIVATE_KEY
    wallet = load_agent_wallet()
    return wallet.get("privateKey", "") if wallet else ""


def get_owner_private_key() -> str:
    """Resolve owner PK from env → wallet file (advanced mode only)."""
    from bot.config import OWNER_PRIVATE_KEY
    if OWNER_PRIVATE_KEY:
        return OWNER_PRIVATE_KEY
    wallet = load_owner_wallet()
    return wallet.get("privateKey", "") if wallet else ""


def update_env_file(key: str, value: str):
    """Update or append a key=value in .env file."""
    env_path = Path(".env")
    lines = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
