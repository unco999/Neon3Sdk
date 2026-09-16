"""Canonical wire constants and enums for the Neon3 protocol.

Every service name, RPC method, event name, and animation action that used to
be a bare string literal now lives here. Import these and your IDE will
autocomplete; a typo becomes a NameError at import time, not a runtime
``unsupported_method``.

    from neon3_sdk.constants import service, method, event_name, AnimationAction

    client.call(service.WGPU_RUNTIME, method.WGPU_UI_SET_VIEW_EXTRAS, {...})
    client.call(service.WGPU_RUNTIME, AnimationAction.PAUSE.method(), {...})
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class service:
    """Service target names (the ``target`` field of every RPC envelope)."""

    EVENTD = "eventd"
    UI_RUNTIME = "ui-runtime"
    WGPU_RUNTIME = "wgpu-runtime"
    #: Headless editor document service backing the NUI ``code_editor``
    #: component (v0.2.10+). Serves the ``editor.document.v1``,
    #: ``editor.changeset.v1``, and ``editor.completion.v1`` capabilities.
    EDITOR_RUNTIME = "editor-runtime"


class method:
    """RPC method names, grouped by the service that answers them."""

    # service lifecycle
    SERVICE_HEALTH = "service.health"
    SERVICE_DESCRIBE = "service.describe"
    SERVICE_SHUTDOWN = "service.shutdown"

    # ui-runtime
    UI_FLOW_SUBMIT = "ui.flow.submit"
    UI_HOST_INBOUND = "ui.host.inbound"
    UI_INPUT_FRAME = "ui.input.frame"
    UI_HOST_POINTER_EVENT = "ui.host.pointer_event"

    # debug
    DEBUG_SNAPSHOT_GET = "debug.snapshot.get"
    DEBUG_UI_HOST_SNAPSHOT = "debug.ui.host.snapshot"

    # wgpu-runtime: surfaces
    RENDER_SURFACE_OPEN = "render.surface.open"
    RENDER_SURFACE_ACQUIRE = "render.surface.acquire"
    RENDER_SURFACE_FRAME = "render.surface.frame"
    RENDER_SURFACE_CAPTURE_PNG = "render.surface.capture_png"

    # wgpu-runtime: diagnostics
    WGPU_RENDER_DIAGNOSTICS = "wgpu.render.diagnostics"
    WGPU_RENDER_GRAPH_SNAPSHOT = "wgpu.render.graph.snapshot"

    # v0.2.7 shader extras
    WGPU_UI_SET_VIEW_EXTRAS = "wgpu.ui.set_view_extras"

    # v0.2.10 animation
    WGPU_UI_ANIMATION_PREFIX = "wgpu.ui.animation."

    # wgpu-runtime: custom text material packages
    WGPU_SHADER_REGISTER = "wgpu.shader.register"
    WGPU_SHADER_STATE = "wgpu.shader.state"

    # editor-runtime: code_editor document service (v0.2.10+)
    EDITOR_DOCUMENT_OPEN = "editor.document.open"
    EDITOR_DOCUMENT_SNAPSHOT_GET = "editor.document.snapshot.get"
    EDITOR_DOCUMENT_CHANGE_APPLY = "editor.document.change.apply"
    EDITOR_DOCUMENT_CHANGE_COMMIT = "editor.document.change.commit"
    EDITOR_COMPLETION_REQUEST = "editor.completion.request"
    EDITOR_DOCUMENT_CLOSE = "editor.document.close"


class event_name:
    """Event names published on eventd."""

    #: GPU→CPU event from WGSL ``emit_shader_event`` (v0.2.7).
    #: Payload: ``{event_id: int, payload: [float, float, float, float]}``.
    SHADER_EVENT = "shader.event"

    #: File-drop acceptance.
    UI_FILE_DROP_ACCEPTED = "ui.file_drop.accepted"

    #: Blank-area click (v0.2.9); outside-click dismissal.
    UI_CLICK_BLANK = "ui.click_blank"

    #: Semantic event kind emitted when a NUI ``code_editor`` node commits its
    #: document (v0.2.10+). Arrives over ``ui.host.inbound`` with the full
    #: document text in the ``text.value`` payload; the node's ``event``
    #: clause names the intent action (e.g. ``editor.commit``).
    DOCUMENT_COMMIT = "document_commit"


@enum.unique
class SurfaceKind(str, enum.Enum):
    """Rendered surface kind (NUI ``kind`` field)."""

    SCREEN_UI = "screen_ui"
    WORLD_UI = "world_ui"


@enum.unique
class AnimationAction(str, enum.Enum):
    """Animation control action (v0.2.10). Maps to ``wgpu.ui.animation.<action>``."""

    PAUSE = "pause"
    RESUME = "resume"
    SEEK = "seek"
    CANCEL = "cancel"

    def method(self) -> str:
        """Full RPC method: ``wgpu.ui.animation.<action>``."""
        return f"{method.WGPU_UI_ANIMATION_PREFIX}{self.value}"
