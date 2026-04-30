"""
Paid game join — EIP-712 sign → POST /games/{id}/join-paid.
Per paid-games.md: check balance → find room → sign → submit → poll currentGames.
"""
import asyncio
from bot.api_client import MoltyAPI, APIError
from bot.web3.eip712_signer import sign_join_paid
from bot.credentials import get_agent_private_key
from bot.config import PAID_ENTRY_FEE_SMOLTZ
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def join_paid_game(api: MoltyAPI) -> tuple[str, str]:
    """
    Join a paid room via EIP-712 signed flow.
    Returns (game_id, agent_id) when registered.
    """
    # Step 1: Balance check (mandatory before signing per paid-games.md)
    me = await api.get_accounts_me()
    balance = me.get("balance", 0)
    if balance < PAID_ENTRY_FEE_SMOLTZ:
        raise RuntimeError(
            f"Insufficient sMoltz: {balance}/{PAID_ENTRY_FEE_SMOLTZ}. "
            "Keep playing free rooms to earn more."
        )

    # Step 2: Find waiting paid game
    games_resp = await api.get_games("waiting")
    games = games_resp if isinstance(games_resp, list) else games_resp.get("games", [])
    paid_games = [g for g in games if g.get("entryType") == "paid"]

    if not paid_games:
        raise RuntimeError("No waiting paid rooms available")

    game = paid_games[0]
    game_id = game["gameId"]
    log.info("Found paid room: %s", game_id)

    # Step 3: Get EIP-712 typed data
    eip712_data = await api.get_join_paid_message(game_id)

    # Step 4: Sign with Agent EOA
    agent_pk = get_agent_private_key()
    if not agent_pk:
        raise RuntimeError("Agent private key not found")

    signature = sign_join_paid(agent_pk, eip712_data)
    deadline = eip712_data["message"]["deadline"]

    # Step 5: Submit (offchain by default)
    log.info("Submitting paid join for game=%s...", game_id)
    result = await api.post_join_paid(game_id, deadline, signature)
    log.info("Paid join submitted: %s", result)

    # Step 6: Poll GET /accounts/me until currentGames[] shows the game
    for attempt in range(30):  # Max 30 attempts × 2s = 60s timeout
        await asyncio.sleep(2)
        me = await api.get_accounts_me()
        for cg in me.get("currentGames", []):
            if cg.get("gameId") == game_id:
                agent_id = cg["agentId"]
                log.info("✅ Paid game active: game=%s agent=%s", game_id, agent_id)
                return game_id, agent_id

    raise RuntimeError(f"Paid game {game_id} did not appear in currentGames after 60s")
