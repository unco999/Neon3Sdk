"""Stage 004 typed store and publication tests.

Covers the plan's acceptance gates: every mutation kind produces a correct
typed publication, a 1000-item collection publishing one updated item emits a
single-row window (never 1000 diffs), transaction aborts leave no half
publication, and to_wire/from_wire canonical bytes are pinned for the
cross-language check the Node suite repeats against the same digest.
"""

from __future__ import annotations

import hashlib
import unittest

from neon3_sdk.errors import InvalidPublicationError
from neon3_sdk.store import CollectionStore, ObservableStore, SelectionStore, ScalarStore, typed_value
from neon3_sdk.wire import canonical_json

PROGRAM_REVISION = {"program_id": "demo", "revision": 1, "schema_version": 1, "capabilities": []}


def item(key: str, n: int, label: str = "") -> dict:
    return {"key": key, "n": n, "label": label or f"item-{key}"}


def cells(collection: CollectionStore, entry: dict) -> dict:
    return {"label": {"value": {"kind": "enum", "value": entry["label"]}, "display": {"id": 1, "generation": 1}}}


class TypedValueTests(unittest.TestCase):
    def test_python_types_map_to_wire_kinds(self) -> None:
        self.assertEqual(typed_value(True), {"kind": "bool", "value": True})
        self.assertEqual(typed_value(7), {"kind": "i32", "value": 7})
        self.assertEqual(typed_value(2.5), {"kind": "f32", "value": 2.5})
        self.assertEqual(typed_value("ready"), {"kind": "enum", "value": "ready"})
        self.assertEqual(typed_value((1, 2)), {"kind": "vec2", "value": [1.0, 2.0]})
        self.assertEqual(typed_value({"kind": "u32", "value": 4}), {"kind": "u32", "value": 4})

    def test_rejects_outside_vocabulary(self) -> None:
        with self.assertRaises(InvalidPublicationError):
            typed_value(object())
        with self.assertRaises(InvalidPublicationError):
            typed_value(float("nan"))
        with self.assertRaises(InvalidPublicationError):
            typed_value("")


class ScalarAndSelectionTests(unittest.TestCase):
    def test_scalar_set_marks_dirty_once(self) -> None:
        store = ObservableStore()
        scalar = store.value("count")
        scalar.set(1)
        self.assertTrue(scalar.is_dirty())
        self.assertEqual(store.changed_scalars(), [{"key": "count", "value": {"kind": "i32", "value": 1}}])
        scalar.set(1)
        self.assertTrue(scalar.is_dirty())  # idempotent set keeps existing diff
        store.mark_applied()
        self.assertEqual(store.changed_scalars(), [])
        self.assertEqual(store.domain_revision, 1)

    def test_selection_lane(self) -> None:
        store = ObservableStore()
        store.collection("items").replace([item("a", 1), item("b", 2)])
        store.collection("items").set_key_of(lambda entry: entry["key"])
        selection = store.selection("items")
        selection.set("a")
        publication = store.build_publication(PROGRAM_REVISION, 3, "r-sel", selection_slots={"items": "selected_key"})
        self.assertEqual(publication["scalar_frame"]["changes"], [{"key": "selected_key", "value": {"kind": "enum", "value": "a"}}])
        self.assertEqual(publication["scalar_frame"]["expected_input_revision"], 3)
        store.mark_applied()
        selection.set("b")
        self.assertEqual(selection.selection_revision, 2)


class CollectionDiffTests(unittest.TestCase):
    def fresh(self) -> tuple[ObservableStore, CollectionStore]:
        store = ObservableStore()
        collection = store.collection("items")
        collection.set_key_of(lambda entry: entry["key"])
        collection.replace([item("a", 1), item("b", 2), item("c", 3)])
        store.mark_applied()
        return store, collection

    def published_rows(self, store: ObservableStore, collection: CollectionStore, **kwargs) -> list[str]:
        publication = store.build_publication(PROGRAM_REVISION, 0, "req", cells_of=cells, **kwargs)
        if not publication["grid_inputs"]:
            return []
        return [row["stable_row_key"] for row in publication["grid_inputs"][0]["frame"]["window_rows"]]

    def test_scalar_update_emits_only_that_row(self) -> None:
        store, collection = self.fresh()
        collection.update("c", item("c", 99))
        self.assertEqual(self.published_rows(store, collection), ["c"])

    def test_add_move_remove_republish_bounded_window(self) -> None:
        store, collection = self.fresh()
        collection.add("d", item("d", 4))
        self.assertEqual(self.published_rows(store, collection), ["a", "b", "c", "d"])
        collection.mark_applied()
        collection.move("a", 2)
        self.assertEqual(self.published_rows(store, collection), ["b", "c", "a", "d"])
        collection.mark_applied()
        collection.remove("b")
        self.assertEqual(self.published_rows(store, collection), ["c", "a", "d"])

    def test_one_update_of_thousand_items_emits_single_row(self) -> None:
        big = ObservableStore()
        collection = big.collection("items")
        collection.set_key_of(lambda entry: entry["key"])
        collection.replace([item(f"k{index}", index) for index in range(1000)])
        big.mark_applied()
        collection.update("k42", item("k42", 500))
        publication = big.build_publication(PROGRAM_REVISION, 0, "big", cells_of=cells)
        rows = publication["grid_inputs"][0]["frame"]["window_rows"]
        self.assertEqual([row["stable_row_key"] for row in rows], ["k42"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(publication["grid_inputs"][0]["frame"]["total_rows"], 1000)
        self.assertEqual(publication["scalar_frame"]["changes"], [])

    def test_structural_change_respects_window_cap(self) -> None:
        store, collection = self.fresh()
        collection.add("d", item("d", 4))
        self.assertEqual(self.published_rows(store, collection, window_rows=2), ["a", "b"])

    def test_replace_structure_diff(self) -> None:
        store, collection = self.fresh()
        collection.replace([item("c", 3), item("b", 2)])  # reorder + drop "a"
        self.assertIn("a", set(collection.dirty_keys()))
        self.assertEqual(self.published_rows(store, collection), ["c", "b"])

    def test_no_pending_no_grid_entries(self) -> None:
        store, collection = self.fresh()
        publication = store.build_publication(PROGRAM_REVISION, 0, "noop", cells_of=cells)
        self.assertEqual(publication["grid_inputs"], [])


class TransactionTests(unittest.TestCase):
    def test_mixed_changes_collapse_into_one_publication(self) -> None:
        store = ObservableStore()
        collection = store.collection("items")
        collection.set_key_of(lambda entry: entry["key"])
        collection.replace([item("a", 1)])
        store.mark_applied()
        with store.transaction():
            collection.add("b", item("b", 2))
            store.value("count").set(2)
            store.selection("items").set("b")
        publication = store.build_publication(PROGRAM_REVISION, 0, "txn", cells_of=cells, selection_slots={"items": "selected"})
        self.assertEqual([change["key"] for change in publication["scalar_frame"]["changes"]], ["count", "selected"])
        self.assertEqual([row["stable_row_key"] for row in publication["grid_inputs"][0]["frame"]["window_rows"]], ["a", "b"])

    def test_abort_leaves_no_half_publication(self) -> None:
        store = ObservableStore()
        store.value("count").set(1)
        collection = store.collection("items")
        collection.set_key_of(lambda entry: entry["key"])
        collection.replace([item("a", 1)])
        store.mark_applied()
        with self.assertRaises(RuntimeError):
            with store.transaction():
                store.value("count").set(99)
                collection.remove("a")
                selection = store.selection("items")
                selection.set("ghost")
                raise RuntimeError("domain rule rejected")
        # every local channel reverted; nothing publishable leaked
        self.assertEqual(store.value("count").value, {"kind": "i32", "value": 1})
        self.assertFalse(store.value("count").is_dirty())
        self.assertEqual(collection.keys(), ["a"])
        self.assertFalse(collection.has_pending_changes())
        self.assertTrue("items" not in store._selections or not store._selections["items"].is_dirty())
        self.assertFalse(store.has_pending_changes())
        publication = store.build_publication(PROGRAM_REVISION, 0, "post-abort", cells_of=cells)
        self.assertEqual(publication["scalar_frame"]["changes"], [])
        self.assertEqual(publication["grid_inputs"], [])

    def test_rejection_keeps_local_pending_state(self) -> None:
        store = ObservableStore()
        store.value("count").set(1)
        before = store.domain_revision
        store.reject_pending()  # a rejected publication must not confirm
        self.assertTrue(store.value("count").is_dirty())
        self.assertEqual(store.domain_revision, before)
        store.mark_applied()
        self.assertFalse(store.value("count").is_dirty())


class WireRoundTripTests(unittest.TestCase):
    def test_store_wire_is_canonical_and_pin_digest(self) -> None:
        store = ObservableStore({"status": "ready", "count": 3})
        store.collection("items").set_key_of(lambda entry: entry["key"])
        store.collection("items").replace([item("a", 1), item("b", 2)])
        store.selection("items").set("a")
        wire = store.to_wire()
        restored = ObservableStore.from_wire(wire)
        self.assertEqual(restored.domain_revision, wire["domain_revision"])
        self.assertEqual(restored.collection("items").keys(), ["a", "b"])
        self.assertEqual(restored.value("status").value, {"kind": "enum", "value": "ready"})
        self.assertEqual(restored.selection("items").get(), "a")
        digest = hashlib.sha256(canonical_json(wire).encode("utf-8")).hexdigest()
        # Pinned cross-language digest: the Node suite asserts the same value.
        self.assertEqual(digest, "3f790bd056eb8e06d80e9d50709cea97520277f456df46ed1d9866671a240f6e")


if __name__ == "__main__":
    unittest.main()
