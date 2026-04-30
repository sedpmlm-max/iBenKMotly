"""
Room selector — choose free or paid room based on readiness and config.
ROOM_MODE env: auto | free | paid
"""
from bot.config import ROOM_MODE, PAID_ENTRY_FEE_SMOLTZ
from bot.utils.logger import get_logger

log = get_logger(__name__)


def select_room(me_data: dict) -> str:
    """
    Determine which room type to join.
    Returns 'free' or 'paid'.
    """
    balance = me_data.get("balance", 0)
    readiness = me_data.get("readiness", {})
    whitelist_ok = readiness.get("whitelistApproved", False)
    wallet_ok = readiness.get("walletAddress") is not None
    current_games = me_data.get("currentGames", [])

    # Check if already in a paid game
    has_active_paid = any(
        g.get("entryType") == "paid" and g.get("gameStatus") != "finished"
        for g in current_games
    )

    paid_ready = (
        wallet_ok
        and whitelist_ok
        and balance >= PAID_ENTRY_FEE_SMOLTZ
        and not has_active_paid
    )

    if ROOM_MODE == "free":
        log.info("Room mode: FREE (forced)")
        return "free"

    if ROOM_MODE == "paid":
        if paid_ready:
            log.info("Room mode: PAID (forced, ready)")
            return "paid"
        log.warning("Room mode: PAID forced but not ready (balance=%d, whitelist=%s)", balance, whitelist_ok)
        return "free"  # fallback

    # Auto mode
    if paid_ready:
        log.info("Room mode: AUTO → PAID (balance=%d sMoltz, whitelist=✓)", balance)
        return "paid"

    reasons = []
    if not wallet_ok:
        reasons.append("no wallet")
    if not whitelist_ok:
        reasons.append("whitelist pending")
    if balance < PAID_ENTRY_FEE_SMOLTZ:
        reasons.append(f"balance={balance}/{PAID_ENTRY_FEE_SMOLTZ}")
    if has_active_paid:
        reasons.append("active paid game exists")

    log.info("Room mode: AUTO → FREE (%s)", ", ".join(reasons))
    return "free"
