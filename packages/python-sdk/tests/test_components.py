"""Stage 006 collection/grid binding tests.

Acceptance gates: mutations publish only necessary grid changes through the
binding's cells_of adapter; selection and drag payload always carry the stable
business key rather than visual coordinates; long lists page deterministically
under fixed inputs; and the missing-capability path falls back cleanly (list
mode keeps the binding usable while paging raises, reject mode fails early).
"""

from __future__ import annotations

import unittest

from neon3_sdk.capabilities import CapabilitySet
from neon3_sdk.components import CollectionBinding, CollectionBinder, DragSpec, DropSpec
from neon3_sdk.errors import CapabilityError
from neon3_sdk.store import ObservableStore

PROGRAM_REVISION = {"program_id": "demo", "revision": 1, "schema_version": 1, "capabilities": []}


def grid_capabilities(*extra: str) -> CapabilitySet:
    return CapabilitySet(services=("ui-runtime",), capabilities=frozenset({"ui.data_grid.window.v1", *extra}))


def empty_capabilities() -> CapabilitySet:
    return CapabilitySet(services=("ui-runtime",), capabilities=frozenset({"ui.program.v1"}))


def item(key: str, name: str) -> dict:
    return {"key": key, "name": name}


def columns(entry: dict) -> dict:
    return {"name": {"value": {"kind": "enum", "value": entry["name"]}, "display": {"id": 1, "generation": 1}}}


def _store_with(items: list[dict]) -> ObservableStore:
    store = ObservableStore()
    collection = store.collection("items")
    collection.set_key_of(lambda entry: entry["key"])
    collection.replace(items)
    store.mark_applied()
    return store


class StableIdentityTests(unittest.TestCase):
    def test_node_keys_use_stable_business_keys_not_index(self) -> None:
        store = _store_with([item("a", "Alpha"), item("b", "Beta")])
        binding = CollectionBinder(grid_capabilities()).bind("backpack", store.collection("items"), columns=columns)
        self.assertEqual(binding.stable_node_key(item("b", "Beta")), "backpack:b")
        self.assertEqual(binding.key_for_node("backpack:b"), "b")
        self.assertIsNone(binding.key_for_node("elsewhere:b"))
        # identity survives reorder: the same item key maps to the same node key
        store.collection("items").move("a", 1)
        self.assertEqual(binding.stable_node_key(item("b", "Beta")), "backpack:b")

    def test_drag_and_selection_payloads_carry_stable_keys(self) -> None:
        store = _store_with([item("gem-1", "Gem")])
        selection = store.selection("items")
        binding = CollectionBinder(grid_capabilities()).bind(
            "backpack",
            store.collection("items"),
            columns=columns,
            selection=selection,
            drag=DragSpec(intent="domain.item.move", payload_for=lambda entry: {"item_id": entry["key"], "kind": "gem"}),
        )
        selection.set("gem-1")
        self.assertEqual(binding.selected_key(), "gem-1")
        _key, payload_for, kind_for = binding.drag_source_spec()
        entry = store.collection("items").get("gem-1")
        payload = payload_for(entry)
        self.assertEqual(payload["item_id"], "gem-1")
        self.assertEqual(payload["source_node_key"], "backpack:gem-1")  # stable key, not coordinates
        self.assertEqual(kind_for(entry), "gem")

    def test_drag_default_payload_and_kind(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binding = CollectionBinder(grid_capabilities()).bind("grid", store.collection("items"), columns=columns, drag=DragSpec(intent="domain.item.move"))
        _key, payload_for, kind_for = binding.drag_source_spec()
        entry = store.collection("items").get("a")
        self.assertEqual(payload_for(entry), {"item_key": "a", "kind": "grid", "source_node_key": "grid:a", "intent": "domain.item.move"})
        self.assertEqual(kind_for(entry), "grid")


class MinimalGridChangesTests(unittest.TestCase):
    def test_single_update_publishes_only_that_row(self) -> None:
        store = _store_with([item(f"k{index}", f"N{index}") for index in range(500)])
        binding = CollectionBinder(grid_capabilities()).bind("backpack", store.collection("items"), columns=columns)
        store.collection("items").update("k42", item("k42", "Changed"))
        publication = store.build_publication(PROGRAM_REVISION, 0, "pub", cells_of=binding.cells_of())
        rows = publication["grid_inputs"][0]["frame"]["window_rows"]
        self.assertEqual([row["stable_row_key"] for row in rows], ["k42"])

    def test_cells_of_produces_typed_display_cells(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binding = CollectionBinder(grid_capabilities()).bind("backpack", store.collection("items"), columns=columns)
        store.collection("items").update("a", item("a", "Changed"))
        publication = store.build_publication(PROGRAM_REVISION, 0, "pub", cells_of=binding.cells_of())
        row = publication["grid_inputs"][0]["frame"]["window_rows"][0]
        self.assertEqual(row["cells"]["name"]["value"], {"kind": "enum", "value": "Changed"})
        self.assertEqual(row["cells"]["name"]["display"], {"id": 1, "generation": 1})


class WindowingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _store_with([item(f"k{index}", f"N{index}") for index in range(100)])
        self.binding = CollectionBinder(grid_capabilities()).bind("list", self.store.collection("items"), columns=columns)

    def test_window_slice_is_deterministic(self) -> None:
        first = self.binding.page(10, 25)
        again = self.binding.page(10, 25)
        self.assertEqual([row["stable_row_key"] for row in first.rows], [f"k{index}" for index in range(10, 35)])
        self.assertEqual(first.first_row, 10)
        self.assertEqual(first.total_rows, 100)
        self.assertEqual(again.rows, first.rows)
        self.assertEqual(again.list_revision, first.list_revision)

    def test_page_beyond_end_is_bounded_not_wrapping(self) -> None:
        tail = self.binding.page(90, 50)
        self.assertEqual([row["stable_row_key"] for row in tail.rows], [f"k{index}" for index in range(90, 100)])

    def test_invalid_page_arguments_raise(self) -> None:
        with self.assertRaises(ValueError):
            self.binding.page(-1, 10)
        with self.assertRaises(ValueError):
            self.binding.page(0, 0)


class FallbackTests(unittest.TestCase):
    def test_list_fallback_keeps_binding_usable_and_gates_paging(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binder = CollectionBinder(empty_capabilities(), fallback="list")
        binding = binder.bind("list", store.collection("items"), columns=columns)
        self.assertFalse(binding.windowed)
        with self.assertRaises(CapabilityError):
            binding.page(0, 10)

    def test_reject_fallback_fails_before_use(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binder = CollectionBinder(empty_capabilities(), fallback="reject")
        with self.assertRaises(CapabilityError) as caught:
            binder.bind("list", store.collection("items"), columns=columns)
        self.assertEqual(caught.exception.missing, ("ui.data_grid.window.v1",))

    def test_unknown_fallback_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CollectionBinder(grid_capabilities(), fallback="magic")


class PresentationStateTests(unittest.TestCase):
    def test_state_derivation(self) -> None:
        store = ObservableStore()
        collection = store.collection("items")
        collection.set_key_of(lambda entry: entry["key"])
        loading = store.value("loading")
        error = store.value("error")
        binding = CollectionBinding("list", collection, columns=columns, loading=loading, error=error)
        self.assertEqual(binding.presentation_state(), "empty")
        collection.replace([item("a", "A")])
        self.assertEqual(binding.presentation_state(), "ready")
        loading.set(True)
        self.assertEqual(binding.presentation_state(), "loading")
        error.set(True)
        self.assertEqual(binding.presentation_state(), "error")  # error wins over loading


class DropSpecTests(unittest.TestCase):
    def test_drop_spec_registration_shape(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binding = CollectionBinder(grid_capabilities()).bind(
            "grid",
            store.collection("items"),
            columns=columns,
            drop=DropSpec(intent="domain.item.place", accepts=("gem",)),
        )
        self.assertEqual(binding.drop_target_spec(), ("grid", "domain.item.place", ("gem",)))

    def test_binding_without_drop_returns_none(self) -> None:
        store = _store_with([item("a", "Alpha")])
        binding = CollectionBinder(grid_capabilities()).bind("grid", store.collection("items"), columns=columns)
        self.assertIsNone(binding.drop_target_spec())

    def test_empty_node_key_rejected(self) -> None:
        store = _store_with([])
        with self.assertRaises(ValueError):
            CollectionBinder(grid_capabilities()).bind("", store.collection("items"), columns=columns)


if __name__ == "__main__":
    unittest.main()
