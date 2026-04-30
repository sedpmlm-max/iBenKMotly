"""
ERC-8004 Identity Registry on-chain calls.
register() from Owner EOA → returns tokenId → POST /api/identity.
Uses PoA-enabled Web3 provider.

v1.5.2: Gas is DELEGATED for all ERC-8004 operations (relayed by Tx delegator).
The agent MUST NOT ask the owner to fund CROSS gas for identity registration.
We still set gasLimit manually to prevent ethers from failing on estimation.
"""
from web3 import Web3
from eth_account import Account
from bot.config import IDENTITY_REGISTRY, CROSS_CHAIN_ID
from bot.web3.contracts import IDENTITY_ABI
from bot.web3.provider import get_w3
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def register_identity_onchain(owner_private_key: str) -> int | None:
    """
    Call register() on ERC-8004 Identity Registry from Owner EOA.
    Returns tokenId (= agentId) or None if failed (no crash).

    v1.5.2: Gas is delegated — no gas balance check needed.
    If a gas-related error occurs, treat as client-side problem (e.g. missing gasLimit),
    never escalate to the owner as a funding request.
    """
    acct = Account.from_key(owner_private_key)

    try:
        w3 = get_w3()
        registry = w3.eth.contract(
            address=Web3.to_checksum_address(IDENTITY_REGISTRY),
            abi=IDENTITY_ABI,
        )

        # Gas is delegated (relayed by Tx delegator), but we still set gasLimit
        # manually to prevent ethers from failing early on revert estimation.
        tx = registry.functions.register().build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 200000,
            "chainId": CROSS_CHAIN_ID,
        })

        signed = w3.eth.account.sign_transaction(tx, owner_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt.status != 1:
            log.error("ERC-8004 register() TX failed: %s", tx_hash.hex())
            return None

        # Extract agentId from Transfer event logs (ERC-721 mint)
        for event_log in receipt.logs:
            if len(event_log.topics) >= 4:
                token_id = int(event_log.topics[3].hex(), 16)
                log.info("ERC-8004 registered: tokenId=%d tx=%s", token_id, tx_hash.hex())
                return token_id

        log.warning("Could not extract tokenId from logs")
        return None

    except Exception as e:
        log.error("ERC-8004 register() error (gas is delegated — this is a client-side issue): %s", e)
        return None

