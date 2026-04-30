"""
Shared Web3 provider for Cross Network (PoA chain).
All on-chain calls should use get_w3() from here to ensure
PoA middleware is applied.
"""
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from bot.config import CROSS_RPC

_w3_instance = None


def get_w3() -> Web3:
    """Get Web3 instance with PoA middleware for Cross Network."""
    global _w3_instance
    if _w3_instance is None:
        _w3_instance = Web3(Web3.HTTPProvider(CROSS_RPC))
        # Cross Network is a PoA chain — extraData > 32 bytes
        _w3_instance.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return _w3_instance
