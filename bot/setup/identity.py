"""
ERC-8004 Identity registration — on-chain register() + POST /api/identity.
Never crashes — returns False if setup is incomplete (caller retries).
"""
from bot.api_client import MoltyAPI, APIError
from bot.web3.identity_contract import register_identity_onchain
from bot.credentials import get_owner_private_key, load_credentials, save_credentials
from bot.config import ADVANCED_MODE
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def ensure_identity(api: MoltyAPI) -> bool:
    """
    Ensure ERC-8004 identity is registered.
    Returns True if identity is set. Never crashes.
    """
    # Check if already registered
    try:
        identity = await api.get_identity()
        erc8004_id = identity.get("erc8004Id")
        if erc8004_id is not None:
            log.info("ERC-8004 identity already registered: tokenId=%s", erc8004_id)
            return True
    except APIError:
        pass

    if not ADVANCED_MODE:
        log.info(
            "ERC-8004 identity not registered. In default mode, "
            "register manually then set the tokenId."
        )
        return False

    # Advanced mode: auto-register
    owner_pk = get_owner_private_key()
    if not owner_pk:
        log.error("Advanced mode but no Owner private key available")
        return False

    # On-chain register() — gas_checker runs inside
    log.info("Registering ERC-8004 identity on-chain...")
    token_id = await register_identity_onchain(owner_pk)

    if token_id is None:
        # Gas insufficient or tx failed — caller will retry
        log.info("Identity registration not completed. Will retry later.")
        return False

    # POST /api/identity
    try:
        result = await api.post_identity(token_id)
        log.info("✅ ERC-8004 identity registered: %s", result)

        creds = load_credentials() or {}
        creds["erc8004_token_id"] = token_id
        save_credentials(creds)
        return True

    except APIError as e:
        if e.code == "CONFLICT":
            log.info("Identity already registered")
            return True
        log.error("Identity API registration failed: %s", e)
        return False
