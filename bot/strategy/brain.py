"""
Strategy brain — main decision engine with priority-based action selection.
Implements the game-loop.md priority chain for high win rate.

v1.5.4 improvements:
- Combat lebih agresif: serang player kalau HP enemy < HP kita, atau enemy HP < 50, atau bisa habis dalam 3 hit
- HP threshold combat diturunkan: 35 (early game) / 20 (late game)
- Heal threshold dinaikkan ke HP < 80 (was 70) — selalu fit sebelum combat
- Movement prioritas weapon — bonus score +8 kalau ada weapon di region tujuan
- Tetap backward compatible dengan semua fix v1.5.3

v1.5.3 fixes:
- Removed duplicate _known_agents definition (was at line 99 AND 412)
- Monster farming now requires HP >= 35 (was no HP check)
- Guardian flee threshold raised HP < 55 (was < 40, too risky)
- Memory/lessons integration: brain reads cross-game lessons for adaptive behavior
- Late game pursuit: bot actively moves toward last known enemy location
- can_act_changed guard: skip dead agent re-evaluation

Uses ALL view fields from api-summary.md:
- self: agent stats, inventory, equipped weapon
- currentRegion: terrain, weather, connections, facilities
- connectedRegions: adjacent regions (full Region object when visible, bare string ID when out-of-vision)
- visibleRegions: all regions in vision range
- visibleAgents: other agents (players + guardians — guardians are HOSTILE)
- visibleMonsters: monsters
- visibleNPCs: NPCs (flavor — safe to ignore per game-systems.md)
- visibleItems: ground items in visible regions
- pendingDeathzones: regions becoming death zones next ({id, name} entries)
- recentLogs: recent gameplay events
- recentMessages: regional/private/broadcast messages
- aliveCount: remaining alive agents
"""
from bot.utils.logger import get_logger

log = get_logger(__name__)

# ── Weapon stats from combat-items.md ─────────────────────────────────
WEAPONS = {
    "fist": {"bonus": 0, "range": 0},
    "dagger": {"bonus": 10, "range": 0},
    "sword": {"bonus": 20, "range": 0},
    "katana": {"bonus": 35, "range": 0},
    "bow": {"bonus": 5, "range": 1},
    "pistol": {"bonus": 10, "range": 1},
    "sniper": {"bonus": 28, "range": 2},
}

WEAPON_PRIORITY = ["katana", "sniper", "sword", "pistol", "dagger", "bow", "fist"]

# ── Item priority for pickup ──────────────────────────────────────────
ITEM_PRIORITY = {
    "rewards": 300,
    "katana": 100, "sniper": 95, "sword": 90, "pistol": 85,
    "dagger": 80, "bow": 75,
    "medkit": 70, "bandage": 65, "emergency_food": 60, "energy_drink": 58,
    "binoculars": 55,
    "map": 52,
    "megaphone": 40,
}

# ── Recovery items for healing ────────────────────────────────────────
RECOVERY_ITEMS = {
    "medkit": 50, "bandage": 30, "emergency_food": 20,
    "energy_drink": 0,
}

# Weather combat penalty per game-systems.md
WEATHER_COMBAT_PENALTY = {
    "clear": 0.0,
    "rain": 0.05,
    "fog": 0.10,
    "storm": 0.15,
}

# ── Single definition of global state ────────────────────────────────
# FIX v1.5.3: removed duplicate _known_agents that was also defined at line 412
_known_agents: dict = {}
_map_knowledge: dict = {"revealed": False, "death_zones": set(), "safe_center": []}
# FIX v1.5.6: track picked up item IDs to prevent double-pickup on stale view
_picked_up_ids: set = set()


def calc_damage(atk: int, weapon_bonus: int, target_def: int,
                weather: str = "clear") -> int:
    """Damage formula per combat-items.md + game-systems.md weather penalty."""
    base = atk + weapon_bonus - int(target_def * 0.5)
    penalty = WEATHER_COMBAT_PENALTY.get(weather, 0.0)
    return max(1, int(base * (1 - penalty)))


def get_weapon_bonus(equipped_weapon) -> int:
    if not equipped_weapon:
        return 0
    type_id = equipped_weapon.get("typeId", "").lower()
    return WEAPONS.get(type_id, {}).get("bonus", 0)


def get_weapon_range(equipped_weapon) -> int:
    if not equipped_weapon:
        return 0
    type_id = equipped_weapon.get("typeId", "").lower()
    return WEAPONS.get(type_id, {}).get("range", 0)


def _resolve_region(entry, view: dict):
    """Resolve connectedRegions entry to full region object or None."""
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, str):
        for r in view.get("visibleRegions", []):
            if isinstance(r, dict) and r.get("id") == entry:
                return r
    return None


def _get_region_id(entry) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("id", "")
    return ""


def reset_game_state():
    """Reset per-game tracking state. Call when game ends."""
    global _known_agents, _map_knowledge, _picked_up_ids
    _known_agents = {}
    _map_knowledge = {"revealed": False, "death_zones": set(), "safe_center": []}
    _picked_up_ids = set()
    log.info("Strategy brain reset for new game")


def mark_item_picked_up(item_id: str):
    """FIX v1.5.6: Mark an item as picked up so brain won't try again on stale view."""
    global _picked_up_ids
    _picked_up_ids.add(item_id)


def decide_action(view: dict, can_act: bool, lessons: list = None) -> dict | None:
    """
    Main decision engine. Returns action dict or None (wait).

    Priority chain per game-loop.md §3 (v1.5.3):
    1. DEATHZONE ESCAPE
    1b. Pre-escape pending death zone
    2. [DISABLED] Curse resolution
    2b. Guardian threat evasion
    3. Critical healing
    3b. Use utility items (Map, Energy Drink)
    4. Free actions (pickup, equip)
    5. Guardian farming
    6. Favorable agent combat
    7. Monster farming (HP >= 35 required — FIX v1.5.3)
    8. Facility interaction
    9. Strategic movement + late game pursuit (NEW v1.5.3)
    10. Rest

    lessons: list of cross-game lessons from AgentMemory (NEW v1.5.3)
    """
    self_data = view.get("self", {})
    region = view.get("currentRegion", {})
    hp = self_data.get("hp", 100)
    ep = self_data.get("ep", 10)
    max_ep = self_data.get("maxEp", 10)
    atk = self_data.get("atk", 10)
    defense = self_data.get("def", 5)
    is_alive = self_data.get("isAlive", True)
    inventory = self_data.get("inventory", [])
    equipped = self_data.get("equippedWeapon")

    visible_agents = view.get("visibleAgents", [])
    visible_monsters = view.get("visibleMonsters", [])
    visible_items_raw = view.get("visibleItems", [])

    visible_items = []
    for entry in visible_items_raw:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("item")
        if isinstance(inner, dict):
            inner["regionId"] = entry.get("regionId", "")
            visible_items.append(inner)
        elif entry.get("id"):
            visible_items.append(entry)

    visible_regions = view.get("visibleRegions", [])
    connected_regions = view.get("connectedRegions", [])
    pending_dz = view.get("pendingDeathzones", [])
    alive_count = view.get("aliveCount", 100)

    connections = connected_regions or region.get("connections", [])
    interactables = region.get("interactables", [])
    region_id = region.get("id", "")
    region_terrain = region.get("terrain", "").lower() if isinstance(region, dict) else ""
    region_weather = region.get("weather", "").lower() if isinstance(region, dict) else ""

    if not is_alive:
        return None

    # ── Parse cross-game lessons for adaptive behavior (NEW v1.5.3) ──
    # Default thresholds
    guardian_flee_hp = 55      # FIX: raised from 40 → 55
    be_aggressive = False
    avoid_combat_weather = region_weather in ("fog", "storm")

    if lessons:
        # If bot has been dying with zero kills, be more aggressive on guardian
        if any("zero kills" in l.lower() for l in lessons):
            be_aggressive = True
            log.debug("Lesson applied: zero kills history → aggressive guardian mode")
        # If bot has won before, stay conservative
        if any("won with" in l.lower() for l in lessons):
            guardian_flee_hp = 50  # Slightly less cautious

    # ── Build danger map ──────────────────────────────────────────────
    danger_ids = set()
    for dz in pending_dz:
        if isinstance(dz, dict):
            danger_ids.add(dz.get("id", ""))
        elif isinstance(dz, str):
            danger_ids.add(dz)
    for conn in connections:
        resolved = _resolve_region(conn, view)
        if resolved and resolved.get("isDeathZone"):
            danger_ids.add(resolved.get("id", ""))

    _track_agents(visible_agents, self_data.get("id", ""), region_id)

    move_ep_cost = _get_move_ep_cost(region_terrain, region_weather)

    # ── Priority 1: DEATHZONE ESCAPE ──────────────────────────────────
    if region.get("isDeathZone", False):
        safe = _find_safe_region(connections, danger_ids, view)
        if safe and ep >= move_ep_cost:
            log.warning("🚨 IN DEATH ZONE! Escaping to %s (HP=%d)", safe, hp)
            return {"action": "move", "data": {"regionId": safe},
                    "reason": f"ESCAPE: In death zone! HP={hp} dropping fast (1.34/sec)"}
        elif not safe:
            log.error("🚨 IN DEATH ZONE but NO SAFE REGION!")

    # ── Priority 1b: Pre-escape pending DZ ───────────────────────────
    if region_id in danger_ids:
        safe = _find_safe_region(connections, danger_ids, view)
        if safe and ep >= move_ep_cost:
            log.warning("⚠️ Region %s becoming DZ soon! Escaping to %s", region_id[:8], safe)
            return {"action": "move", "data": {"regionId": safe},
                    "reason": "PRE-ESCAPE: Region becoming death zone soon"}

    # ── Priority 2: Curse — DISABLED v1.5.2 ──────────────────────────

    # ── Priority 2b: Guardian threat evasion ─────────────────────────
    # FIX v1.5.3: threshold raised from HP < 40 → HP < 55
    guardians_here = [a for a in visible_agents
                      if a.get("isGuardian", False) and a.get("isAlive", True)
                      and a.get("regionId") == region_id]
    if guardians_here and hp < guardian_flee_hp and ep >= move_ep_cost:
        safe = _find_safe_region(connections, danger_ids, view)
        if safe:
            log.warning("⚠️ Guardian threat! HP=%d (threshold=%d), fleeing", hp, guardian_flee_hp)
            return {"action": "move", "data": {"regionId": safe},
                    "reason": f"GUARDIAN FLEE: HP={hp}, guardian in region, too dangerous"}

    # ── Priority 3: EMERGENCY healing — SEBELUM can_act check! ─────────
    # FIX v1.5.5: use_item adalah free action, tidak butuh can_act=True
    if hp < 30:
        heal = _find_healing_item(inventory, critical=True)
        if heal:
            log.warning("🚨 EMERGENCY HEAL: HP=%d, using %s", hp, heal.get("typeId", "heal"))
            return {"action": "use_item", "data": {"itemId": heal["id"]},
                    "reason": f"EMERGENCY HEAL: HP={hp} CRITICAL! using {heal.get('typeId', 'heal')}"}
    elif hp < 80:
        heal = _find_healing_item(inventory, critical=False)
        if heal:
            return {"action": "use_item", "data": {"itemId": heal["id"]},
                    "reason": f"HEAL: HP={hp}, using {heal.get('typeId', 'heal')}"}

    # ── FREE ACTIONS ──────────────────────────────────────────────────
    pickup_action = _check_pickup(visible_items, inventory, region_id)
    if pickup_action:
        return pickup_action

    equip_action = _check_equip(inventory, equipped)
    if equip_action:
        return equip_action

    util_action = _use_utility_item(inventory, hp, ep, alive_count)
    if util_action:
        return util_action

    if not can_act:
        return None

    # ── Priority 4: EP recovery ───────────────────────────────────────
    if ep == 0:
        energy_drink = _find_energy_drink(inventory)
        if energy_drink:
            return {"action": "use_item", "data": {"itemId": energy_drink["id"]},
                    "reason": "EP RECOVERY: EP=0, using energy drink (+5 EP)"}

    # ── Priority 5: Guardian farming ──────────────────────────────────
    # Aggressive mode (from lessons) lowers HP requirement to 25
    guardian_fight_hp = 25 if be_aggressive else 35
    guardians = [a for a in visible_agents
                 if a.get("isGuardian", False) and a.get("isAlive", True)]
    if guardians and ep >= 2 and hp >= guardian_fight_hp:
        target = _select_weakest(guardians)
        w_range = get_weapon_range(equipped)
        if _is_in_range(target, region_id, w_range, connections):
            my_dmg = calc_damage(atk, get_weapon_bonus(equipped),
                                 target.get("def", 5), region_weather)
            guardian_dmg = calc_damage(target.get("atk", 10),
                                       _estimate_enemy_weapon_bonus(target),
                                       defense, region_weather)
            if my_dmg >= guardian_dmg or target.get("hp", 100) <= my_dmg * 3:
                return {"action": "attack",
                        "data": {"targetId": target["id"], "targetType": "agent"},
                        "reason": f"GUARDIAN FARM: HP={target.get('hp','?')} "
                                  f"(120 sMoltz! dmg={my_dmg} vs {guardian_dmg})"}

    # ── Priority 6: Favorable agent combat ───────────────────────────
    # IMPROVED v1.5.4: attack lebih agresif — serang kalau ada kesempatan menang
    hp_threshold = 35 if alive_count > 20 else 20
    enemies = [a for a in visible_agents
               if not a.get("isGuardian", False) and a.get("isAlive", True)
               and a.get("id") != self_data.get("id")]
    if enemies and ep >= 2 and hp >= hp_threshold and not avoid_combat_weather:
        target = _select_weakest(enemies)
        w_range = get_weapon_range(equipped)
        if _is_in_range(target, region_id, w_range, connections):
            my_dmg = calc_damage(atk, get_weapon_bonus(equipped),
                                 target.get("def", 5), region_weather)
            enemy_dmg = calc_damage(target.get("atk", 10),
                                    _estimate_enemy_weapon_bonus(target),
                                    defense, region_weather)
            enemy_hp = target.get("hp", 100)
            # IMPROVED: serang kalau:
            # - dmg kita lebih besar, ATAU
            # - HP enemy <= 3x dmg kita (bisa habis dalam 3 hit), ATAU
            # - HP kita lebih tinggi dari enemy (kita unggul), ATAU
            # - enemy HP di bawah 50 (enemy udah lemah)
            should_attack = (
                my_dmg > enemy_dmg
                or enemy_hp <= my_dmg * 3
                or hp > enemy_hp
                or enemy_hp < 50
            )
            if should_attack:
                return {"action": "attack",
                        "data": {"targetId": target["id"], "targetType": "agent"},
                        "reason": f"COMBAT: Target HP={enemy_hp}, "
                                  f"my_dmg={my_dmg} vs enemy_dmg={enemy_dmg}, our_hp={hp}"}

    # ── Priority 7: Monster farming ───────────────────────────────────
    # FIX v1.5.3: added HP >= 35 check (was no HP check — could fight while dying)
    monsters = [m for m in visible_monsters if m.get("hp", 0) > 0]
    if monsters and ep >= 2 and hp >= 35:
        target = _select_weakest(monsters)
        w_range = get_weapon_range(equipped)
        if _is_in_range(target, region_id, w_range, connections):
            return {"action": "attack",
                    "data": {"targetId": target["id"], "targetType": "monster"},
                    "reason": f"MONSTER FARM: {target.get('name', 'monster')} HP={target.get('hp', '?')}"}

    # ── Priority 7b: Moderate healing in safe area ────────────────────
    if hp < 70 and not enemies:
        heal = _find_healing_item(inventory, critical=(hp < 30))
        if heal:
            return {"action": "use_item", "data": {"itemId": heal["id"]},
                    "reason": f"HEAL: HP={hp}, area safe, using {heal.get('typeId', 'heal')}"}

    # ── Priority 8: Facility interaction ──────────────────────────────
    if interactables and ep >= 2 and not region.get("isDeathZone"):
        facility = _select_facility(interactables, hp, ep)
        if facility:
            return {"action": "interact",
                    "data": {"interactableId": facility["id"]},
                    "reason": f"FACILITY: {facility.get('type', 'unknown')}"}

    # ── Priority 9: Strategic movement + late game pursuit ───────────
    if ep >= move_ep_cost and connections:
        # NEW v1.5.3: late game (< 10 alive) → pursue last known enemy
        if alive_count < 10 and _known_agents:
            pursue_target = _find_pursuit_target(connections, danger_ids)
            if pursue_target:
                return {"action": "move", "data": {"regionId": pursue_target},
                        "reason": f"PURSUE: Late game ({alive_count} alive), moving toward last known enemy"}

        move_target = _choose_move_target(connections, danger_ids,
                                          region, visible_items, alive_count)
        if move_target:
            return {"action": "move", "data": {"regionId": move_target},
                    "reason": "EXPLORE: Moving to better position"}

    # ── Priority 10: Rest ─────────────────────────────────────────────
    if ep < 4 and not enemies and not region.get("isDeathZone") and region_id not in danger_ids:
        return {"action": "rest", "data": {},
                "reason": f"REST: EP={ep}/{max_ep}, area is safe (+1 bonus EP)"}

    return None


# ── Helper functions ───────────────────────────────────────────────────

def _get_move_ep_cost(terrain: str, weather: str) -> int:
    if terrain == "water":
        return 3
    if weather == "storm":
        return 3
    return 2


def _estimate_enemy_weapon_bonus(agent: dict) -> int:
    weapon = agent.get("equippedWeapon")
    if not weapon:
        return 0
    type_id = weapon.get("typeId", "").lower() if isinstance(weapon, dict) else ""
    return WEAPONS.get(type_id, {}).get("bonus", 0)


def _track_agents(visible_agents: list, my_id: str, my_region: str):
    """Track observed agents for threat assessment."""
    global _known_agents
    for agent in visible_agents:
        if not isinstance(agent, dict):
            continue
        aid = agent.get("id", "")
        if not aid or aid == my_id:
            continue
        _known_agents[aid] = {
            "hp": agent.get("hp", 100),
            "atk": agent.get("atk", 10),
            "isGuardian": agent.get("isGuardian", False),
            "equippedWeapon": agent.get("equippedWeapon"),
            "lastSeen": my_region,
            "regionId": agent.get("regionId", my_region),
            "isAlive": agent.get("isAlive", True),
        }
    if len(_known_agents) > 50:
        dead = [k for k, v in _known_agents.items() if not v.get("isAlive", True)]
        for d in dead:
            del _known_agents[d]


def _find_pursuit_target(connections, danger_ids: set) -> str | None:
    """NEW v1.5.3: Find connected region where an enemy was last seen.
    Used in late game to actively pursue remaining enemies.
    """
    conn_ids = set()
    for conn in connections:
        rid = conn if isinstance(conn, str) else conn.get("id", "")
        if rid and rid not in danger_ids:
            conn_ids.add(rid)

    # Find alive non-guardian enemies last seen in a connected region
    for aid, data in _known_agents.items():
        if not data.get("isAlive", True):
            continue
        if data.get("isGuardian", False):
            continue
        last_region = data.get("regionId", data.get("lastSeen", ""))
        if last_region in conn_ids:
            log.info("PURSUE: Enemy %s last seen at %s", aid[:8], last_region[:8])
            return last_region
    return None


def _use_utility_item(inventory: list, hp: int, ep: int, alive_count: int) -> dict | None:
    for item in inventory:
        if not isinstance(item, dict):
            continue
        type_id = item.get("typeId", "").lower()
        if type_id == "map":
            log.info("🗺️ Using Map! Will reveal entire map for strategic learning.")
            return {"action": "use_item", "data": {"itemId": item["id"]},
                    "reason": "UTILITY: Using Map — reveals entire map for DZ tracking"}
    return None


def learn_from_map(view: dict):
    """Called after Map is used — learn entire map layout."""
    global _map_knowledge
    visible_regions = view.get("visibleRegions", [])
    if not visible_regions:
        return

    _map_knowledge["revealed"] = True
    safe_regions = []

    for region in visible_regions:
        if not isinstance(region, dict):
            continue
        rid = region.get("id", "")
        if not rid:
            continue
        if region.get("isDeathZone"):
            _map_knowledge["death_zones"].add(rid)
        else:
            conns = region.get("connections", [])
            terrain = region.get("terrain", "").lower()
            terrain_value = {"hills": 3, "plains": 2, "ruins": 2, "forest": 1, "water": -1}.get(terrain, 0)
            score = len(conns) + terrain_value
            safe_regions.append((rid, score))

    safe_regions.sort(key=lambda x: x[1], reverse=True)
    _map_knowledge["safe_center"] = [r[0] for r in safe_regions[:5]]

    log.info("🗺️ MAP LEARNED: %d DZ regions, top center: %s",
             len(_map_knowledge["death_zones"]),
             _map_knowledge["safe_center"][:3])


def _check_pickup(items: list, inventory: list, region_id: str) -> dict | None:
    if len(inventory) >= 10:
        return None
    # FIX v1.5.6: filter out items already picked up (stale view protection)
    local_items = [i for i in items
                   if isinstance(i, dict)
                   and i.get("regionId") == region_id
                   and i.get("id") not in _picked_up_ids]
    if not local_items:
        local_items = [i for i in items
                       if isinstance(i, dict)
                       and i.get("id")
                       and i.get("id") not in _picked_up_ids]
    if not local_items:
        return None

    heal_count = sum(1 for i in inventory if isinstance(i, dict)
                     and i.get("typeId", "").lower() in RECOVERY_ITEMS
                     and RECOVERY_ITEMS.get(i.get("typeId", "").lower(), 0) > 0)

    local_items.sort(key=lambda i: _pickup_score(i, inventory, heal_count), reverse=True)
    best = local_items[0]
    score = _pickup_score(best, inventory, heal_count)
    if score > 0:
        type_id = best.get('typeId', 'item')
        log.info("PICKUP: %s (score=%d)", type_id, score)
        return {"action": "pickup", "data": {"itemId": best["id"]},
                "reason": f"PICKUP: {type_id}"}
    return None


def _pickup_score(item: dict, inventory: list, heal_count: int) -> int:
    type_id = item.get("typeId", "").lower()
    category = item.get("category", "").lower()

    if type_id == "rewards" or category == "currency":
        return 300

    if category == "weapon":
        bonus = WEAPONS.get(type_id, {}).get("bonus", 0)
        current_best = 0
        for inv_item in inventory:
            if isinstance(inv_item, dict) and inv_item.get("category") == "weapon":
                cb = WEAPONS.get(inv_item.get("typeId", "").lower(), {}).get("bonus", 0)
                current_best = max(current_best, cb)
        if bonus > current_best:
            return 100 + bonus
        return 0

    if type_id == "binoculars":
        has_binos = any(isinstance(i, dict) and i.get("typeId", "").lower() == "binoculars"
                        for i in inventory)
        return 55 if not has_binos else 0

    if type_id == "map":
        return 52

    if type_id in RECOVERY_ITEMS and RECOVERY_ITEMS.get(type_id, 0) > 0:
        if heal_count < 4:
            return ITEM_PRIORITY.get(type_id, 0) + 10
        return ITEM_PRIORITY.get(type_id, 0)

    if type_id == "energy_drink":
        return 58

    return ITEM_PRIORITY.get(type_id, 0)


def _check_equip(inventory: list, equipped) -> dict | None:
    current_bonus = get_weapon_bonus(equipped) if equipped else 0
    best = None
    best_bonus = current_bonus
    for item in inventory:
        if not isinstance(item, dict):
            continue
        if item.get("category") == "weapon":
            type_id = item.get("typeId", "").lower()
            bonus = WEAPONS.get(type_id, {}).get("bonus", 0)
            if bonus > best_bonus:
                best = item
                best_bonus = bonus
    if best:
        return {"action": "equip", "data": {"itemId": best["id"]},
                "reason": f"EQUIP: {best.get('typeId', 'weapon')} (+{best_bonus} ATK)"}
    return None


def _find_safe_region(connections, danger_ids: set, view: dict = None) -> str | None:
    safe_regions = []
    for conn in connections:
        if isinstance(conn, str):
            if conn not in danger_ids:
                safe_regions.append((conn, 0))
        elif isinstance(conn, dict):
            rid = conn.get("id", "")
            is_dz = conn.get("isDeathZone", False)
            if rid and not is_dz and rid not in danger_ids:
                terrain = conn.get("terrain", "").lower()
                score = {"hills": 3, "plains": 2, "ruins": 1, "forest": 0, "water": -2}.get(terrain, 0)
                safe_regions.append((rid, score))

    if safe_regions:
        safe_regions.sort(key=lambda x: x[1], reverse=True)
        return safe_regions[0][0]

    for conn in connections:
        rid = conn if isinstance(conn, str) else conn.get("id", "")
        is_dz = conn.get("isDeathZone", False) if isinstance(conn, dict) else False
        if rid and not is_dz:
            log.warning("No fully safe region! Using fallback: %s", rid[:8])
            return rid
    return None


def _find_healing_item(inventory: list, critical: bool = False) -> dict | None:
    heals = []
    for i in inventory:
        if not isinstance(i, dict):
            continue
        type_id = i.get("typeId", "").lower()
        if type_id in RECOVERY_ITEMS and RECOVERY_ITEMS[type_id] > 0:
            heals.append(i)
    if not heals:
        return None

    if critical:
        heals.sort(key=lambda i: RECOVERY_ITEMS.get(i.get("typeId", "").lower(), 0), reverse=True)
    else:
        heals.sort(key=lambda i: RECOVERY_ITEMS.get(i.get("typeId", "").lower(), 0))
    return heals[0]


def _find_energy_drink(inventory: list) -> dict | None:
    for i in inventory:
        if isinstance(i, dict) and i.get("typeId", "").lower() == "energy_drink":
            return i
    return None


def _select_weakest(targets: list) -> dict:
    return min(targets, key=lambda t: t.get("hp", 999))


def _is_in_range(target: dict, my_region: str, weapon_range: int,
                  connections=None) -> bool:
    target_region = target.get("regionId", "")
    if not target_region:
        return True
    if target_region == my_region:
        return True

    if weapon_range >= 1 and connections:
        adj_ids = set()
        for conn in connections:
            if isinstance(conn, str):
                adj_ids.add(conn)
            elif isinstance(conn, dict):
                adj_ids.add(conn.get("id", ""))
        if target_region in adj_ids:
            return True
    return False


def _select_facility(interactables: list, hp: int, ep: int) -> dict | None:
    for fac in interactables:
        if not isinstance(fac, dict):
            continue
        if fac.get("isUsed"):
            continue
        ftype = fac.get("type", "").lower()
        if ftype == "medical_facility" and hp < 80:
            return fac
        if ftype == "supply_cache":
            return fac
        if ftype == "watchtower":
            return fac
        if ftype == "broadcast_station":
            return fac
    return None


def _choose_move_target(connections, danger_ids: set,
                         current_region: dict, visible_items: list,
                         alive_count: int) -> str | None:
    candidates = []
    item_regions = set()
    for item in visible_items:
        if isinstance(item, dict):
            item_regions.add(item.get("regionId", ""))

    for conn in connections:
        if isinstance(conn, str):
            if conn in danger_ids:
                continue
            score = 1
            if conn in item_regions:
                score += 5
            candidates.append((conn, score))

        elif isinstance(conn, dict):
            rid = conn.get("id", "")
            if not rid or conn.get("isDeathZone") or rid in danger_ids:
                continue

            score = 0
            terrain = conn.get("terrain", "").lower()
            terrain_scores = {"hills": 4, "plains": 2, "ruins": 2, "forest": 1, "water": -3}
            score += terrain_scores.get(terrain, 0)

            if rid in item_regions:
                score += 5

            # IMPROVED v1.5.4: bonus score kalau ada weapon di region itu
            for item in visible_items:
                if isinstance(item, dict) and item.get("regionId") == rid:
                    if item.get("category") == "weapon":
                        score += 8  # weapon sangat prioritas
                    elif item.get("typeId", "").lower() in ("medkit", "bandage"):
                        score += 3

            facs = conn.get("interactables", [])
            if facs:
                unused = [f for f in facs if isinstance(f, dict) and not f.get("isUsed")]
                score += len(unused) * 2

            weather = conn.get("weather", "").lower()
            weather_penalty = {"storm": -2, "fog": -1, "rain": 0, "clear": 1}
            score += weather_penalty.get(weather, 0)

            if alive_count < 30:
                score += 3

            if _map_knowledge.get("revealed") and rid in _map_knowledge.get("safe_center", []):
                score += 5

            if rid in _map_knowledge.get("death_zones", set()):
                continue

            candidates.append((rid, score))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
