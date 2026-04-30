"""
Action envelope builder + cooldown state tracker.
Builds action messages per actions.md spec.
"""
from bot.utils.logger import get_logger

log = get_logger(__name__)

# Group 1 actions (trigger 60s cooldown)
COOLDOWN_ACTIONS = {"move", "attack", "use_item", "interact", "rest"}
# Group 2 actions (no cooldown)
FREE_ACTIONS = {"pickup", "equip", "talk", "whisper", "broadcast"}


class ActionSender:
    """Tracks cooldown state and builds action envelopes."""

    def __init__(self):
        self.can_act = True
        self.cooldown_remaining_ms = 0

    def update_from_result(self, result: dict):
        """Update state from action_result payload.
        Per actions.md: canAct and cooldownRemainingMs are at TOP LEVEL of action_result.
        """
        if isinstance(result, dict):
            self.can_act = result.get("canAct", self.can_act)
            self.cooldown_remaining_ms = result.get("cooldownRemainingMs", 0)

    def update_from_can_act_changed(self, msg: dict):
        """Update state from can_act_changed server push."""
        self.can_act = msg.get("canAct", True)
        self.cooldown_remaining_ms = msg.get("cooldownRemainingMs", 0)

    def can_send_cooldown_action(self) -> bool:
        """Can we send a Group 1 (cooldown) action?"""
        return self.can_act

    def build_action(self, action_type: str, data: dict = None,
                     reasoning: str = "", planned_action: str = "") -> dict:
        """
        Build action envelope per actions.md spec.
        Truncates thought fields to spec limits.
        """
        payload = {
            "type": "action",
            "data": {"type": action_type, **(data or {})},
            "thought": {
                "reasoning": reasoning[:500],        # Max 500 chars
                "plannedAction": planned_action[:200],  # Max 200 chars
            },
        }
        return payload

    # ── Convenience builders ──────────────────────────────────────────

    def move(self, region_id: str, reason: str = "") -> dict:
        return self.build_action("move", {"regionId": region_id},
                                 reason, f"Move to {region_id}")

    def attack(self, target_id: str, target_type: str = "agent", reason: str = "") -> dict:
        return self.build_action("attack",
                                 {"targetId": target_id, "targetType": target_type},
                                 reason, f"Attack {target_type} {target_id[:8]}")

    def use_item(self, item_id: str, reason: str = "") -> dict:
        return self.build_action("use_item", {"itemId": item_id}, reason, "Use item")

    def interact(self, interactable_id: str, reason: str = "") -> dict:
        return self.build_action("interact", {"interactableId": interactable_id},
                                 reason, "Interact with facility")

    def rest(self, reason: str = "Conserving energy") -> dict:
        return self.build_action("rest", {}, reason, "Rest for +1 EP")

    def pickup(self, item_id: str) -> dict:
        return self.build_action("pickup", {"itemId": item_id}, "Collecting item", "Pickup")

    def equip(self, weapon_id: str) -> dict:
        return self.build_action("equip", {"itemId": weapon_id}, "Equipping weapon", "Equip")

    def talk(self, message: str) -> dict:
        return self.build_action("talk", {"message": message[:200]}, "", "Talk")

    def whisper(self, target_id: str, message: str) -> dict:
        return self.build_action("whisper",
                                 {"targetId": target_id, "message": message[:200]}, "", "Whisper")

    def broadcast(self, message: str) -> dict:
        """Per actions.md: requires megaphone item or broadcast_station facility.
        Sends message to all agents globally. Max 200 chars.
        """
        return self.build_action("broadcast", {"message": message[:200]}, "", "Broadcast")
