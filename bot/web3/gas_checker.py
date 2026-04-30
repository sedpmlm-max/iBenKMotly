"""
Gas fee checker — check CROSS balance before any on-chain transaction.
If insufficient, wait and retry every 2 minutes until funded.
"""
import asyncio
from web3 import Web3
from bot.web3.provider import get_w3
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Minimum CROSS needed for gas (0.001 CROSS should be enough for most txs)
MIN_GAS_WEI = Web3.to_wei(0.001, "ether")


def check_cross_balance(address: str) -> tuple[bool, int]:
    """
    Check if address has enough CROSS for gas.
    Returns (has_enough, balance_wei).
    """
    try:
        w3 = get_w3()
        balance = w3.eth.get_balance(Web3.to_checksum_address(address))
        has_enough = balance >= MIN_GAS_WEI
        return has_enough, balance
    except Exception as e:
        log.warning("Failed to check CROSS balance for %s: %s", address, e)
        return False, 0


def require_gas_or_wait(address: str, action_name: str) -> bool:
    """
    Check gas balance synchronously. If insufficient, log instructions and return False.
    For async retry loop, use require_gas_or_wait_async() instead.
    """
    has_gas, balance_wei = check_cross_balance(address)

    if has_gas:
        balance_cross = Web3.from_wei(balance_wei, "ether")
        log.info("Gas check OK: %s has %s CROSS", address[:12] + "...", balance_cross)
        return True

    balance_cross = Web3.from_wei(balance_wei, "ether")
    log.warning(
        "═══════════════════════════════════════════════════════════════\n"
        "  ⚠️ INSUFFICIENT CROSS FOR GAS — %s\n"
        "  Wallet: %s\n"
        "  Balance: %s CROSS (need min 0.001 CROSS)\n"
        "  Action: %s\n"
        "  \n"
        "  → Please send CROSS to the wallet above\n"
        "  → Bot will retry automatically every 2 minutes\n"
        "═══════════════════════════════════════════════════════════════",
        action_name, address, balance_cross, action_name,
    )
    return False


async def require_gas_or_wait_async(address: str, action_name: str,
                                     retry_interval: int = 120) -> bool:
    """
    Check gas balance. If insufficient, wait and retry every 2 minutes
    until gas is available. Blocks until funded.

    Args:
        address: Wallet address to check
        action_name: Description for logs
        retry_interval: Seconds between retries (default 120 = 2 minutes)

    Returns True when gas is available.
    """
    attempt = 0
    while True:
        has_gas, balance_wei = check_cross_balance(address)
        balance_cross = Web3.from_wei(balance_wei, "ether")

        if has_gas:
            if attempt > 0:
                log.info("✅ Gas funded after %d attempts! Balance: %s CROSS",
                         attempt, balance_cross)
            else:
                log.info("Gas check OK: %s has %s CROSS",
                         address[:12] + "...", balance_cross)
            return True

        attempt += 1
        log.warning(
            "═══════════════════════════════════════════════════════════════\n"
            "  ⚠️ INSUFFICIENT CROSS FOR GAS — Attempt #%d\n"
            "  Wallet: %s\n"
            "  Balance: %s CROSS (need min 0.001 CROSS)\n"
            "  Action: %s\n"
            "  \n"
            "  → Please send CROSS to the wallet above\n"
            "  → Retrying in %d seconds (%d minutes)...\n"
            "═══════════════════════════════════════════════════════════════",
            attempt, address, balance_cross, action_name,
            retry_interval, retry_interval // 60,
        )
        await asyncio.sleep(retry_interval)
