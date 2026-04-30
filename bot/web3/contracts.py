"""
Contract ABIs and helpers for on-chain interactions.
All addresses from contracts.md.
"""
from bot.config import (
    IDENTITY_REGISTRY, WALLET_FACTORY, CROSS_RPC, CROSS_CHAIN_ID,
)

# ── ERC-8004 Identity Registry ────────────────────────────────────────
IDENTITY_ABI = [
    {
        "name": "register",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [],
        "outputs": [{"name": "agentId", "type": "uint256"}],
    },
    {
        "name": "ownerOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address"}],
    },
]

# ── WalletFactory ─────────────────────────────────────────────────────
WALLET_FACTORY_ABI = [
    {
        "name": "getWallets",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "address[]"}],
    },
]

# ── MoltyRoyaleWallet (resolved from WalletFactory) ──────────────────
MOLTY_WALLET_ABI = [
    {
        "name": "getRequestedAddWhitelists",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [
            {
                "name": "",
                "type": "tuple[]",
                "components": [
                    {"name": "eoa", "type": "address"},
                    {"name": "agentId", "type": "uint256"},
                ],
            }
        ],
    },
    {
        "name": "approveAddWhitelist",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "requestor", "type": "address"},
            {"name": "agentId", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "getWhitelists",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address[]"}],
    },
]

# ── ERC-20 (Moltz) ───────────────────────────────────────────────────
ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]
