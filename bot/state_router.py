"""
State router — determines agent state from GET /accounts/me response.
Routes per skill.md State Router logic.
"""
from bot.utils.logger import get_logger

log = get_logger(__name__)

# States
NO_ACCOUNT = "NO_ACCOUNT"
NO_IDENTITY = "NO_IDENTITY"
IN_GAME = "IN_GAME"
READY_PAID = "READY_PAID"
READY_FREE = "READY_FREE"
ERROR = "ERROR"


def determine_state(me_response: dict) -> tuple[str, dict]:
    """
    Analyze /accounts/me response → return (state, context).
    Context contains relevant data for the next step.

    v2.1.2 fix: erc8004Id ada di ROOT level response, bukan di readiness.
    Kalau erc8004Id None → selalu NO_IDENTITY, biar bot register dulu.
    Readiness complete tanpa erc8004Id = masih perlu register identity NFT.
    """
    readiness = me_response.get("readiness", {})
    current_games = me_response.get("currentGames", [])

    # Check for active game
    for game in current_games:
        if game.get("gameStatus") in ("waiting", "running"):
            log.info("Active game found: %s (status=%s)",
                     game["gameId"], game["gameStatus"])
            return IN_GAME, {
                "game_id": game["gameId"],
                "agent_id": game["agentId"],
                "game_status": game["gameStatus"],
                "entry_type": game.get("entryType", "free"),
                "is_alive": game.get("isAlive", True),
            }

    # v2.1.2: erc8004Id ada di ROOT level — bukan di readiness
    erc8004_id = me_response.get("erc8004Id") or readiness.get("erc8004Id")

    if not erc8004_id:
        # Belum ada identity NFT — perlu register dulu
        # Tidak peduli readiness flags seberapa complete
        log.info("No ERC-8004 identity registered (erc8004Id=%s)", erc8004_id)
        return NO_IDENTITY, {}

    log.info("ERC-8004 identity found: tokenId=%s", erc8004_id)

    # Check paid readiness
    if readiness.get("paidReady", False):
        balance = me_response.get("balance", 0)
        if balance >= 500:
            log.info("Paid ready: balance=%d sMoltz", balance)
            return READY_PAID, {"balance": balance}

    # Default to free
    log.info("Ready for free play")
    return READY_FREE, {
        "balance": me_response.get("balance", 0),
        "wallet_address": readiness.get("walletAddress"),
        "whitelist_approved": readiness.get("whitelistApproved", False),
    }
