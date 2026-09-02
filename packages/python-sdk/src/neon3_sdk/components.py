"""Schema-driven collection/grid bindings (Stage 006).

Binds a keyed :class:`~neon3_sdk.store.CollectionStore` to an NUI template or
data grid so arbitrary collections stop hand-rolling node updates. The
backpack list is just one consumer; nothing domain-specific lives here.

Responsibilities:

- **Stable identity**: node/drag keys follow the fixed rule
  ``<binding node key>:<stable item key>``; array index is never identity.
- **Minimal publication**: the binding yields the ``cells_of`` adapter for
  ``ObservableStore.build_publication`` (Stage 004 structural reconciliation
  keeps grid changes minimal); selection and drag payloads always carry stable
  business keys, never visual coordinates.
- **Windowed paging**: with ``ui.data_grid.window.v1`` advertised, ``page()``
  resolves a renderer window request to a deterministic row slice; without it,
  ``fallback="list"`` keeps the binding usable as a plain keyed list (paging
  raises CapabilityError) or ``fallback="reject"`` refuses binding at creation.
- **Presentation states**: ``empty`` / ``loading`` / ``error`` derive from the
  source and optional caller-owned status stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .capabilities import CapabilitySet
from .errors import CapabilityError
from .store import CollectionStore

DATA_GRID_WINDOW_CAPABILITY = "ui.data_grid.window.v1"

# Node keys the runtime accepts match ``[A-Za-z0-9._-]`` (nui_flow invalid_key
# rule); the binding row separator must stay inside that set, so it is a dot.
KEY_SEPARATOR = "."

GridCell = dict[str, Any]  # {"value": typed|raw, "display": {"id": n, "generation": g}}
ColumnMapper = Callable[[Any], dict[str, GridCell]]


def _read_flag(store: Any) -> bool:
    """Best-effort truthiness for a status store (ScalarStore/SelectionStore/callable/bool)."""
    if store is None:
        return False
    if callable(store):
        store = store()
    if hasattr(store, "get"):
        value = store.get()
    else:
        value = store
    if isinstance(value, dict):
        value = value.get("value")
    return bool(value)


def default_drag_payload(item: Any, key: str, node_key: str) -> dict[str, Any]:
    """Default payload: stable key plus the item's own kind when present."""
    kind = item.get("kind") if isinstance(item, dict) else getattr(item, "kind", None)
    return {"item_key": key, "kind": str(kind) if kind is not None else node_key}


@dataclass(frozen=True)
class DragSpec:
    """Declarative drag intent for items sourced from this collection.

    ``payload_for`` maps a domain item to the SDK-level drag payload; it
    defaults to a stable-key + node-kind envelope so bindings work without a
    custom factory.
    """

    intent: str
    payload_for: Callable[[Any], dict[str, Any]] | None = None

    def payload(self, item: Any, key: str, node_key: str) -> dict[str, Any]:
        base = self.payload_for(item) if self.payload_for else default_drag_payload(item, key, node_key)
        return {**base, "source_node_key": f"{node_key}{KEY_SEPARATOR}{key}", "intent": self.intent}


@dataclass(frozen=True)
class DropSpec:
    """Declarative drop-target intent for drops landing on this collection."""

    intent: str
    accepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BindingPage:
    """A resolved window slice with the pairing metadata probes require."""

    first_row: int
    rows: list[dict[str, Any]]  # UiDataGridWindowRow entries
    list_revision: int
    total_rows: int


class CollectionBinding:
    """One keyed collection bound to a template/grid node."""

    def __init__(
        self,
        node_key: str,
        source: CollectionStore,
        *,
        columns: ColumnMapper,
        item_template: str | None = None,
        key_of: Callable[[Any], str] | None = None,
        selection: Any = None,
        drag: DragSpec | None = None,
        drop: DropSpec | None = None,
        windowed: bool = True,
        loading: Any = None,
        error: Any = None,
    ) -> None:
        if not node_key:
            raise ValueError("binding node_key must be non-empty")
        self.node_key = node_key
        self.source = source
        self.columns = columns
        self.item_template = item_template
        self.selection = selection
        self.drag = drag
        self.drop = drop
        self.windowed = windowed
        self.loading = loading
        self.error = error
        if key_of is not None:
            source.set_key_of(key_of)

    # -- identity -------------------------------------------------------------

    def item_key(self, item: Any) -> str:
        return self.source._key_of(item)

    def stable_node_key(self, item: Any) -> str:
        """Fixed rule: binding node key + stable business key, never array index."""
        return f"{self.node_key}{KEY_SEPARATOR}{self.item_key(item)}"

    def key_for_node(self, node_key: str) -> str | None:
        prefix = f"{self.node_key}{KEY_SEPARATOR}"
        return node_key[len(prefix):] if node_key.startswith(prefix) else None

    def selected_key(self) -> str | None:
        if self.selection is None:
            return None
        value = self.selection.get() if hasattr(self.selection, "get") else self.selection
        if isinstance(value, dict):
            value = value.get("value")
        return value

    # -- publication adapter ----------------------------------------------------

    def cells_of(self):
        """Adapter for ``ObservableStore.build_publication(cells_of=...)``.

        The store calls ``cells_of(collection, item)``; the binding's column
        mapper only needs the item, so this closes over it.
        """
        return lambda _collection, item: self.columns(item)

    def build_row(self, item: Any) -> dict[str, Any]:
        return {"stable_row_key": self.item_key(item), "cells": self.columns(item)}

    # -- presentation state -------------------------------------------------------

    def presentation_state(self) -> str:
        if _read_flag(self.error):
            return "error"
        if _read_flag(self.loading):
            return "loading"
        return "empty" if len(self.source) == 0 else "ready"

    # -- windowed paging ------------------------------------------------------------

    def page(self, first_row: int, max_rows: int) -> BindingPage:
        """Resolve a renderer window request deterministically.

        Paging requires ``ui.data_grid.window.v1``; in list fallback mode this
        raises CapabilityError so callers never silently receive truncated
        data. Given fixed inputs the slice is stable across calls.
        """
        if not self.windowed:
            raise CapabilityError((DATA_GRID_WINDOW_CAPABILITY,), service="ui-runtime")
        if first_row < 0 or max_rows <= 0:
            raise ValueError("first_row must be >= 0 and max_rows > 0")
        items = self.source.items[first_row : first_row + max_rows]
        return BindingPage(
            first_row=first_row,
            rows=[self.build_row(item) for item in items],
            list_revision=self.source.list_revision,
            total_rows=len(self.source),
        )

    # -- router registration helpers -------------------------------------------------

    def drag_source_spec(self, router_source_key: str | None = None) -> tuple[str, Callable[[Any], dict[str, Any]], Callable[[Any], str]]:
        """Return (router key, payload factory, kind factory) for registration.

        The router keys a drag source by the item's stable node key so each
        list row is independently draggable.
        """
        def payload(item: Any) -> dict[str, Any]:
            if self.drag is None:
                return {**default_drag_payload(item, self.item_key(item), self.node_key), "source_node_key": self.stable_node_key(item)}
            return self.drag.payload(item, self.item_key(item), self.node_key)

        def kind_of(item: Any) -> str:
            return payload(item).get("kind", self.node_key)

        return (router_source_key or self.node_key, payload, kind_of)

    def drop_target_spec(self) -> tuple[str, str, tuple[str, ...]] | None:
        if self.drop is None:
            return None
        return (self.node_key, self.drop.intent, self.drop.accepts)


class CollectionBinder:
    """Factory that gates bindings on the runtime's grid capability.

    ``fallback="list"`` (default) keeps a binding usable as a plain keyed
    list when ``ui.data_grid.window.v1`` is absent — only paging is disabled.
    ``fallback="reject"`` refuses to bind at creation time instead.
    """

    def __init__(self, capabilities: CapabilitySet, *, fallback: str = "list") -> None:
        if fallback not in {"list", "reject"}:
            raise ValueError('fallback must be "list" or "reject"')
        self.capabilities = capabilities
        self.fallback = fallback

    @property
    def windowed(self) -> bool:
        return self.capabilities.has(DATA_GRID_WINDOW_CAPABILITY)

    def bind(self, node_key: str, source: CollectionStore, **kwargs: Any) -> CollectionBinding:
        windowed = self.windowed
        if not windowed and self.fallback == "reject":
            raise CapabilityError((DATA_GRID_WINDOW_CAPABILITY,), service="ui-runtime")
        kwargs.pop("windowed", None)
        return CollectionBinding(node_key, source, windowed=windowed, **kwargs)
