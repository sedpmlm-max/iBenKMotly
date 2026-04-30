"""
Free game join via matchmaking queue.
POST /join (Long Poll ~15s) → assigned → open WS immediately.
No extra sleep between retries per free-games.md.
"""
from bot.api_client import MoltyAPI, APIError
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def join_free_game(api: MoltyAPI) -> tuple[str, str]:
    """
    Enter free matchmaking queue and wait for assignment.
    Returns (game_id, agent_id) when assigned.
    """
    # Idempotency guard: check queue status first
    try:
        status_resp = await api.get_join_status()
        if isinstance(status_resp, dict):
            status = status_resp.get("status", "not_queued")
            if status == "assigned":
                gid = status_resp.get("gameId", "")
                aid = status_resp.get("agentId", "")
                if gid and aid:
                    log.info("Already assigned to game: %s", gid)
                    return gid, aid
            elif status == "queued":
                log.info("Already in queue, resuming...")
    except APIError:
        pass

    # Queue loop — no extra sleep, server Long Poll throttles (per free-games.md)
    attempt = 0
    while True:
        attempt += 1
        log.info("Free queue attempt #%d...", attempt)

        try:
            resp = await api.post_join("free")
            if not isinstance(resp, dict):
                log.warning("Unexpected join response type: %s", type(resp).__name__)
                continue

            status = resp.get("status", "")

            if status == "assigned":
                gid = resp.get("gameId", "")
                aid = resp.get("agentId", "")
                if gid and aid:
                    log.info("✅ Assigned to free game: %s (agent=%s)", gid, aid)
                    return gid, aid
                log.warning("Assigned but missing gameId/agentId: %s", resp)

            if status in ("not_selected", "queued"):
                log.debug("Queue status: %s — retrying immediately", status)
                continue

            log.warning("Unexpected queue response: %s", resp)

        except APIError as e:
            if e.code == "NO_IDENTITY":
                log.error("❌ ERC-8004 identity not registered. Cannot join free room.")
                raise
            if e.code == "OWNERSHIP_LOST":
                log.error("❌ NFT ownership changed. Re-register identity.")
                raise
            if e.code == "TOO_MANY_AGENTS_PER_IP":
                log.error("❌ IP agent limit reached for this game")
                raise
            if e.code == "ACCOUNT_ALREADY_IN_GAME":
                log.info("Already in a game. Returning to heartbeat.")
                raise
            log.warning("Join error: %s — retrying", e)
