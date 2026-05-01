"""
Agent memory — persistent cross-game learning via molty-royale-context.json.
Two sections: `overall` (persistent) and `temp` (per-game).

v1.6.0: Persistent memory via Railway Variables API — lessons tidak hilang saat redeploy!
Memory disimpen di 2 tempat:
1. File lokal (temp, hilang saat redeploy)
2. Railway Variables BOT_MEMORY (permanen, sync setiap game selesai)
"""
import json
import os
import urllib.request
from pathlib import Path
from typing import Optional
from bot.config import MEMORY_DIR, MEMORY_FILE
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Railway API config — ambil dari env vars yang sudah ada
RAILWAY_API_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "")
RAILWAY_ENVIRONMENT_ID = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")

DEFAULT_MEMORY = {
    "overall": {
        "identity": {"name": "", "playstyle": "adaptive guardian hunter"},
        "strategy": {
            "deathzone": "move inward before turn 5",
            "guardians": "engage immediately — highest sMoltz value",
            "weather": "avoid combat in fog or storm",
            "ep_management": "rest when EP < 4 before engaging",
        },
        "history": {
            "totalGames": 0,
            "wins": 0,
            "avgKills": 0.0,
            "lessons": [],
        },
    },
    "temp": {},
}


class AgentMemory:
    """Read/write molty-royale-context.json with overall + temp sections."""

    def __init__(self):
        self.data = dict(DEFAULT_MEMORY)
        self._loaded = False

    async def load(self):
        """Load memory from disk + Railway Variables (v1.6.0)."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if MEMORY_FILE.exists():
            try:
                raw = MEMORY_FILE.read_text(encoding="utf-8")
                self.data = json.loads(raw)
                self._loaded = True
                log.info("Memory loaded: %d games, %d lessons",
                         self.data["overall"]["history"]["totalGames"],
                         len(self.data["overall"]["history"]["lessons"]))
            except (json.JSONDecodeError, KeyError) as e:
                log.warning("Memory file corrupt, using defaults: %s", e)
                self.data = dict(DEFAULT_MEMORY)
        else:
            log.info("No memory file — starting fresh")
        # v1.6.0: restore lessons dari Railway Variables (survive redeploy!)
        await self.load_from_railway()

    async def save(self):
        """Persist memory to disk AND sync to Railway Variables (v1.6.0)."""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.debug("Memory saved to %s", MEMORY_FILE)
        # v1.6.0: sync ke Railway Variables biar tidak hilang saat redeploy
        await self.sync_to_railway()

    def set_agent_name(self, name: str):
        self.data["overall"]["identity"]["name"] = name

    def get_strategy(self) -> dict:
        return self.data.get("overall", {}).get("strategy", {})

    def get_lessons(self) -> list:
        return self.data.get("overall", {}).get("history", {}).get("lessons", [])

    # ── Temp (per-game) ───────────────────────────────────────────────

    def set_temp_game(self, game_id: str):
        self.data["temp"] = {
            "gameId": game_id,
            "currentStrategy": "adaptive",
            "knownAgents": [],
            "notes": "",
        }

    def update_temp_note(self, note: str):
        if "temp" not in self.data:
            self.data["temp"] = {}
        existing = self.data["temp"].get("notes", "")
        self.data["temp"]["notes"] = f"{existing}\n{note}".strip()

    def clear_temp(self):
        self.data["temp"] = {}

    # ── History update (after game end) ───────────────────────────────

    def record_game_end(self, is_winner: bool, final_rank: int,
                        kills: int, smoltz_earned: int = 0):
        history = self.data["overall"]["history"]
        history["totalGames"] += 1
        if is_winner:
            history["wins"] += 1

        # Rolling average kills
        total = history["totalGames"]
        old_avg = history["avgKills"]
        history["avgKills"] = round(((old_avg * (total - 1)) + kills) / total, 2)

    def add_lesson(self, lesson: str, max_lessons: int = 20):
        """Append a new lesson, keeping max_lessons most recent."""
        lessons = self.data["overall"]["history"]["lessons"]
        if lesson not in lessons:
            lessons.append(lesson)
            if len(lessons) > max_lessons:
                lessons.pop(0)

    # ── Railway Variables persistent memory (v1.6.0) ─────────────────

    async def sync_to_railway(self):
        """
        Simpan memory ke Railway Variables sebagai BOT_MEMORY.
        Dipanggil setelah game selesai — data tidak hilang saat redeploy!
        """
        if not RAILWAY_API_TOKEN or not RAILWAY_SERVICE_ID or not RAILWAY_ENVIRONMENT_ID:
            log.debug("Railway sync skipped — env vars not set")
            return

        try:
            memory_json = json.dumps({
                "totalGames": self.data["overall"]["history"]["totalGames"],
                "wins": self.data["overall"]["history"]["wins"],
                "avgKills": self.data["overall"]["history"]["avgKills"],
                "lessons": self.data["overall"]["history"]["lessons"][-10:],  # 10 lessons terakhir
            }, ensure_ascii=False)

            query = """
            mutation UpsertVariables($input: VariableCollectionUpsertInput!) {
              variableCollectionUpsert(input: $input)
            }
            """
            variables = {
                "input": {
                    "projectId": os.environ.get("RAILWAY_PROJECT_ID", ""),
                    "environmentId": RAILWAY_ENVIRONMENT_ID,
                    "serviceId": RAILWAY_SERVICE_ID,
                    "variables": {
                        "BOT_MEMORY": memory_json
                    }
                }
            }

            payload = json.dumps({"query": query, "variables": variables}).encode()
            req = urllib.request.Request(
                "https://backboard.railway.app/graphql/v2",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if "errors" in result:
                    log.warning("Railway sync error: %s", result["errors"])
                else:
                    log.info("✅ Memory synced to Railway Variables (%d lessons, %d games)",
                             len(self.data["overall"]["history"]["lessons"]),
                             self.data["overall"]["history"]["totalGames"])
        except Exception as e:
            log.warning("Railway sync failed (non-critical): %s", e)

    async def load_from_railway(self):
        """
        Load memory dari Railway Variables BOT_MEMORY saat startup.
        Restore lessons yang tersimpan dari game-game sebelumnya.
        """
        if not RAILWAY_API_TOKEN:
            return

        try:
            bot_memory = os.environ.get("BOT_MEMORY", "")
            if bot_memory:
                saved = json.loads(bot_memory)
                history = self.data["overall"]["history"]

                # Restore data, tapi jangan overwrite kalau lokal lebih baru
                if saved.get("totalGames", 0) > history.get("totalGames", 0):
                    history["totalGames"] = saved["totalGames"]
                    history["wins"] = saved.get("wins", 0)
                    history["avgKills"] = saved.get("avgKills", 0.0)

                # Merge lessons — gabungkan lokal + railway, hapus duplikat
                saved_lessons = saved.get("lessons", [])
                current_lessons = history.get("lessons", [])
                merged = list(dict.fromkeys(saved_lessons + current_lessons))[-20:]
                history["lessons"] = merged

                log.info("✅ Memory restored from Railway: %d games, %d lessons",
                         history["totalGames"], len(history["lessons"]))
        except Exception as e:
            log.warning("Railway memory load failed (non-critical): %s", e)
