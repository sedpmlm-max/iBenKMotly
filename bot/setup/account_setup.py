"""
Account setup — First-Run Intake per setup.md.
Generates Agent EOA, creates account, persists credentials.
Supports both interactive (local) and non-interactive (Railway/Docker) modes.

IMPORTANT: On Railway, env vars persist across restarts but dev-agent/ does not.
If env vars already have credentials (API_KEY, AGENT_PRIVATE_KEY, etc),
we restore from them instead of generating new wallets.
"""
import os
import sys
import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.credentials import (
    is_first_run, save_credentials, save_owner_intake,
    save_agent_wallet, save_owner_wallet, load_credentials,
    load_agent_wallet, load_owner_wallet, update_env_file,
)
from bot.web3.wallet_manager import generate_agent_wallet, generate_owner_wallet
from bot.config import ADVANCED_MODE, AGENT_NAME, OWNER_EOA
from bot.utils.logger import get_logger

log = get_logger(__name__)


def _is_interactive() -> bool:
    """Check if stdin is a TTY (terminal). False on Railway/Docker."""
    return sys.stdin.isatty()


def _ask_or_env(prompt: str, env_value: str, default: str = "") -> str:
    """Read from env var first, then ask interactively, then fall back to default."""
    if env_value:
        return env_value
    if _is_interactive():
        val = input(prompt).strip()
        if val:
            return val
    if default:
        log.info("Using default: %s", default)
    return default


def _restore_from_env() -> dict | None:
    """
    Check if we have existing credentials in env vars (Railway persistence).
    If so, restore them to dev-agent/ and return creds dict.
    This prevents generating new wallets on every container restart.
    """
    api_key = os.getenv("API_KEY", "")
    agent_pk = os.getenv("AGENT_PRIVATE_KEY", "")
    agent_addr = os.getenv("AGENT_WALLET_ADDRESS", "")
    owner_pk = os.getenv("OWNER_PRIVATE_KEY", "")
    owner_addr = os.getenv("OWNER_EOA", "")
    agent_name = os.getenv("AGENT_NAME", "")

    if not api_key or not agent_pk:
        return None  # No env credentials — truly first run

    log.info("♻️ Restoring credentials from Railway Variables (env vars)...")

    # Restore wallet files
    if agent_pk and agent_addr:
        save_agent_wallet(agent_addr, agent_pk)
        log.info("  Restored Agent wallet: %s", agent_addr[:12] + "...")
    if owner_pk and owner_addr:
        save_owner_wallet(owner_addr, owner_pk)
        log.info("  Restored Owner wallet: %s", owner_addr[:12] + "...")

    # Restore credentials file
    creds = {
        "api_key": api_key,
        "agent_name": agent_name,
        "agent_wallet_address": agent_addr,
        "owner_eoa": owner_addr,
    }
    save_credentials(creds)

    # Restore intake file
    intake = {
        "agent_name": agent_name,
        "advanced_mode": ADVANCED_MODE,
        "owner_eoa": owner_addr,
        "agent_wallet_generated": True,
        "owner_wallet_generated": bool(owner_pk),
    }
    save_owner_intake(intake)

    log.info("✅ Credentials restored from env vars — skipping wallet generation")
    return creds


async def run_first_run_intake() -> dict:
    """
    First-Run Intake Flow (setup.md):
    1. Check if env vars have existing credentials (Railway restart)
    2. Get agent name (env → input → default)
    3. Auto-generate Agent EOA
    4. Auto-generate Owner EOA (advanced mode) or read from env/input
    5. POST /accounts → save api_key
    6. Persist credentials + intake
    Returns credentials dict.
    """
    # Step 0: Check if this is a Railway restart with existing env credentials
    restored = _restore_from_env()
    if restored:
        return restored

    log.info("═══ FIRST-RUN INTAKE ═══")
    if not _is_interactive():
        log.info("Non-interactive mode (Railway/Docker detected)")

    # Step 1: Agent name
    agent_name = _ask_or_env(
        "Enter agent name (max 50 chars): ",
        AGENT_NAME,
        "MoltyAgent",
    )
    if len(agent_name) > 50:
        agent_name = agent_name[:50]

    # Step 2: Generate Agent EOA (never ask the owner — setup.md)
    log.info("Generating Agent EOA...")
    agent_address, agent_pk = generate_agent_wallet()
    save_agent_wallet(agent_address, agent_pk)
    update_env_file("AGENT_WALLET_ADDRESS", agent_address)
    update_env_file("AGENT_PRIVATE_KEY", agent_pk)

    # Step 3: Owner EOA
    owner_address = ""
    owner_pk = ""
    if ADVANCED_MODE:
        log.info("Advanced mode: Generating Owner EOA...")
        owner_address, owner_pk = generate_owner_wallet()
        save_owner_wallet(owner_address, owner_pk)
        update_env_file("OWNER_EOA", owner_address)
        update_env_file("OWNER_PRIVATE_KEY", owner_pk)
        log.info(
            "Owner EOA generated: %s\n"
            "  → Private key stored at: dev-agent/owner-wallet.json\n"
            "  → You can view/download this file anytime\n"
            "  → To import into MetaMask: Settings → Import Account → paste private key",
            owner_address,
        )
    else:
        owner_address = _ask_or_env(
            "Enter your Owner EOA address (0x...): ",
            OWNER_EOA,
            "",
        )
        if not owner_address or not owner_address.startswith("0x") or len(owner_address) != 42:
            log.error(
                "Owner EOA address required but not provided or invalid. "
                "Set OWNER_EOA env var (0x + 40 hex chars) or use ADVANCED_MODE=true."
            )
            raise ValueError("Missing or invalid Owner EOA address")
        update_env_file("OWNER_EOA", owner_address)

    # Step 4: Create account via API
    log.info("Creating account via POST /accounts...")
    api = MoltyAPI()
    try:
        result = await api.create_account(agent_name, agent_address)
    except APIError as e:
        if e.code == "CONFLICT":
            log.warning("Wallet already registered. Loading existing credentials.")
            return load_credentials() or {}
        raise
    finally:
        await api.close()

    api_key = result.get("apiKey", "")
    account_id = result.get("accountId", "")
    public_id = result.get("publicId", "")

    if not api_key:
        raise RuntimeError("No apiKey returned from POST /accounts!")

    log.info("✅ Account created! apiKey=%s... accountId=%s", api_key[:15], account_id[:8])

    # Step 5: Persist
    creds = {
        "api_key": api_key,
        "agent_name": agent_name,
        "account_id": account_id,
        "public_id": public_id,
        "agent_wallet_address": agent_address,
        "owner_eoa": owner_address,
    }
    save_credentials(creds)
    update_env_file("API_KEY", api_key)
    update_env_file("AGENT_NAME", agent_name)

    intake = {
        "agent_name": agent_name,
        "advanced_mode": ADVANCED_MODE,
        "owner_eoa": owner_address,
        "agent_wallet_generated": True,
        "owner_wallet_generated": ADVANCED_MODE,
    }
    save_owner_intake(intake)

    # Step 6: Auto-sync to Railway Variables (if on Railway)
    from bot.utils.railway_sync import is_railway, sync_all_to_railway
    if is_railway():
        log.info("Detected Railway — syncing all variables in one batch...")
        await sync_all_to_railway(creds, agent_pk, owner_pk)

    return creds


async def ensure_account_ready() -> dict:
    """
    Ensure account exists. Run first-run intake if needed.
    Returns credentials dict with api_key.
    """
    if is_first_run():
        return await run_first_run_intake()

    creds = load_credentials()
    if not creds or not creds.get("api_key"):
        log.warning("Credentials file exists but no api_key. Re-running intake.")
        return await run_first_run_intake()

    log.info("Returning run: account=%s", creds.get("agent_name", "unknown"))
    return creds
