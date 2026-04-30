"""
EIP-712 typed data signing for paid room join.
Signs JoinTournament typed data with Agent EOA private key.
"""
from eth_account import Account
from eth_account.messages import encode_typed_data
from bot.utils.logger import get_logger

log = get_logger(__name__)


def sign_join_paid(agent_private_key: str, eip712_data: dict) -> str:
    """
    Sign EIP-712 typed data for paid room join.
    eip712_data comes from GET /games/{id}/join-paid/message response.
    Returns hex signature string.
    """
    domain = eip712_data["domain"]
    types = eip712_data["types"]
    message = eip712_data["message"]

    # encode_typed_data expects the primaryType
    primary_type = "JoinTournament"

    signable = encode_typed_data(
        primaryType=primary_type,
        domain_data=domain,
        types=types,
        message_data=message,
    )

    acct = Account.from_key(agent_private_key)
    signed = acct.sign_message(signable)
    signature = signed.signature.hex()

    log.info("Signed EIP-712 JoinTournament for agent=%s", acct.address[:10] + "...")
    return "0x" + signature if not signature.startswith("0x") else signature
