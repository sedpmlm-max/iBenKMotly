"""
Wallet manager — generate Agent EOA and Owner EOA keypairs.
Uses eth_account for EVM key generation.
"""
from eth_account import Account
from bot.utils.logger import get_logger

log = get_logger(__name__)


def generate_agent_wallet() -> tuple[str, str]:
    """Generate a new Agent EOA keypair. Returns (address, private_key_hex)."""
    acct = Account.create()
    log.info("Generated Agent EOA: %s", acct.address)
    return acct.address, acct.key.hex()


def generate_owner_wallet() -> tuple[str, str]:
    """Generate a new Owner EOA keypair (advanced mode). Returns (address, private_key_hex)."""
    acct = Account.create()
    log.info("Generated Owner EOA: %s", acct.address)
    return acct.address, acct.key.hex()


def load_account_from_key(private_key: str) -> Account:
    """Load an eth_account Account from a private key hex string."""
    return Account.from_key(private_key)
