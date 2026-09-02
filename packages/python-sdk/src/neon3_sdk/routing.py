"""Intent routing and drag/drop abstractions (Stage 005).

``IntentRouter`` turns any business semantic/drop event into a typed handler
call and a resulting publication. It matches an exact intent first, then a
registered prefix (``domain.item.*``), then an optional default handler; an
unmatched intent raises a structured :class:`UnsupportedIntentError` instead
of being silently dropped. Handlers may be sync or async and may return
``None`` (no state change), a ``UiHostPublication`` dict, or a store
transaction result.

Drag/drop is declarative and generic: a :class:`DragSource` binds a stable
node key to a payload factory and :class:`DropTarget` records which payload
*kinds* it accepts and which intent a completed drop dispatches. The router
resolves a raw ``UiProgramDragDropEvent`` into a :class:`DropEvent` carrying
the SDK-level business payload, then routes on the target's intent. Nothing
here knows about inventory, equipment or recipes — those live in examples.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from .errors import DropRejectedError, UnknownTargetError, UnsupportedIntentError
from .models import DropEvent, IntentEvent

HandlerResult = Any
IntentHandler = Callable[[Any], HandlerResult | Awaitable[HandlerResult]]


@dataclass(frozen=True)
class DragSource:
    """A stable node key plus the business payload a completed drag yields."""

    key: str
    payload_for: Callable[[Any], dict[str, Any]] = field(default=lambda item: {"key": item} if not isinstance(item, dict) else dict(item))
    kind_of: Callable[[Any], str] = field(default=lambda item: str(item.get("kind") if isinstance(item, dict) else type(item).__name__))

    def payload(self, item: Any) -> dict[str, Any]:
        return dict(self.payload_for(item))

    def kind(self, item: Any) -> str:
        return self.kind_of(item)


@dataclass(frozen=True)
class DropTarget:
    """A stable node key that accepts certain payload kinds and emits ``intent``."""

    key: str
    intent: str
    accepts: tuple[str, ...] = ()

    def accepts_kind(self, kind: str) -> bool:
        return not self.accepts or kind in self.accepts


class IntentRouter:
    """Exact/prefix/default intent dispatch with typed rejections."""

    def __init__(self) -> None:
        self._exact: dict[str, IntentHandler] = {}
        self._prefix: list[tuple[str, IntentHandler]] = []
        self._default: IntentHandler | None = None
        self._drag_sources: dict[str, DragSource] = {}
        self._drop_targets: dict[str, DropTarget] = {}
        self._catalog: dict[str, Any] = {}  # stable node key -> domain item

    # -- registration -------------------------------------------------------

    def on(self, intent: str, handler: IntentHandler | None = None):
        """Register a handler for an exact intent (or ``prefix.*``).

        Usable directly (``router.on("x", fn)``) or as a decorator
        (``@router.on("x")``).
        """
        def _register(function: IntentHandler) -> IntentHandler:
            if intent.endswith(".*"):
                self._prefix.append((intent[:-1], function))
            elif intent == "*":
                self._default = function
            else:
                self._exact[intent] = function
            return function

        if handler is None:
            return _register
        return _register(handler)

    def default(self, handler: IntentHandler):
        self._default = handler
        return handler

    def drag_source(self, key: str, payload: Callable[[Any], dict[str, Any]] | None = None, *, kind_of: Callable[[Any], str] | None = None) -> DragSource:
        source = DragSource(key=key, payload_for=payload or DragSource.payload_for, kind_of=kind_of or DragSource.kind_of)
        self._drag_sources[key] = source
        return source

    def drop_target(self, key: str, intent: str, accepts: Iterable[str] | None = None) -> DropTarget:
        target = DropTarget(key=key, intent=intent, accepts=tuple(accepts or ()))
        self._drop_targets[key] = target
        return target

    def catalog(self, items: dict[str, Any]) -> None:
        """Bind stable node keys to domain items so drops can resolve payload."""
        self._catalog = dict(items)

    def register_catalog(self, key_of: Callable[[Any], str], items: Iterable[Any]) -> None:
        self._catalog = {key_of(item): item for item in items}

    # -- lookup -------------------------------------------------------------

    def has_intent(self, intent: str) -> bool:
        if intent in self._exact or self._default is not None:
            return True
        return any(intent.startswith(prefix) for prefix, _ in self._prefix)

    def handler_for(self, intent: str) -> IntentHandler:
        if intent in self._exact:
            return self._exact[intent]
        for prefix, handler in self._prefix:
            if intent.startswith(prefix):
                return handler
        if self._default is not None:
            return self._default
        raise UnsupportedIntentError(intent)

    # -- dispatch -----------------------------------------------------------

    async def dispatch(self, event: IntentEvent | DropEvent | dict[str, Any]) -> HandlerResult:
        """Route one semantic or drop event to its handler.

        Accepts an :class:`IntentEvent`, a :class:`DropEvent`, or a raw
        ``UiHostInbound`` envelope. Returns whatever the handler returns
        (``None``, a publication dict, or a store result). Raises
        :class:`UnsupportedIntentError`, :class:`UnknownTargetError`, or
        :class:`DropRejectedError` for the three distinguishable outcomes.
        """
        if isinstance(event, dict):
            event = self.resolve_inbound(event)
        if isinstance(event, DropEvent):
            handler = self.handler_for(event.intent or "")
        else:
            handler = self.handler_for(event.intent)
        result = handler(event)
        if inspect.isawaitable(result):
            result = await result
        return result

    def resolve_inbound(self, inbound: dict[str, Any]) -> IntentEvent | DropEvent:
        """Turn a raw host inbound envelope into a typed SDK event.

        A ``drag_drop`` resolves its SDK payload through the registered drag
        source and catalog, verifies the drop target exists (else
        :class:`UnknownTargetError`) and that it accepts the payload kind
        (else :class:`DropRejectedError`, domain state untouched).
        """
        kind = inbound.get("kind")
        event = inbound.get("event") or {}
        if kind == "semantic_intent":
            return IntentEvent.from_inbound(event)
        if kind == "drag_drop":
            wire = event.get("payload") or {}
            source_key = str(wire.get("source_key", ""))
            target_key = str(wire.get("target_key", ""))
            if target_key not in self._drop_targets:
                raise UnknownTargetError(target_key, kind="drop")
            if source_key not in self._drag_sources:
                raise UnknownTargetError(source_key, kind="drag")
            target = self._drop_targets[target_key]
            item = self._catalog.get(source_key)
            source = self._drag_sources[source_key]
            payload = source.payload(item) if item is not None else {}
            drop_kind = str(payload.get("kind", source.kind(item)))
            if not target.accepts_kind(drop_kind):
                raise DropRejectedError(
                    f"drop target {target_key!r} does not accept kind {drop_kind!r}",
                    source_key=source_key,
                    target_key=target_key,
                    accepted=target.accepts,
                )
            # The runtime enforces drop_record.intent == event.intent, so the
            # target's declared intent is authoritative when the envelope is
            # terse (SDK-built test fixtures) and agrees when it is not.
            resolved = {**event, "intent": event.get("intent") or target.intent}
            return DropEvent.from_inbound(resolved, payload=payload)
        raise UnsupportedIntentError(f"<unknown inbound kind: {kind}>")

    # -- introspection ------------------------------------------------------

    @property
    def intents(self) -> tuple[str, ...]:
        return tuple(sorted(self._exact))

    @property
    def drop_intents(self) -> dict[str, str]:
        return {key: target.intent for key, target in self._drop_targets.items()}
