"""
Whitelist request + auto-approval (advanced mode).
POST /whitelist/request → on-chain approveAddWhitelist().
Never crashes — returns False if setup is incomplete (caller retries).
"""
import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.web3.whitelist_contract import approve_whitelist_onchain, verify_whitelist
from bot.credentials import get_owner_private_key
from bot.config import ADVANCED_MODE
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def ensure_whitelist(api: MoltyAPI, owner_eoa: str, agent_eoa: str) -> bool:
    """
    Request whitelist + auto-approve if advanced mode.
    Returns True if whitelisted. Never crashes.
    """
    # Step 1: Submit whitelist request
    already_whitelisted = False
    try:
        result = await api.whitelist_request(owner_eoa)
        log.info("Whitelist request submitted: %s", result)
    except APIError as e:
        if e.code == "CONFLICT":
            log.info("Whitelist request already exists or already approved")
        elif e.code == "INTERNAL_ERROR" and "AlreadyWhitelisted" in str(e):
            log.info("✅ Already whitelisted on-chain — skipping approval")
            already_whitelisted = True
        elif e.code == "SC_WALLET_NOT_FOUND":
            log.error("SC Wallet not found. Must call POST /create/wallet first.")
            return False
        else:
            log.error("Whitelist request failed: %s", e)
            return False

    # If already whitelisted, skip on-chain approval
    if already_whitelisted:
        return True

    # Step 2: Auto-approve if advanced mode
    if ADVANCED_MODE:
        owner_pk = get_owner_private_key()
        if not owner_pk:
            log.error("Advanced mode but no Owner private key found")
            return False

        log.info("Auto-approving whitelist on-chain...")
        # gas_checker + already-whitelisted check runs inside
        tx_hash = await approve_whitelist_onchain(owner_pk, agent_eoa, owner_eoa)

        if tx_hash is None:
            # Gas insufficient or tx failed — caller will retry
            log.info("Whitelist approval not completed. Will retry later.")
            return False

        if tx_hash == "ALREADY_APPROVED":
            log.info("✅ Whitelist already approved — proceeding")
            return True

        log.info("✅ Whitelist approved: tx=%s", tx_hash)

        # Wait for chain confirmation
        await asyncio.sleep(3)

        # Verify
        is_approved = await verify_whitelist(owner_eoa, agent_eoa)
        if is_approved:
            log.info("✅ Whitelist verification passed")
            return True
        else:
            log.warning("Whitelist verification pending — may need more time")
            return False
    else:
        log.info(
            "Default mode: Please approve whitelist manually at "
            "https://www.moltyroyale.com → My Agent page"
        )
        return False
