"""Stage 005 intent routing and drag/drop tests.

The acceptance intent table (equip/craft/discard/select/move) lives only in
these fixtures — it is a validation case, not SDK public API. The router must
keep a rejected or unroutable drop from mutating any domain state.
"""

from __future__ import annotations

import asyncio
import unittest

from neon3_sdk.errors import DropRejectedError, UnknownTargetError, UnsupportedIntentError
from neon3_sdk.models import DropEvent, IntentEvent
from neon3_sdk.routing import IntentRouter


def drop_inbound(source_key: str, target_key: str, *, intent=None, sequence=1, epoch=1) -> dict:
    event = {
        "event_id": f"evt-{source_key}-{target_key}",
        "drag_key": source_key,
        "drop_key": target_key,
        "payload": {"source_key": source_key, "target_key": target_key, "placement": "into"},
        "interaction": {"sequence": sequence, "renderer_epoch": epoch},
    }
    if intent is not None:
        event["intent"] = intent
    return {"kind": "drag_drop", "event": event}


def inventory_fixture():
    """Backpack-shaped fixture: three items, three targets, one catalog."""
    router = IntentRouter()
    items = {
        "backpack-compass": {"id": "compass", "kind": "accessory", "slot": "trinket"},
        "backpack-potion": {"id": "potion", "kind": "consumable", "count": 3},
        "backpack-gem": {"id": "gem", "kind": "material"},
    }
    router.catalog(items)
    payload = lambda item: {"item_id": item["id"], "kind": item["kind"]}
    kind_of = lambda item: item["kind"]
    for key in items:
        router.drag_source(key, payload=payload, kind_of=kind_of)
    router.drop_target("equipment-zone", "inventory.item.equip", accepts=("accessory",))
    router.drop_target("crafting-zone", "inventory.item.craft", accepts=("material", "consumable"))
    router.drop_target("discard-zone", "inventory.item.discard")  # accepts anything

    state = {"equipped": None, "crafted": None, "discarded": None}
    router.on("inventory.item.equip")(lambda event: state.__setitem__("equipped", event.payload["item_id"]))
    router.on("inventory.item.craft")(lambda event: state.__setitem__("crafted", event.payload["item_id"]))
    router.on("inventory.item.discard")(lambda event: state.__setitem__("discarded", event.payload["item_id"]))
    return router, state


class RouterMatchingTests(unittest.TestCase):
    def test_exact_prefix_and_default(self) -> None:
        router = IntentRouter()
        calls = []
        router.on("app.save", lambda e: calls.append(("exact", e.intent)))
        router.on("app.*", lambda e: calls.append(("prefix", e.intent)))
        router.default(lambda e: calls.append(("default", e.intent)))
        asyncio.run(router.dispatch(IntentEvent(event_id="1", intent="app.save", source_node_key="n")))
        asyncio.run(router.dispatch(IntentEvent(event_id="2", intent="app.open", source_node_key="n")))
        asyncio.run(router.dispatch(IntentEvent(event_id="3", intent="other", source_node_key="n")))
        self.assertEqual(calls, [("exact", "app.save"), ("prefix", "app.open"), ("default", "other")])

    def test_unknown_intent_raises_structured_error(self) -> None:
        router = IntentRouter()
        router.on("known", lambda e: None)
        with self.assertRaises(UnsupportedIntentError) as caught:
            asyncio.run(router.dispatch(IntentEvent(event_id="1", intent="missing", source_node_key="n")))
        self.assertEqual(caught.exception.intent, "missing")
        self.assertEqual(caught.exception.code, "unsupported_intent")

    def test_async_handler_awaited(self) -> None:
        router = IntentRouter()
        seen = {}

        async def handler(event):
            seen["intent"] = event.intent
            return "publication-marker"

        router.on("slow.task", handler)
        result = asyncio.run(router.dispatch(IntentEvent(event_id="1", intent="slow.task", source_node_key="n")))
        self.assertEqual(seen["intent"], "slow.task")
        self.assertEqual(result, "publication-marker")


class DragDropTests(unittest.TestCase):
    def test_three_drops_trigger_their_intents(self) -> None:
        router, state = inventory_fixture()
        asyncio.run(router.dispatch(drop_inbound("backpack-compass", "equipment-zone")))
        asyncio.run(router.dispatch(drop_inbound("backpack-gem", "crafting-zone")))
        asyncio.run(router.dispatch(drop_inbound("backpack-potion", "discard-zone")))
        self.assertEqual(state, {"equipped": "compass", "crafted": "gem", "discarded": "potion"})

    def test_drop_carries_resolved_business_payload(self) -> None:
        router, _ = inventory_fixture()
        resolved = router.resolve_inbound(drop_inbound("backpack-compass", "equipment-zone"))
        self.assertIsInstance(resolved, DropEvent)
        self.assertEqual(resolved.payload, {"item_id": "compass", "kind": "accessory"})
        self.assertEqual(resolved.source_key, "backpack-compass")
        self.assertEqual(resolved.target_key, "equipment-zone")
        self.assertEqual(resolved.placement, "into")
        self.assertEqual(resolved.frame_sequence, 1)
        self.assertEqual(resolved.generation, 1)

    def test_target_rejection_leaves_state_untouched(self) -> None:
        router, state = inventory_fixture()
        # gem (material) dropped on the equipment zone (accepts accessory only).
        with self.assertRaises(DropRejectedError) as caught:
            asyncio.run(router.dispatch(drop_inbound("backpack-gem", "equipment-zone")))
        self.assertEqual(caught.exception.code, "drop_rejected")
        self.assertEqual(caught.exception.details["accepted"], ["accessory"])
        self.assertIsNone(state["equipped"])  # domain state unchanged

    def test_missing_source_or_target_is_unknown_target_not_rejection(self) -> None:
        router, _ = inventory_fixture()
        with self.assertRaises(UnknownTargetError) as caught:
            asyncio.run(router.dispatch(drop_inbound("backpack-compass", "ghost-zone")))
        self.assertEqual(caught.exception.code, "unknown_target")
        with self.assertRaises(UnknownTargetError):
            asyncio.run(router.dispatch(drop_inbound("ghost-item", "equipment-zone")))

    def test_accepts_none_target_accepts_any_kind(self) -> None:
        router, _ = inventory_fixture()
        # discard-zone declares no accepts, so any kind routes.
        asyncio.run(router.dispatch(drop_inbound("backpack-gem", "discard-zone")))

    def test_semantic_intent_envelope_resolves_to_intent_event(self) -> None:
        router = IntentRouter()
        resolved = router.resolve_inbound({"kind": "semantic_intent", "event": {
            "event_id": "e", "intent": "inventory.item.select", "source_node_key": "row-1",
            "payload": {"item_id": {"kind": "enum", "value": "compass"}}, "input_revision": 4,
            "program_revision": {"revision": 1}, "interaction": {"interaction_id": "e", "sequence": 2, "renderer_epoch": 1},
        }})
        self.assertIsInstance(resolved, IntentEvent)
        self.assertEqual(resolved.input_revision, 4)
        self.assertEqual(resolved.payload["item_id"]["value"], "compass")


if __name__ == "__main__":
    unittest.main()
