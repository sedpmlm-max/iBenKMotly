"""
MoltyRoyale Wallet (SC Wallet) setup — POST /create/wallet.
Handles CONFLICT, WALLET_ALREADY_EXISTS, and other error codes.
Never crashes — returns "" if recovery fails.
"""
from bot.api_client import MoltyAPI, APIError
from bot.web3.whitelist_contract import get_molty_wallet_address
from bot.credentials import load_credentials, save_credentials
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def ensure_molty_wallet(api: MoltyAPI, owner_eoa: str) -> str:
    """
    Create or recover MoltyRoyale Wallet. Returns wallet address or "".
    Per setup.md §6: one wallet per Owner EOA, don't blindly create.
    Never crashes.
    """
    # Step 1: Try to get existing wallet from credentials
    creds = load_credentials() or {}
    existing = creds.get("molty_royale_wallet", "")
    if existing:
        log.info("MoltyRoyale Wallet already known: %s", existing)
        return existing

    # Step 2: Try to create
    try:
        result = await api.create_wallet(owner_eoa)
        wallet_addr = result.get("walletAddress", "")
        log.info("✅ MoltyRoyale Wallet created: %s", wallet_addr)

        creds["molty_royale_wallet"] = wallet_addr
        save_credentials(creds)
        return wallet_addr

    except APIError as e:
        if e.code in ("CONFLICT", "WALLET_ALREADY_EXISTS"):
            log.info("MoltyRoyale Wallet already exists — recovering address...")
            return await _recover_wallet_address(owner_eoa, creds)

        if e.code == "AGENT_EOA_EQUALS_OWNER_EOA":
            log.error(
                "❌ Agent EOA and Owner EOA are the same address! "
                "The contract requires these to be different."
            )
            return ""

        log.error("Wallet creation failed: %s", e)
        return ""

    except Exception as e:
        log.error("Unexpected wallet setup error: %s", e)
        return ""


async def _recover_wallet_address(owner_eoa: str, creds: dict) -> str:
    """Try to recover wallet address on-chain via WalletFactory.getWallets()."""
    try:
        wallet_addr = await get_molty_wallet_address(owner_eoa)
        if wallet_addr:
            log.info("✅ Recovered MoltyRoyale Wallet: %s", wallet_addr)
            creds["molty_royale_wallet"] = wallet_addr
            save_credentials(creds)
            return wallet_addr
    except Exception as e:
        log.warning("On-chain wallet recovery failed: %s", e)

    log.warning(
        "Wallet exists but address could not be recovered. "
        "Check My Agent page at https://www.moltyroyale.com"
    )
    return ""
