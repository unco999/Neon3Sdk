"""NeonApp: the general-purpose application entry point (Stage 007).

Owns runtime lifecycle, client reuse, capability caching, the active
program/surface/epoch/input-revision lifecycle, intent routing, event
deduplication, error propagation and shutdown. Business code expresses one
UI flow::

    with NeonApp.start(mode="windowed", origin="inventory-example") as app:
        program = app.ui.mount_flow_file("inventory.nui")
        state = ObservableStore({"items": items, "selected": None})
        app.ui.bind("items", state.collection("items"))
        app.intent("domain.item.equip")(handle_equip)
        app.run()

`NeonApp` is a business host process: the runtime forwards
``ui.host.inbound`` (semantic intents, drag/drop commits) to the domain
endpoint; the router resolves and dispatches them, handlers mutate the
attached :class:`~neon3_sdk.store.ObservableStore`, and exactly one typed
``UiHostPublication`` — built from the store's pending diffs — answers the
RPC, which the runtime applies as the authoritative next fragment. No domain
models (inventory, calculator, editor) live here; examples supply those.

``run_once`` drives the identical dispatch path synchronously, so unit tests
and Stage 008 probes are behaviorally equal to the live socket path.
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .capabilities import CapabilitySet, describe_capabilities
from .client import NeonClient
from .android import AndroidConfig, AndroidSession
from .errors import NeonError
from .event import EventClient
from .models import RpcResponse, ServiceDescription
from .render import RenderClient
from .routing import IntentRouter
from .runtime import RuntimeConfig, RuntimeEndpoints, RuntimeMode, RuntimeSession
from .session import UiSession
from .store import ObservableStore
from .ui import UiClient, UiProgram

# Node keys the runtime accepts use letters/digits/'.'/'_'/'-'; the binding
# row separator must stay inside that set (see nui_flow invalid_key).
KEY_SEPARATOR = "."


def _response(request_id: str, status: str, *, result: Any = None, snapshot: Any = None, revision: int | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"request_id": request_id, "status": status, "revision": revision, "result": result, "snapshot": snapshot, "error": error}


def _recv_exact(stream: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection_closed")
        data.extend(chunk)
    return bytes(data)


class OfflineRpc:
    """A NeonClient stand-in for offline unit tests: canned describe, no I/O.

    Every ``call`` raises :class:`RuntimeUnavailableOffline` except
    ``service.describe``/``service.health`` for the capabilities cache.
    """

    class RuntimeUnavailableOffline(NeonError):
        code = "runtime_unavailable_offline"
        retryable = False

    def __init__(self, capabilities: CapabilitySet | None = None) -> None:
        self._capabilities = capabilities or CapabilitySet(services=("ui-runtime", "wgpu-runtime"), capabilities=frozenset({
            "ui.program.v1", "ui.semantic_input.v1", "ui.intent_dispatch.v1", "ui.program.input.v1",
            "ui.text_input.commit.v1", "ui.data_grid.window.v1", "ui.host.pointer_event.v1",
            "ui.state.animation.v1", "ui.numeric.animation.v1",
        }), epochs=(1, 1))

    def describe(self, target: str) -> ServiceDescription:
        return ServiceDescription(
            service=target,
            protocol_version={"major": 1, "minor": 0},
            endpoint=f"offline://{target}",
            epoch=self._capabilities.epoch_of(target) or 1,
            capabilities=tuple(cap for cap in sorted(self._capabilities.capabilities)),
        )

    def health(self, target: str):
        class _H:
            service = target
            status = "healthy"
            epoch = self._capabilities.epoch_of(target) or 1
        return _H()

    def call(self, target, method, params=None, **kwargs) -> RpcResponse:
        raise OfflineRpc.RuntimeUnavailableOffline(f"offline app cannot call {method} on {target}")


@dataclass
class InboundOutcome:
    """One host dispatch result: RPC response plus SDK-level diagnostics."""

    response: dict[str, Any]
    publication: dict[str, Any] | None = None
    intent: str = ""
    error: NeonError | None = None
    replayed: bool = False


class DomainService:
    """Generic Neon RPC host server bound to a NeonApp.

    Serves ``service.health`` / ``service.describe`` / ``debug.snapshot.get``
    and ``ui.host.inbound``. The inbound path defers entirely to
    :meth:`NeonApp.handle_inbound`, so the socket server and ``run_once``
    share one dispatch implementation.
    """

    def __init__(self, app: "NeonApp") -> None:
        host, port = app.config.domain_endpoint.rsplit(":", 1)
        self.endpoint = (host, int(port))
        self.app = app
        self._listener: socket.socket | None = None
        self._stop = threading.Event()
        self.ready = threading.Event()
        self.start_error: Exception | None = None

    def serve(self) -> None:
        try:
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(self.endpoint)
            listener.listen(16)
            listener.settimeout(0.2)
            self._listener = listener
            self.ready.set()
            while not self._stop.is_set():
                try:
                    stream, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle, args=(stream,), daemon=True).start()
        except OSError as error:
            self.start_error = error
            self.ready.set()
        finally:
            if self._listener is not None:
                self._listener.close()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()

    def _handle(self, stream: socket.socket) -> None:
        with stream:
            try:
                size = struct.unpack(">I", _recv_exact(stream, 4))[0]
                request = json.loads(_recv_exact(stream, size).decode("utf-8"))
            except (ConnectionError, UnicodeDecodeError, json.JSONDecodeError):
                return
            try:
                response = self.dispatch(request)
            except Exception as error:  # the server must always answer
                request_id = request.get("request_id", "unknown") if isinstance(request, dict) else "unknown"
                response = _response(request_id, "failed", error={"code": "domain_error", "message": str(error)})
            try:
                body = json.dumps(response, separators=(",", ":")).encode("utf-8")
                stream.sendall(struct.pack(">I", len(body)) + body)
            except OSError:
                pass

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id", ""))
        method = str(request.get("method", ""))
        if method == "service.health":
            return _response(request_id, "accepted", result={"service": self.app.service_name, "status": "healthy", "epoch": self.app.epoch})
        if method == "service.describe":
            return _response(request_id, "accepted", result={
                "service": self.app.service_name,
                "protocol_version": {"major": 1, "minor": 0},
                "endpoint": f"{self.endpoint[0]}:{self.endpoint[1]}",
                "epoch": self.app.epoch,
                "capabilities": list(self.app.service_capabilities),
            })
        if method == "debug.snapshot.get":
            return _response(request_id, "accepted", result=self.app.debug_snapshot())
        if method != "ui.host.inbound":
            return _response(request_id, "rejected", error={"code": "unsupported_method", "message": f"method is not supported: {method}"})
        outcome = self.app.handle_inbound(request.get("params") or {})
        response = dict(outcome.response)
        response["request_id"] = request_id
        return response


class _AppUi:
    """``app.ui`` façade over the revision-aware session."""

    def __init__(self, app: "NeonApp", session: UiSession) -> None:
        self._app = app
        self.session = session

    @property
    def client(self) -> UiClient:
        return self.session.ui

    @property
    def active_program(self) -> UiProgram | None:
        return self.session.program

    def mount_flow(self, source: str, **kwargs: Any) -> UiProgram:
        return self._app.mount_flow(source, **kwargs)

    def mount_flow_file(self, path: str | Path, **kwargs: Any) -> UiProgram:
        return self._app.mount_flow_file(path, **kwargs)

    def bind(self, node_key: str, collection: Any, **kwargs: Any):
        """Minimal generic binding (plan §3.1): bind a keyed collection store."""
        return self._app.bind(node_key, collection, **kwargs)

    def collection(self, node_key: str, *, source: Any, **kwargs: Any):
        """Full schema-driven collection binding (plan §3.5)."""
        return self._app.bind_collection(node_key, source, **kwargs)

    def drag_source(self, key: str, payload: Callable[[Any], dict[str, Any]], **kwargs: Any):
        return self._app.router.drag_source(key, payload, **kwargs)

    def drop_target(self, key: str, intent: str, accepts: tuple[str, ...] = ()):
        return self._app.router.drop_target(key, intent, accepts)

    def publish(self, changes: list[dict[str, Any]] | None = None, **kwargs: Any) -> Any:
        return self._app.publish(changes, **kwargs)

    async def flush(self) -> dict[str, Any]:
        return self._app.flush()


class NeonApp:
    """Application entry point wiring runtime, session, store and routing."""

    service_name = "neon3-app"
    service_capabilities = ("ui.host.publication.v1",)

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        mode: RuntimeMode = RuntimeMode.HEADLESS,
        origin: str = "neon3-app",
        external: bool = False,
        store: ObservableStore | None = None,
        service_name: str | None = None,
    ) -> None:
        self.config = config
        self.mode = mode
        self.origin = origin
        self.external = external
        self.epoch = 1
        self.store = store
        if service_name:
            self.service_name = service_name
        self.runtime: RuntimeSession | None = None
        self.android: AndroidSession | None = None
        self.client: NeonClient | Any | None = None
        self.render: RenderClient | None = None
        self.events: EventClient | None = None
        self.router = IntentRouter()
        self.ui: _AppUi | None = None
        self._session: UiSession | None = None
        self._server: DomainService | None = None
        self._server_thread: threading.Thread | None = None
        self._bindings: list[Any] = []
        self._selection_slots: dict[str, str] = {}
        self._dedupe: dict[str, InboundOutcome] = {}
        self._dispatch_log: list[InboundOutcome] = []
        self._closed = False

    # ------------------------------------------------------------------ boot

    @classmethod
    def start(
        cls,
        *,
        mode: str = "windowed",
        origin: str = "neon3-app",
        neon_root: Any = None,
        profile: Any = None,
        endpoints: RuntimeEndpoints | None = None,
        domain_endpoint: str | None = None,
        external: bool = False,
        store: ObservableStore | None = None,
        service_name: str | None = None,
        timeout_seconds: float | None = None,
        transport: str = "loopback",
        android: AndroidConfig | None = None,
    ) -> "NeonApp":
        """Launch (or attach to) the runtime and return a live app.

        ``transport="android"`` connects to a Neon3 Android Host inside an
        APK foreground service through adb forward (or a direct device IP)
        instead of starting local desktop processes. All three clients then
        share the single headless endpoint; ``UiClient`` targets
        ``wgpu-runtime`` because the Android host answers ``ui.*`` and
        ``wgpu.*`` on one socket.
        """
        runtime_mode = RuntimeMode(mode)
        base = RuntimeConfig()
        config = RuntimeConfig(
            neon_root=str(neon_root) if neon_root is not None else base.neon_root,
            mode=runtime_mode,
            endpoints=endpoints or base.endpoints,
            domain_endpoint=domain_endpoint or base.domain_endpoint,
            profile=profile if profile is not None else base.profile,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else base.timeout_seconds,
        )
        app = cls(config=config, mode=runtime_mode, origin=origin, external=external, store=store, service_name=service_name)
        if transport == "android":
            session = AndroidSession(android or AndroidConfig())
            session.start()
            app.android = session
            try:
                app._boot_android()
            except Exception:
                try:
                    session.stop()
                finally:
                    app.android = None
                raise
            return app
        app._boot()
        return app

    @classmethod
    def offline(
        cls,
        *,
        origin: str = "neon3-app-offline",
        store: ObservableStore | None = None,
        capabilities: CapabilitySet | None = None,
        program: dict[str, Any] | None = None,
        service_name: str | None = None,
    ) -> "NeonApp":
        """Build a runtime-less app for unit tests and fixture authoring.

        ``handle_inbound``/``run_once``/binding all work offline (no RPC);
        anything that would touch the runtime raises
        ``OfflineRpc.RuntimeUnavailableOffline``.
        """
        app = cls(config=RuntimeConfig(mode=RuntimeMode.HEADLESS), mode=RuntimeMode.HEADLESS, origin=origin, external=True, store=store, service_name=service_name)
        client = OfflineRpc(capabilities)
        ui = UiClient(client)  # type: ignore[arg-type]
        app.client = client
        app._session = UiSession(ui)
        app.ui = _AppUi(app, app._session)
        if program is not None:
            app.adopt_program(UiProgram.from_submission(program), synchronize=False)
        return app

    def _boot_android(self) -> None:
        """Connect all clients to the single Android headless endpoint.

        The Android host has no separate eventd stream, so ``events`` stays
        None; domain semantics stay in the SDK (the SDK is the business host).
        """
        assert self.android is not None
        self.client = NeonClient.connect(
            self.android.endpoint,
            origin=self.origin,
            kind="cli",
            allow_non_loopback=True,
        )
        self.render = RenderClient(
            NeonClient.connect(self.android.endpoint, origin=self.origin, kind="cli", allow_non_loopback=True)
        )
        self.events = None
        self._session = UiSession(UiClient(self.client, target="wgpu-runtime"))
        self.ui = _AppUi(self, self._session)

    def _boot(self) -> None:
        if not self.external:
            self.runtime = RuntimeSession(self.config)
            try:
                self.runtime.start()
            except Exception:
                self.runtime = None
                raise
        try:
            self.client = NeonClient.connect(self.config.endpoints.ui, origin=self.origin, kind="cli")
            self.render = RenderClient(NeonClient.connect(self.config.endpoints.wgpu, origin=self.origin, kind="cli"))
            self.events = EventClient.connect(self.config.endpoints.eventd, origin=self.origin, kind="app_host")
            self._session = UiSession(UiClient(self.client))
            self.ui = _AppUi(self, self._session)
        except Exception:
            if self.runtime is not None:
                self.runtime.stop()
                self.runtime = None
            raise

    def attach_store(self, store: ObservableStore) -> None:
        self.store = store

    # ------------------------------------------------------------- program

    def mount_flow(self, source: str, **kwargs: Any) -> UiProgram:
        program = self.session.mount_flow(source, **kwargs)
        self.adopt_program(program)
        return program

    def mount_flow_file(self, path: str | Path, **kwargs: Any) -> UiProgram:
        return self.mount_flow(Path(path).read_text(encoding="utf-8"), **kwargs)

    def adopt_program(self, program: UiProgram, *, synchronize: bool = True) -> None:
        """Adopt an already-mounted program and reset host-side ledgers."""
        self.session.adopt(program, synchronize=synchronize)
        self._dedupe.clear()
        self._dispatch_log.clear()

    @property
    def session(self) -> UiSession:
        if self._session is None:
            raise RuntimeError("NeonApp is not started")
        return self._session

    def capabilities(self, *, refresh: bool = False) -> CapabilitySet:
        return self.session.ui.capabilities(refresh=refresh)

    def require_capabilities(self, *capabilities: str) -> CapabilitySet:
        return self.session.ui.require_capabilities(*capabilities)

    # -------------------------------------------------------------- binding

    def bind(self, node_key: str, collection: Any, *, columns: Callable[[Any], dict[str, Any]] | None = None, selection_slot: str | None = None, **kwargs: Any):
        """Minimal generic binding from the plan's entry example (§3.1)."""
        effective_columns = columns or (lambda item: {
            "key": {"value": str(collection._key_of(item)), "display": {"id": 0, "generation": 0}},
        })
        binding = self.bind_collection(node_key, collection, columns=effective_columns, **kwargs)
        if selection_slot:
            self._selection_slots[collection.name] = selection_slot
        return binding

    def bind_collection(self, node_key: str, source: Any, **kwargs: Any):
        """Full schema-driven binding, capability-gated by the binder."""
        binding = self.session.ui.collection(node_key, source=source, **kwargs)
        self._bindings.append(binding)
        self.router.add_binding(binding)
        return binding

    def intent(self, name: str):
        """Decorator entry: ``@app.intent("domain.item.equip")`` (plan §3.1)."""
        return self.router.on(name)

    # ------------------------------------------------------------- publish

    def publication_from_store(self, program_revision: dict[str, Any], expected_input_revision: int, request_id: str) -> dict[str, Any]:
        """Build the single merged publication for all pending store diffs."""
        assert self.store is not None
        return self.store.build_publication(
            program_revision,
            expected_input_revision,
            request_id,
            cells_of=self._merged_cells_of(),
            selection_slots=self._selection_slots or None,
        )

    def _merged_cells_of(self):
        bindings = {binding.source.name: binding for binding in self._bindings}
        if not bindings:
            return None

        def cells_of(collection: Any, item: Any) -> dict[str, Any]:
            binding = bindings.get(collection.name)
            return binding.columns(item) if binding else {}

        return cells_of

    def publish(self, changes: list[dict[str, Any]] | None = None, *, request_id: str | None = None) -> Any:
        """Actively publish scalar-lane diffs through ``ui.input.frame``.

        Grid lanes ride on the next inbound host publication (the runtime's
        external frame schema is scalar-only). With no explicit changes, the
        store's pending scalar + selection diffs publish; acceptance marks
        only those lanes applied.
        """
        session = self.session
        request_id = request_id or str(uuid.uuid4())
        if changes is None and self.store is not None:
            changes = self._pending_scalar_changes()
            if not changes:
                return None
        if not changes:
            return None
        result = session.publish(changes, request_id=request_id)
        if self.store is not None:
            self.store.mark_scalars_applied()
        return result

    def _pending_scalar_changes(self) -> list[dict[str, Any]]:
        assert self.store is not None
        changes = list(self.store.changed_scalars())
        for name in self.store.changed_selections():
            slot = self._selection_slots.get(name)
            selected = self.store.selection(name).get()
            if slot and selected is not None:
                changes.append({"key": slot, "value": {"kind": "enum", "value": selected}})
        changes.sort(key=lambda change: change["key"])
        return changes

    def flush(self) -> dict[str, Any]:
        """Publish pending active diffs and report the revision state."""
        self.publish()
        return self.session.flush().to_wire()

    # -------------------------------------------------------------- inbound

    def handle_inbound(self, inbound: dict[str, Any]) -> InboundOutcome:
        """Process one forwarded ``ui.host.inbound`` envelope.

        Shared by the live socket server and ``run_once``: resolve through the
        router (structured ``unsupported_intent`` / ``unknown_target`` /
        ``drop_rejected``), run the handler inside a store transaction so a
        raise leaves no half publication, then build exactly one publication
        from the pending diffs and shape the host RPC response. Duplicate
        event ids replay the cached response without touching the store.
        """
        event = inbound.get("event") or {}
        request_id = str(event.get("request_id", "") or event.get("event_id", ""))
        event_id = str(event.get("event_id", ""))
        cached = self._dedupe.get(event_id) if event_id else None
        if cached is not None:
            response = dict(cached.response)
            response["request_id"] = request_id
            return InboundOutcome(response=response, publication=cached.publication, intent=cached.intent, replayed=True)

        try:
            resolved = self.router.resolve_inbound(inbound)
        except NeonError as error:
            response = _response(request_id, "rejected", error={"code": str(getattr(error, "code", type(error).__name__)), "message": str(error)})
            return InboundOutcome(response=response, intent="", error=error)

        intent = getattr(resolved, "intent", "") or ""
        try:
            if self.store is not None:
                with self.store.transaction():
                    result = self.router.run_handler(resolved)
                    if asyncio.iscoroutine(result):
                        asyncio.run(result)
            else:
                result = self.router.run_handler(resolved)
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
        except NeonError as error:
            response = _response(request_id, "rejected", error={"code": str(getattr(error, "code", type(error).__name__)), "message": str(error)})
            return InboundOutcome(response=response, intent=intent, error=error)
        except Exception as error:
            wrapped = NeonError(str(error))
            response = _response(request_id, "rejected", error={"code": "domain_rejected", "message": str(error)})
            return InboundOutcome(response=response, intent=intent, error=wrapped)

        if self.store is None:
            response = _response(request_id, "accepted", revision=int(event.get("input_revision", 0)) + 1, result=None, snapshot=self.debug_snapshot())
            outcome = InboundOutcome(response=response, intent=intent)
            self._record(event_id, outcome)
            return outcome

        try:
            publication = self.publication_from_store(
                event.get("program_revision") or self.session.program_revision_wire,
                int(event.get("input_revision", 0)),
                event_id or request_id or str(uuid.uuid4()),
            )
        except NeonError as error:
            self.store.reject_pending()
            response = _response(request_id, "rejected", error={"code": str(getattr(error, "code", type(error).__name__)), "message": str(error)})
            return InboundOutcome(response=response, intent=intent, error=error)
        self.store.mark_applied()

        new_revision = int(event.get("input_revision", 0)) + 1
        response = _response(request_id, "accepted", revision=new_revision, result=publication, snapshot=self.debug_snapshot())
        if self.external:
            self.session.input_revision = max(self.session.input_revision, new_revision)
        outcome = InboundOutcome(response=response, publication=publication, intent=intent)
        self._record(event_id, outcome)
        return outcome

    def _record(self, event_id: str, outcome: InboundOutcome) -> None:
        self._dispatch_log.append(outcome)
        if event_id:
            self._dedupe[event_id] = outcome

    def debug_snapshot(self) -> dict[str, Any]:
        return {
            "service": self.service_name,
            "epoch": self.epoch,
            "revision": self.session.input_revision if self._session else 0,
            "state": {
                "domain": self.store.to_wire() if self.store is not None else None,
                "input_revision": self.session.input_revision if self._session else 0,
            },
        }

    # --------------------------------------------------------------- running

    def serve(self, *, block: bool = True) -> DomainService:
        """Serve the domain endpoint; the runtime forwards UI events here."""
        if self._server is None:
            self._server = DomainService(self)
            self._server_thread = threading.Thread(target=self._server.serve, daemon=True)
            self._server_thread.start()
            self._server.ready.wait(timeout=5)
            if self._server.start_error:
                raise self._server.start_error
        if block:
            try:
                while not self._closed:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                pass
        return self._server

    def run(self, *, block: bool = True) -> DomainService:
        return self.serve(block=block)

    def run_once(self, events: list[str] | list[dict[str, Any]]) -> list[InboundOutcome]:
        """Drive the host dispatch path synchronously (tests/probes).

        Accepts shorthand strings — ``"drop:<source>:<target>"``,
        ``"intent:<name>"``, ``"intent:<name>:<json payload>"`` — or raw
        inbound envelopes; each goes through :meth:`handle_inbound` exactly as
        the socket path does.
        """
        return [self.handle_inbound(self._parse_event(entry)) for entry in events]

    def _parse_event(self, entry: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(entry, dict):
            return entry
        parts = str(entry).split(":", 2)
        kind = parts[0]
        if kind == "drop" and len(parts) >= 3:
            source_key, target_key = parts[1], parts[2]
            return self._envelope("drag_drop", {
                "drag_key": source_key,
                "drop_key": target_key,
                "payload": {"source_key": source_key, "target_key": target_key, "placement": "into"},
            })
        if kind == "intent" and len(parts) >= 2:
            payload = json.loads(parts[2]) if len(parts) > 2 else {}
            return self._envelope("semantic_intent", {
                "kind": "activate",
                "intent": parts[1],
                "source_node_key": "sdk",
                "payload": payload,
            })
        raise ValueError(f"unrecognized event shorthand: {entry!r}")

    def _envelope(self, kind: str, fields: dict[str, Any]) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        event: dict[str, Any] = {
            "event_id": event_id,
            "request_id": event_id,
            "idempotency_key": f"intent:{event_id}",
            "program_revision": self.session.program_revision_wire,
            "input_revision": self.session.input_revision,
            "interaction": {
                "interaction_id": event_id,
                "sequence": len(self._dispatch_log) + 1,
                "renderer_epoch": self.session.renderer_epoch or 0,
            },
            **fields,
        }
        return {"kind": kind, "event": event}

    # -------------------------------------------------------------- shutdown

    def stop(self) -> None:
        self._closed = True
        if self._server is not None:
            self._server.stop()
        if self._server_thread is not None:
            self._server_thread.join(timeout=3)
        if self.runtime is not None:
            self.runtime.stop()
            self.runtime = None
        if self.android is not None:
            try:
                self.android.stop()
            finally:
                self.android = None

    def __enter__(self) -> "NeonApp":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.stop()
