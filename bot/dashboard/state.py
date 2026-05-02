"""
Dashboard shared state — bridge between bot engine and web dashboard.
Bot writes → Dashboard reads. Thread-safe via asyncio lock.
"""
import time
from collections import deque
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Maximum log entries kept in memory
MAX_LOGS = 500


class DashboardState:
    """Singleton shared state between bot and dashboard."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # ── Agent state ────────────────────────────────────────
        self.agents: dict[str, dict] = {}  # {agent_id: {name, status, hp, ep, ...}}

        # ── Global stats ───────────────────────────────────────
        self.total_wins = 0
        self.total_moltz = 0
        self.total_smoltz = 0
        self.total_cross = 0.0
        self.bots_running = 0

        # ── Logs ───────────────────────────────────────────────
        self.global_logs: deque = deque(maxlen=MAX_LOGS)
        self.agent_logs: dict[str, deque] = {}  # {agent_id: deque}

        # ── Accounts ───────────────────────────────────────────
        self.accounts: list[dict] = []

        # ── Timestamps ─────────────────────────────────────────
        self.started_at = time.time()
        self.last_update = time.time()

        # ── Memory / cross-game stats (v1.7.0) ─────────────────
        self.memory: dict = {
            "totalGames": 0,
            "wins": 0,
            "avgKills": 0.0,
            "totalKills": 0,
            "totalMoltz": 0,
            "totalSmoltz": 0,
            "totalCross": 0.0,
            "bestKills": 0,
            "gamesThisSession": 0,
            "avgRank": 0.0,
            "lessons": [],
        }

    # ── Bot writes ─────────────────────────────────────────────

    def update_agent(self, agent_id: str, data: dict):
        """Update agent state from bot engine."""
        if agent_id not in self.agents:
            self.agents[agent_id] = {}
            self.agent_logs[agent_id] = deque(maxlen=MAX_LOGS)
        self.agents[agent_id].update(data)
        self.agents[agent_id]["last_update"] = time.time()
        self.last_update = time.time()

    def add_log(self, message: str, level: str = "info", agent_id: str = None):
        """Add log entry."""
        entry = {
            "ts": time.time(),
            "msg": message,
            "level": level,
            "agent": agent_id,
        }
        self.global_logs.append(entry)
        if agent_id and agent_id in self.agent_logs:
            self.agent_logs[agent_id].append(entry)

    def update_memory(self, memory_data: dict):
        """Update cross-game memory stats from AgentMemory."""
        history = memory_data.get("overall", {}).get("history", {})
        self.memory["totalGames"] = history.get("totalGames", 0)
        self.memory["wins"] = history.get("wins", 0)
        self.memory["avgKills"] = history.get("avgKills", 0.0)
        self.memory["lessons"] = history.get("lessons", [])

    def record_game_result(self, kills: int, is_winner: bool,
                           final_rank: int, smoltz_earned: int = 0,
                           moltz_earned: int = 0):
        """Record game result into memory stats (v1.7.0)."""
        self.memory["totalGames"] += 1
        self.memory["gamesThisSession"] += 1
        if is_winner:
            self.memory["wins"] += 1
        self.memory["totalKills"] += kills
        self.memory["totalSmoltz"] += smoltz_earned
        self.memory["totalMoltz"] += moltz_earned
        if kills > self.memory["bestKills"]:
            self.memory["bestKills"] = kills
        # Rolling avg kills
        n = self.memory["totalGames"]
        old_avg = self.memory["avgKills"]
        self.memory["avgKills"] = round(((old_avg * (n-1)) + kills) / n, 2)
        # Rolling avg rank
        old_rank = self.memory["avgRank"]
        self.memory["avgRank"] = round(((old_rank * (n-1)) + final_rank) / n, 1)
        self.last_update = time.time()

    def set_account(self, account_data: dict):
        """Add or update account."""
        api_key = account_data.get("api_key", "")
        for i, acc in enumerate(self.accounts):
            if acc.get("api_key") == api_key:
                self.accounts[i] = account_data
                return
        self.accounts.append(account_data)

    # ── Dashboard reads ────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Full state snapshot for dashboard API."""
        return {
            "agents": dict(self.agents),
            "stats": {
                "total_wins": self.total_wins,
                "total_moltz": self.total_moltz,
                "total_smoltz": self.total_smoltz,
                "total_cross": self.total_cross,
                "bots_running": self.bots_running,
                "agents_active": sum(1 for a in self.agents.values()
                                     if a.get("status") == "playing"),
                "agents_idle": sum(1 for a in self.agents.values()
                                   if a.get("status") in ("idle", "queuing")),
                "agents_dead": sum(1 for a in self.agents.values()
                                   if a.get("status") == "dead"),
                "agents_error": sum(1 for a in self.agents.values()
                                    if a.get("status") == "error"),
                "uptime": time.time() - self.started_at,
            },
            "memory": dict(self.memory),
            "accounts": self.accounts,
            "logs": list(self.global_logs)[-200:],
            "agent_logs": {k: list(v)[-100:] for k, v in self.agent_logs.items()},
        }


# Global singleton
dashboard_state = DashboardState()
