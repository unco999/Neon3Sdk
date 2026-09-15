"""React-hooks-style façade over the Neon3 SDK.

This is the public "easy mode" API. It wraps :class:`~neon3_sdk.app.NeonApp`
and :class:`~neon3_sdk.store.ObservableStore` so a counter demo reads::

    from neon3_sdk.facade import start, mount, state, on, run

    with start(mode="windowed", origin="demo"):
        mount("counter.nui")
        count = state(0)

        @on("btn.increment")
        def _():
            count.value += 1

        run()

The lower-level ``NeonApp`` is still available as ``app.neon`` inside the
context if you need fine-grained control.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from .app import NeonApp
from .constants import AnimationAction
from .errors import CapabilityError
from .store import ObservableStore

# ---------------------------------------------------------------------------
# Global "current app" context (like React's current renderer).
#
# ``with start(...)`` pushes a FacadeApp onto this thread-local stack; the
# module-level ``mount``/``state``/``on`` helpers operate on the top. This
# keeps the example code free of explicit ``app.`` everywhere.
# ---------------------------------------------------------------------------

_thread_local = threading.local()


def _current() -> "FacadeApp":
    try:
        stack: list[FacadeApp] = _thread_local.stack  # type: ignore[attr-defined]
    except AttributeError:
        stack = []
        _thread_local.stack = stack  # type: ignore[attr-defined]
    if not stack:
        raise RuntimeError(
            "No active Neon3 app. Wrap your code in `with start(...) as app:` "
            "before calling mount()/state()/on()."
        )
    return stack[-1]


def _push(app: "FacadeApp") -> None:
    try:
        stack: list[FacadeApp] = _thread_local.stack  # type: ignore[attr-defined]
    except AttributeError:
        stack = []
        _thread_local.stack = stack  # type: ignore[attr-defined]
    stack.append(app)


def _pop() -> None:
    try:
        stack: list[FacadeApp] = _thread_local.stack  # type: ignore[attr-defined]
        stack.pop()
    except (AttributeError, IndexError):
        pass


# ---------------------------------------------------------------------------
# State[T]: a readable/writable scalar that auto-publishes on assignment.
# ---------------------------------------------------------------------------


class State:
    """A readable/writable scalar bound to the current app's store.

    ``s.value`` reads the current value; ``s.value = x`` writes it and
    immediately publishes one ``ui.input.frame`` (throttled to the next
    microtask / RPC batch). This is the ``useState`` analogue.
    """

    __slots__ = ("_key", "_app", "_store")

    def __init__(self, key: str, app: "FacadeApp") -> None:
        self._key = key
        self._app = app
        self._store = app.store

    @property
    def key(self) -> str:
        return self._key

    @property
    def value(self) -> Any:
        raw = self._store.value(self._key).get()
        # Unwrap the wire envelope {"kind": ..., "value": ...} into the raw
        # Python value so users get `42`, not `{"kind": "i32", "value": 42}`.
        if isinstance(raw, dict) and "kind" in raw and "value" in raw:
            return raw["value"]
        return raw

    @value.setter
    def value(self, new_value: Any) -> None:
        self._store.value(self._key).set(new_value)
        self._app._publish_now()

    # Python niceties: let `count += 1` work by reading, modifying, writing.
    def __iadd__(self, other: Any) -> "State":
        self.value = self.value + other  # type: ignore[operator]
        return self

    def __repr__(self) -> str:
        return f"State({self._key!r}={self.value!r})"


# ---------------------------------------------------------------------------
# Sub-namespaces: app.shader.* / app.renderer.* / app.anim.* / app.surface.*
# ---------------------------------------------------------------------------


class _ShaderNamespace:
    """``app.shader.on(event_id)`` — subscribe to WGSL emit_shader_event."""

    def __init__(self, app: "FacadeApp") -> None:
        self._app = app

    def on(self, event_id: int) -> Callable[[Callable[[list[float]], Any]], Callable[[list[float]], Any]]:
        """Decorator: register a handler for a specific shader event_id.

        The handler receives a ``list[float]`` of length 4 (the payload).
        """
        def decorator(handler: Callable[[list[float]], Any]) -> Callable[[list[float]], Any]:
            self._app._shader_handlers[int(event_id)] = handler
            return handler
        return decorator


class _RendererNamespace:
    """``app.renderer.view_extras(...)`` — upload shader uniform data."""

    def __init__(self, app: "FacadeApp") -> None:
        self._app = app
        self._last_flush = 0.0
        self._pending: list[list[float]] | None = None

    def view_extras(self, *rows: list[float]) -> None:
        """Upload 1..10 rows of vec4 to ``view.extras[0..9]``.

        Fewer than 10 rows are padded with ``[0, 0, 0, 0]``. Calls are
        throttled to 60 Hz; multiple calls within one frame batch into a
        single RPC.
        """
        if not 1 <= len(rows) <= 10:
            raise ValueError(f"view_extras expects 1..10 rows, got {len(rows)}")
        for i, row in enumerate(rows):
            if len(row) != 4:
                raise ValueError(f"row {i} must have 4 floats, got {len(row)}")
        self._pending = [list(r) for r in rows]
        now = time.monotonic()
        if now - self._last_flush >= 1.0 / 60.0:
            self.flush()

    def flush(self) -> None:
        """Force-pending view_extras immediately (bypasses the 60 Hz throttle)."""
        if self._pending is None:
            return
        rows = self._pending
        self._pending = None
        self._last_flush = time.monotonic()
        if self._app.neon.render is None:
            return
        self._app.neon.render.set_view_extras(rows)


class _AnimNamespace:
    """``app.anim.pause/resume/seek/cancel`` — renderer-owned timeline control."""

    def __init__(self, app: "FacadeApp") -> None:
        self._app = app

    def _render(self):
        if self._app.neon.render is None:
            raise CapabilityError("wgpu.ui.animation.control.v1")
        return self._app.neon.render

    def pause(self, node_path: str) -> None:
        self._render().animation_pause(node_path)

    def resume(self, node_path: str) -> None:
        self._render().animation_resume(node_path)

    def cancel(self, node_path: str) -> None:
        self._render().animation_cancel(node_path)

    def seek(self, node_path: str, progress: float) -> None:
        self._render().animation_seek(node_path, progress)


# ---------------------------------------------------------------------------
# FacadeApp: the context-manager object returned by start().
# ---------------------------------------------------------------------------


class PNG:
    """A rendered PNG returned by ``app.surface.render(...)``."""

    def __init__(self, path: str) -> None:
        self._path = path

    @property
    def path(self) -> str:
        """The on-disk path the runtime wrote."""
        return self._path

    def save(self, path: str) -> None:
        """Copy the rendered PNG to ``path``."""
        import shutil
        shutil.copyfile(self._path, path)

    def bytes(self) -> bytes:
        """Read the PNG bytes from disk."""
        with open(self._path, "rb") as f:
            return f.read()


class _SurfaceNamespace:
    """``app.surface.render(nui, size=(w, h)) -> PNG`` — offscreen render to file."""

    def __init__(self, app: "FacadeApp") -> None:
        self._app = app

    def render(self, nui: str, *, size: tuple[int, int] = (1280, 720),
               surface_id: str = "facade-offscreen") -> PNG:
        """Render a NUI flow offscreen and return a PNG handle.

        Opens a shared surface, mounts the flow, captures one frame as PNG,
        and returns a :class:`PNG` you can ``.save(path)`` or ``.bytes()``.
        """
        import os
        import uuid
        from .render import ExternalSurface, SurfaceKind, SurfaceOpen, SurfaceSize

        if self._app.neon.render is None:
            raise RuntimeError("render client is not available (offline?)")
        w, h = size
        sid = f"{surface_id}-{uuid.uuid4().hex[:8]}"
        out_path = os.path.join(os.environ.get("TEMP", "."), f"neon3-{uuid.uuid4().hex[:8]}.png")
        surface = self._app.neon.render.open_surface(SurfaceOpen(
            session_id=self._app.origin,
            surface_id=sid,
            kind=SurfaceKind.SCREEN_UI,
            size=SurfaceSize(width=w, height=h),
            buffer_count=1,
        ))
        # Mount flow onto the surface
        self._app.neon.ui.mount_flow(nui)
        surface.save_png(out_path)
        return PNG(out_path)


class FacadeApp:
    """The high-level app object. Created by :func:`start`, used as a context
    manager. Inside ``with start(...) as app:`` the module-level helpers
    (``mount``/``state``/``on``) operate on it.
    """

    def __init__(self, neon: NeonApp) -> None:
        self.neon = neon
        self.store: ObservableStore = neon.store or ObservableStore()
        if neon.store is None:
            neon.store = self.store
        self._state_counter = 0
        self._shader_handlers: dict[int, Callable[[list[float]], Any]] = {}
        self._shader_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        # sub-namespaces
        self.shader = _ShaderNamespace(self)
        self.renderer = _RendererNamespace(self)
        self.anim = _AnimNamespace(self)
        self.surface = _SurfaceNamespace(self)

    # --------------------------------------------------------- lifecycle
    def __enter__(self) -> "FacadeApp":
        _push(self)
        self._start_shader_dispatch()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._stop_flag.set()
        try:
            self.renderer.flush()
        finally:
            try:
                self.neon.stop()
            finally:
                _pop()

    # --------------------------------------------------------- helpers
    def mount(self, source: str | Path) -> Any:
        """Mount a NUI flow. Accepts a file path (``.nui``) or a NUI string."""
        if isinstance(source, (str, Path)) and Path(source).is_file():
            return self.neon.ui.mount_flow_file(source)  # type: ignore[union-attr]
        return self.neon.ui.mount_flow(str(source))  # type: ignore[union-attr]

    def state(self, initial: Any, *, node: str | None = None) -> State:
        """Register a new reactive scalar and return a ``State`` handle."""
        self._state_counter += 1
        key = node or f"state_{self._state_counter}"
        slot = self.store.value(key)
        slot.set(initial)
        slot.mark_applied()
        return State(key, self)

    def on(self, intent: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator: register a semantic-intent handler."""
        return self.neon.intent(intent)

    def run(self, *, block: bool = True) -> Any:
        """Block and serve the domain endpoint (callbacks arrive here)."""
        return self.neon.run(block=block)

    # --------------------------------------------------------- internals
    def _publish_now(self) -> None:
        """Flush pending scalar diffs to the runtime immediately."""
        try:
            self.neon.publish()
        except Exception:
            # Offline apps / tests may not have a live connection; swallow.
            pass

    def _start_shader_dispatch(self) -> None:
        """Background thread: subscribe to shader.event and dispatch by id."""
        if self.neon.events is None:
            return

        def loop() -> None:
            try:
                sub = self.neon.events.subscribe("shader.event")  # type: ignore[union-attr]
            except Exception:
                return
            while not self._stop_flag.is_set():
                try:
                    envelope = sub.recv(timeout=0.2)
                except Exception:
                    continue
                if envelope is None:
                    continue
                payload = envelope.payload
                event_id = int(payload.get("event_id", 0))
                handler = self._shader_handlers.get(event_id)
                if handler is None:
                    continue
                values = [float(v) for v in payload.get("payload", [0.0, 0.0, 0.0, 0.0])]
                try:
                    handler(values)
                except Exception:
                    # A user handler must not kill the dispatch thread.
                    pass

        self._shader_thread = threading.Thread(target=loop, daemon=True)
        self._shader_thread.start()


# ---------------------------------------------------------------------------
# Module-level helpers (operate on the current app).
# ---------------------------------------------------------------------------


def start(
    *,
    mode: str = "windowed",
    origin: str = "neon3-facade",
    **kwargs: Any,
) -> FacadeApp:
    """Boot (or attach to) the Neon3 runtime and return a context manager.

    Use as ``with start(...) as app: ...``. The app is automatically stopped
    when the block exits.
    """
    neon = NeonApp.start(mode=mode, origin=origin, **kwargs)
    return FacadeApp(neon)


def mount(source: str | Path) -> Any:
    """Mount a NUI flow on the current app."""
    return _current().mount(source)


def state(initial: Any, *, node: str | None = None) -> State:
    """Create a reactive scalar bound to the current app's store."""
    return _current().state(initial, node=node)


def on(intent: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a semantic-intent handler on the current app."""
    return _current().on(intent)


def run(*, block: bool = True) -> Any:
    """Block and serve (only needed after the ``with`` block if you want to
    keep the process alive; inside the block this is optional)."""
    return _current().run(block=block)
