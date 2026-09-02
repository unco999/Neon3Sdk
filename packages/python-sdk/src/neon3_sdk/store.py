"""Typed observable store and UI publication building (Stage 004).

Generic domain-state layer only: keyed collections, scalar values and
selections with diff tracking, transactions, and canonical
``UiHostPublication`` construction. No inventory/calculator/editor domain
models live here — those belong to examples. Business code mutates the store
inside a transaction, builds one publication per operation, and on runtime
acceptance calls ``mark_applied`` to clear pending diffs (a rejection leaves
local confirm state untouched so the caller can retry or roll forward).

Wire shapes follow docs/sdk-wire-contract.md §4.4; ``to_wire`` output must
stay byte-identical with the Node implementation (verified by shared
canonical fixtures).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .errors import InvalidPublicationError

# Wire vocabulary for scalar input values (UiInputValue kinds).
_VALUE_KINDS = frozenset({"bool", "i32", "u32", "f32", "vec2", "vec4", "color", "enum", "text_handle", "asset_handle"})


def typed_value(value: Any) -> dict[str, Any]:
    """Coerce a Python value into a canonical ``UiInputValue`` envelope.

    bool -> bool, int -> i32/u32, float -> f32, str -> enum, length-2/4
    numeric sequences -> vec2/vec4. Dicts already carrying a valid ``kind``
    pass through. Anything outside the finite wire vocabulary raises
    :class:`InvalidPublicationError`.
    """
    if isinstance(value, dict) and value.get("kind") in _VALUE_KINDS:
        return {"kind": value["kind"], **{key: item for key, item in value.items() if key != "kind"}}
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int):
        if -(2**31) <= value < 2**31:
            return {"kind": "i32", "value": value}
        if 0 <= value < 2**32:
            return {"kind": "u32", "value": value}
        raise InvalidPublicationError(f"integer out of wire range: {value}")
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidPublicationError("non-finite floats are not representable in f32 inputs")
        return {"kind": "f32", "value": value}
    if isinstance(value, str):
        if not value.strip():
            raise InvalidPublicationError("enum values must be non-empty strings")
        return {"kind": "enum", "value": value}
    if isinstance(value, (tuple, list)) and len(value) in (2, 4):
        if all(isinstance(component, (int, float)) and not isinstance(component, bool) for component in value):
            kind = "vec2" if len(value) == 2 else "vec4"
            return {"kind": kind, "value": [float(component) for component in value]}
    raise InvalidPublicationError(f"value type is outside the wire vocabulary: {type(value).__name__}")


def _cell_value(value: Any) -> dict[str, Any]:
    return typed_value(value)


@dataclass
class ScalarStore:
    """A typed observable value inside an :class:`ObservableStore`."""

    key: str
    _value: Any = None
    _dirty: bool = False
    _owner: "ObservableStore | None" = field(default=None, repr=False)

    @property
    def value(self) -> Any:
        return self._value

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        coerced = typed_value(value)
        if coerced == self._value:
            return
        self._value = coerced
        self._dirty = True
        if self._owner is not None:
            self._owner._touch_scalar(self.key)

    def to_wire(self) -> Any:
        return self._value

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_applied(self) -> None:
        self._dirty = False


@dataclass
class CollectionStore:
    """A keyed list of items with per-key diff tracking.

    Stable identity is ``key_of(item)``; array index is never identity.
    Structural ops (add/remove/move/replace) mark the collection structure
    dirty so the grid window is re-published; scalar-only updates mark just
    the touched key.
    """

    name: str
    _items: list[Any] = field(default_factory=list)
    _key_of: Callable[[Any], str] = field(default=lambda item: str(item["key"]) if isinstance(item, dict) else str(item))
    _dirty_keys: set[str] = field(default_factory=set)
    _structure_dirty: bool = False
    list_revision: int = 0
    window_rows: int | None = None
    _owner: "ObservableStore | None" = field(default=None, repr=False)

    # -- reading -------------------------------------------------------------

    @property
    def items(self) -> list[Any]:
        return list(self._items)

    def keys(self) -> list[str]:
        return [self._key_of(item) for item in self._items]

    def index_of(self, key: str) -> int:
        for index, item in enumerate(self._items):
            if self._key_of(item) == key:
                return index
        raise KeyError(key)

    def get(self, key: str) -> Any:
        return self._items[self.index_of(key)]

    def __len__(self) -> int:
        return len(self._items)

    # -- mutation ------------------------------------------------------------

    def _bump(self, structure: bool, *keys: str) -> None:
        self.list_revision += 1
        if structure:
            self._structure_dirty = True
        self._dirty_keys.update(keys)
        if self._owner is not None:
            self._owner._touch_collection(self.name)

    def set_key_of(self, key_of: Callable[[Any], str]) -> None:
        self._key_of = key_of

    def add(self, key: str, item: Any | None = None, *, index: int | None = None) -> None:
        if any(self._key_of(existing) == key for existing in self._items):
            raise KeyError(f"duplicate collection key: {key}")
        payload = item if item is not None else {"key": key}
        if self._key_of(payload) != key:
            raise ValueError("item key must match the add() key")
        if index is None:
            self._items.append(payload)
        else:
            self._items.insert(index, payload)
        self._bump(True, key)

    def remove(self, key: str) -> Any:
        index = self.index_of(key)
        item = self._items.pop(index)
        self._bump(True, key)
        return item

    def update(self, key: str, item: Any) -> None:
        index = self.index_of(key)
        if self._key_of(item) != key:
            raise ValueError("update must preserve the stable key")
        self._items[index] = item
        self._bump(False, key)

    def move(self, key: str, target_index: int) -> None:
        if not 0 <= target_index < len(self._items):
            raise IndexError(f"target_index {target_index} out of range")
        index = self.index_of(key)
        if index == target_index:
            return
        item = self._items.pop(index)
        self._items.insert(target_index, item)
        self._bump(True, key)

    def replace(self, items: list[Any]) -> None:
        previous_by_key = {self._key_of(item): item for item in self._items}
        next_by_key = {self._key_of(item): item for item in items}
        if len(next_by_key) != len(items):
            raise ValueError("replacement list contains duplicate keys")
        order_changed = list(previous_by_key) != list(next_by_key)
        membership_changed = set(previous_by_key) != set(next_by_key)
        changed = set(previous_by_key) ^ set(next_by_key)
        for key in set(previous_by_key) & set(next_by_key):
            if previous_by_key[key] != next_by_key[key]:
                changed.add(key)
        self._items = list(items)
        self.list_revision += 1
        self._dirty_keys.update(changed)
        if order_changed or membership_changed:
            self._structure_dirty = True
        if self._owner is not None:
            self._owner._touch_collection(self.name)

    # -- diff / commit ---------------------------------------------------------

    def dirty_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._dirty_keys))

    def has_pending_changes(self) -> bool:
        return bool(self._dirty_keys) or self._structure_dirty

    def mark_applied(self) -> None:
        self._dirty_keys.clear()
        self._structure_dirty = False

    def window(self, rows: int | None = None) -> list[Any]:
        cap = rows if rows is not None else self.window_rows
        return self.items[:cap] if cap is not None else self.items

    def to_wire(self) -> dict[str, Any]:
        return {"name": self.name, "list_revision": self.list_revision, "items": list(self._items)}


@dataclass
class SelectionStore:
    """The currently selected stable key (or None) for one collection lane."""

    name: str
    _key: str | None = None
    _dirty: bool = False
    selection_revision: int = 0
    _owner: "ObservableStore | None" = field(default=None, repr=False)

    @property
    def value(self) -> str | None:
        return self._key

    def get(self) -> str | None:
        return self._key

    def set(self, key: str | None) -> None:
        if key == self._key:
            return
        self._key = key
        self._dirty = True
        self.selection_revision += 1
        if self._owner is not None:
            self._owner._touch_selection(self.name)

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_applied(self) -> None:
        self._dirty = False


class ObservableStore:
    """Generic observable domain state: typed scalars, keyed collections and
    selections, one monotonic domain revision, transactions, and publication
    building. Domain items are opaque caller-chosen values (dicts, objects
    with a ``key`` attribute, or plain strings).
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._scalars: dict[str, ScalarStore] = {}
        self._collections: dict[str, CollectionStore] = {}
        self._selections: dict[str, SelectionStore] = {}
        self._dirty_scalars: set[str] = set()
        self._dirty_collections: set[str] = set()
        self._dirty_selections: set[str] = set()
        self._transaction_depth = 0
        self.domain_revision = 0
        for key, value in (initial or {}).items():
            if isinstance(value, list):
                collection = self.collection(key)
                collection.replace(value)
                collection.mark_applied()
            else:
                scalar = self.value(key)
                if value is not None:
                    scalar.set(value)
                scalar.mark_applied()

    # -- accessors --------------------------------------------------------------

    def value(self, key: str) -> ScalarStore:
        if key not in self._scalars:
            self._scalars[key] = ScalarStore(key=key, _owner=self)
        return self._scalars[key]

    def collection(self, name: str) -> CollectionStore:
        if name not in self._collections:
            self._collections[name] = CollectionStore(name=name, _owner=self)
        return self._collections[name]

    def selection(self, name: str) -> SelectionStore:
        if name not in self._selections:
            self._selections[name] = SelectionStore(name=name, _owner=self)
        return self._selections[name]

    # -- dirty bookkeeping ---------------------------------------------------------

    def _touch_scalar(self, key: str) -> None:
        self._dirty_scalars.add(key)

    def _touch_collection(self, name: str) -> None:
        self._dirty_collections.add(name)

    def _touch_selection(self, name: str) -> None:
        self._dirty_selections.add(name)

    # -- transactions -----------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator["ObservableStore"]:
        """Group mutations so one business operation yields one publication.

        If the block raises, scalar/selection values and collection contents
        and diff sets revert to their pre-transaction state, so no half
        publication can be built from a failed operation.
        """
        scalars = {name: (store._value, store._dirty) for name, store in self._scalars.items()}
        selections = {name: (store._key, store._dirty, store.selection_revision) for name, store in self._selections.items()}
        collections = {
            name: (list(store._items), store.list_revision, set(store._dirty_keys), store._structure_dirty)
            for name, store in self._collections.items()
        }
        dirty = (set(self._dirty_scalars), set(self._dirty_collections), set(self._dirty_selections))
        self._transaction_depth += 1
        try:
            yield self
        except Exception:
            for name, (value, is_dirty) in scalars.items():
                store = self._scalars[name]
                store._value, store._dirty = value, is_dirty
            for name in list(self._scalars):
                if name not in scalars:
                    del self._scalars[name]
            for name, (key, is_dirty, revision) in selections.items():
                store = self._selections[name]
                store._key, store._dirty, store.selection_revision = key, is_dirty, revision
            for name in list(self._selections):
                if name not in selections:
                    del self._selections[name]
            for name, (items, revision, keys, structure) in collections.items():
                store = self._collections[name]
                store._items, store.list_revision = items, revision
                store._dirty_keys, store._structure_dirty = keys, structure
            for name in list(self._collections):
                if name not in collections:
                    del self._collections[name]
            self._dirty_scalars, self._dirty_collections, self._dirty_selections = dirty
            raise
        finally:
            self._transaction_depth -= 1

    # -- diff / publication -----------------------------------------------------------------

    def changed_scalars(self) -> list[dict[str, Any]]:
        return [
            {"key": name, "value": self._scalars[name]._value}
            for name in sorted(self._dirty_scalars)
            if self._scalars[name].is_dirty() and self._scalars[name]._value is not None
        ]

    def changed_collections(self) -> list[CollectionStore]:
        return [self._collections[name] for name in sorted(self._dirty_collections) if self._collections[name].has_pending_changes()]

    def changed_selections(self) -> list[str]:
        return [name for name in sorted(self._dirty_selections) if self._selections[name].is_dirty()]

    def has_pending_changes(self) -> bool:
        return any(store.is_dirty() for store in self._scalars.values()) or any(store.is_dirty() for store in self._selections.values()) or any(store.has_pending_changes() for store in self._collections.values())

    def build_publication(
        self,
        program_revision: dict[str, Any],
        expected_input_revision: int,
        request_id: str,
        *,
        cells_of: Callable[[CollectionStore, Any], dict[str, Any]] | None = None,
        window_rows: int | None = None,
        selection_slots: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Produce one canonical ``UiHostPublication`` covering all pending diffs.

        - ``cells_of(collection, item) -> {column: {"value": <typed|raw>,
          "display": {"id": n, "generation": g}}}`` maps domain items to grid
          cells; collections without a cell mapper are skipped (scalar lane
          only).
        - Grid reconciliation is structural-aware: a scalar-only update
          publishes exactly the dirty rows (so one update in a 1000-item
          collection emits one row), while any add/remove/move/replace that
          changes order or membership publishes the bounded current window so
          the renderer can re-map by ``stable_row_key``. ``first_row`` stays 0
          until Stage 006 implements paging against ``ui.data_grid.window.v1``.
        - ``selection_slots`` maps selection store name -> scalar input key;
          the selected key publishes as an enum value there (clear/None skips
          the slot; wire has no null enum).
        - ``window_rows`` overrides the per-collection window cap so probes
          stay bounded.

        The returned dict must not gain extra keys: the runtime parses
        ``UiHostPublication`` with ``deny_unknown_fields``.
        """
        changes = self.changed_scalars()
        for name in self.changed_selections():
            slot = (selection_slots or {}).get(name)
            selected = self._selections[name].get()
            if slot is not None and selected is not None:
                changes.append({"key": slot, "value": {"kind": "enum", "value": selected}})
        changes.sort(key=lambda change: change["key"])
        grid_inputs: list[dict[str, Any]] = []
        if cells_of is not None:
            for collection in self.changed_collections():
                if collection._structure_dirty:
                    source_rows = collection.window(window_rows)
                else:
                    dirty = collection._dirty_keys
                    capped = [entry for entry in collection.items if collection._key_of(entry) in dirty]
                    source_rows = capped[:window_rows] if window_rows is not None else capped
                window_entries: list[dict[str, Any]] = []
                for item in source_rows:
                    cells: dict[str, Any] = {}
                    for column, cell in sorted(cells_of(collection, item).items()):
                        entry: dict[str, Any] = {"value": _cell_value(cell["value"]), "display": cell["display"]}
                        if cell.get("presentation_override") is not None:
                            entry["presentation_override"] = cell["presentation_override"]
                        cells[column] = entry
                    window_entries.append({"stable_row_key": collection._key_of(item), "cells": cells})
                grid_inputs.append({
                    "source_key": collection.name,
                    "frame": {
                        "list_revision": collection.list_revision,
                        "total_rows": len(collection),
                        "first_row": 0,
                        "window_rows": window_entries,
                        "expected_program_revision": program_revision,
                    },
                })
        return {
            "scalar_frame": {
                "program_revision": program_revision,
                "expected_input_revision": expected_input_revision,
                "request_id": request_id,
                "idempotency_key": f"publication:{request_id}",
                "changes": changes,
            },
            "grid_inputs": grid_inputs,
            "presentation_update": None,
        }

    def mark_applied(self) -> None:
        """Confirm pending diffs after runtime acceptance (domain step +1)."""
        for name in self._dirty_scalars:
            self._scalars[name].mark_applied()
        for name in self._dirty_collections:
            self._collections[name].mark_applied()
        for name in self._dirty_selections:
            self._selections[name].mark_applied()
        self._dirty_scalars.clear()
        self._dirty_collections.clear()
        self._dirty_selections.clear()
        self.domain_revision += 1

    def reject_pending(self) -> None:
        """Rejection path: leave local confirm state untouched.

        Explicit no-op kept for API symmetry with the acceptance flow:
        pending diffs stay dirty so the caller can rebuild a publication with
        a fresh request id after refresh().
        """

    # -- wire helpers --------------------------------------------------------------------

    def to_wire(self) -> dict[str, Any]:
        return {
            "domain_revision": self.domain_revision,
            "scalars": {name: store.to_wire() for name, store in sorted(self._scalars.items())},
            "collections": {name: store.to_wire() for name, store in sorted(self._collections.items())},
            "selections": {name: store.get() for name, store in sorted(self._selections.items())},
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ObservableStore":
        store = cls()
        store.domain_revision = value["domain_revision"]
        for name, raw in value.get("scalars", {}).items():
            scalar = store.value(name)
            scalar._value = raw
        for name, raw in value.get("collections", {}).items():
            collection = store.collection(name)
            collection.list_revision = raw["list_revision"]
            collection._items = list(raw["items"])
        for name, key in value.get("selections", {}).items():
            store.selection(name)._key = key
        return store

    def snapshot_wire(self) -> str:
        from .wire import canonical_json

        return canonical_json(self.to_wire())
