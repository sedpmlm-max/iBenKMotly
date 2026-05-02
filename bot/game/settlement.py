"""
Game settlement — Phase 3: process game end, update memory, prepare for next game.

v1.5.3: more detailed lessons recorded for cross-game brain adaptation.
"""
from bot.memory.agent_memory import AgentMemory
from bot.dashboard.state import dashboard_state
from bot.utils.logger import get_logger

log = get_logger(__name__)


async def settle_game(game_result: dict, entry_type: str, memory: AgentMemory):
    """
    Process game end:
    1. Extract final stats
    2. Update memory (overall history + lessons)
    3. Clear temp memory
    """
    result = game_result.get("result", game_result)
    is_winner = result.get("isWinner", False)
    final_rank = result.get("finalRank", 0)
    kills = result.get("kills", 0)
    rewards = result.get("rewards", {})
    smoltz_earned = rewards.get("sMoltz", 0)
    moltz_earned = rewards.get("moltz", 0)

    log.info("═══ GAME SETTLEMENT ═══")
    log.info("  Winner: %s | Rank: %d | Kills: %d", "YES" if is_winner else "No", final_rank, kills)
    log.info("  Rewards: %d sMoltz, %d Moltz", smoltz_earned, moltz_earned)

    memory.record_game_end(
        is_winner=is_winner,
        final_rank=final_rank,
        kills=kills,
        smoltz_earned=smoltz_earned,
    )

    # ── Record lessons for cross-game brain adaptation (v1.5.3) ──────
    if is_winner:
        memory.add_lesson(f"won with {kills} kills at rank {final_rank}")
    elif final_rank <= 3:
        memory.add_lesson(f"top 3 finish rank {final_rank} with {kills} kills — stay conservative")
    elif kills == 0:
        # Brain reads this → activates be_aggressive mode
        memory.add_lesson("zero kills — need more aggressive guardian/monster targeting")
    elif kills >= 5:
        memory.add_lesson(f"high kill game ({kills} kills) rank {final_rank} — aggressive works")

    # Rank-based lessons
    if final_rank > 20 and kills == 0:
        memory.add_lesson("died early with zero kills — prioritize weapon pickup and guardian farm")
    elif final_rank <= 10 and kills > 0:
        memory.add_lesson(f"top 10 finish with {kills} kills — current strategy effective")

    memory.clear_temp()
    await memory.save()

    # v1.7.0: update dashboard memory stats
    dashboard_state.record_game_result(
        kills=kills,
        is_winner=is_winner,
        final_rank=final_rank,
        smoltz_earned=smoltz_earned,
        moltz_earned=moltz_earned,
    )
    dashboard_state.update_memory(memory.data)

    log.info("Settlement complete. Ready for next game.")
