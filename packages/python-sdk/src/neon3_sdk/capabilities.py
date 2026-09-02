"""Capability negotiation for the Neon3 SDK (docs/sdk-wire-contract.md §5).

``CapabilitySet`` is the single cross-language view of what the connected
runtime advertises. Flow constructs are mapped to the capabilities they need,
so ``UiClient.validate_flow`` can fail *before* submission with a typed
:class:`~neon3_sdk.errors.CapabilityError` instead of a vague runtime
rejection. Static checks mirror the runtime's own closed node vocabulary and
line grammar (neon-ui-runtime ``nui_flow.rs``) rather than guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .errors import CapabilityError, FlowValidationError
from .models import ServiceDescription

# Flow construct -> capabilities the runtime must advertise for it to work.
# Only capabilities real runtimes declare belong here. Constructs present in
# every supported runtime version (tooltip, modal, slider, ...) get no entry;
# a too-old runtime rejects them itself as ``nui_flow_unknown_component``,
# which submit_flow surfaces as a typed RemoteError instead.
FLOW_CAPABILITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "data_grid": ("ui.data_grid.window.v1",),
    "canvas": ("ui.canvas.points_lines.v1",),
    "image": ("ui.image.upload.v1",),
    "input": ("ui.text_input.commit.v1",),
    "motion": ("ui.state.animation.v1",),
    "transition": ("ui.state.animation.v1",),
    "drag": ("ui.semantic_input.v1", "ui.intent_dispatch.v1"),
    "drop": ("ui.semantic_input.v1", "ui.intent_dispatch.v1"),
}

# Constructs that always ride on the semantic input path.
SEMANTIC_EVENT_CAPABILITIES = ("ui.semantic_input.v1", "ui.intent_dispatch.v1")

# Capabilities advertised only by the renderer process. A UI-session client
# (connected to the ui-runtime endpoint) cannot describe them, so Flow
# submission validation must not gate on them; the render-bound component
# helpers negotiate them against the wgpu-runtime instead.
RENDERER_ONLY_CAPABILITIES = frozenset({"ui.canvas.points_lines.v1"})

# Capability -> owning service, used when a caller validates against a single
# service's advertised set (docs/sdk-wire-contract.md §5.1).
def capability_owner(capability: str) -> str:
    """Return the service that advertises ``capability`` in the base runtime."""
    if capability in RENDERER_ONLY_CAPABILITIES or capability.startswith("wgpu."):
        return "wgpu-runtime"
    return "ui-runtime"

# Closed node vocabulary from neon-ui-runtime nui_flow.rs::parse_node.
KNOWN_FLOW_COMPONENTS = frozenset({
    "surface", "panel", "scroll", "overlay", "branch", "repeat", "template",
    "data_grid", "tooltip", "modal", "dialog", "text", "button", "input",
    "checkbox", "radio_button", "slider", "drag_value", "combo", "dropdown",
    "tabs", "selectable", "list_box", "scrollbar", "progress_bar", "image",
    "render", "canvas", "world",
})

# Declaration heads (not node components) that start a top-level statement.
DECLARATION_HEADS = frozenset({"drag", "drop", "motion", "transition"})

# State-machine declaration forms (nui_flow.rs parse_state_machine_declaration).
STATE_MACHINE_HEADS = frozenset({"machine", "sync", "on", "state"})

# Indent-0 directive heads the runtime special-cases before node parsing.
DIRECTIVE_HEADS = frozenset({
    "version", "flow", "budget", "input", "grid_input", "resource",
    "text_registry", "surface_bind", "camera", "style", "binding",
    "resource_bind",
})

_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class FlowComponentInfo:
    """One construct discovered while scanning a Flow document."""

    component: str
    line: int
    column: int
    key: str | None = None


@dataclass(frozen=True)
class CapabilitySet:
    """Immutable view of the capabilities one or more services advertise."""

    services: tuple[str, ...] = ()
    capabilities: frozenset[str] = field(default_factory=frozenset)
    epochs: tuple[int, ...] = ()

    @classmethod
    def from_descriptions(cls, descriptions: Iterable[ServiceDescription]) -> "CapabilitySet":
        services: list[str] = []
        capabilities: set[str] = set()
        epochs: list[int] = []
        for description in descriptions:
            services.append(description.service)
            capabilities.update(description.capabilities)
            epochs.append(description.epoch)
        return cls(services=tuple(services), capabilities=frozenset(capabilities), epochs=tuple(epochs))

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def missing(self, *capabilities: str) -> tuple[str, ...]:
        return tuple(name for name in capabilities if name not in self.capabilities)

    def require(self, *capabilities: str, service: str = "") -> "CapabilitySet":
        """Return self when every capability is advertised, else raise."""
        gaps = self.missing(*capabilities)
        if gaps:
            raise CapabilityError(gaps, service=service)
        return self

    def union(self, other: "CapabilitySet") -> "CapabilitySet":
        return CapabilitySet(
            services=self.services + tuple(name for name in other.services if name not in self.services),
            capabilities=self.capabilities | other.capabilities,
            epochs=self.epochs + other.epochs,
        )


@dataclass(frozen=True)
class _Line:
    raw: str
    number: int
    indent: int
    tokens: list[str]


def _content_lines(source: str) -> list[_Line]:
    """Return non-empty, non-comment lines with their indent and tokens."""
    lines: list[_Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_Line(raw=raw, number=number, indent=indent, tokens=stripped.split()))
    return lines


def _node_component(line: _Line) -> str | None:
    """Return the capability-bearing component for a line, if any.

    Distinguishes the indent-0 scalar/grid ``input`` declaration from an
    ``input`` text node (indent > 0), matching the runtime's indent-0
    directive dispatch. ``world panel`` reports as ``panel``.
    """
    head = line.tokens[0] if line.tokens else ""
    if head == "world":
        return "panel" if len(line.tokens) >= 3 and line.tokens[1] == "panel" else None
    if head in DECLARATION_HEADS:
        return head
    if head in {"data_grid", "canvas", "image"}:
        return head
    if head == "input":
        return "input" if line.indent > 0 else None
    if head in KNOWN_FLOW_COMPONENTS:
        return head
    return None


def _node_key(line: _Line, component: str) -> str | None:
    head = line.tokens[0] if line.tokens else ""
    if head == "world":
        raw_key = line.tokens[2] if len(line.tokens) > 2 else None
    else:
        raw_key = line.tokens[1] if len(line.tokens) > 1 else None
    return raw_key if raw_key and _KEY_RE.match(raw_key) else None


def scan_flow(source: str) -> tuple[FlowComponentInfo, ...]:
    """Extract capability-bearing constructs with their line/column location.

    Conservative tokenizer over the closed vocabulary. The inline ``event``
    keyword (on any node) and the ``emit`` keyword (on ``drop``/state-machine
    ``on`` transitions) both imply the semantic-input path, so they are
    detected even on lines that are not otherwise node constructs.
    """
    found: list[FlowComponentInfo] = []
    for line in _content_lines(source):
        head = line.tokens[0]
        column = line.raw.index(head) + 1
        component = _node_component(line)
        if component is not None:
            found.append(FlowComponentInfo(component=component, line=line.number, column=column, key=_node_key(line, component)))
        stripped = line.raw.strip()
        if " event " in f" {stripped} " or " emit " in f" {stripped} ":
            found.append(FlowComponentInfo(component="event", line=line.number, column=column, key=None))
    return tuple(found)


def required_capabilities_for_flow(source: str) -> tuple[str, ...]:
    """Capabilities a Flow needs, derived from the constructs it uses."""
    needed: set[str] = set()
    for info in scan_flow(source):
        if info.component == "event":
            needed.update(SEMANTIC_EVENT_CAPABILITIES)
        needed.update(FLOW_CAPABILITY_REQUIREMENTS.get(info.component, ()))
    return tuple(sorted(needed))


# Heads the runtime accepts for a content line: node components plus the
# indent-0 directive and declaration forms. Used only to catch obvious typos
# locally; the runtime remains authoritative for full grammar validation.
_ACCEPTED_HEADS = (
    KNOWN_FLOW_COMPONENTS
    | DECLARATION_HEADS
    | STATE_MACHINE_HEADS
    | DIRECTIVE_HEADS
    | frozenset({"text", "resource_bind", "binding", "style"})
)


def validate_flow_source(source: str, capabilities: CapabilitySet | None = None, *, service: str = "ui-runtime") -> tuple[str, ...]:
    """Statically validate a Flow before submission.

    Raises :class:`CapabilityError` when ``capabilities`` is provided and the
    runtime lacks a capability the Flow requires. Independently, a content
    line whose head token is neither a known node component nor a recognized
    directive/declaration form raises :class:`FlowValidationError` with the
    line/column (mirroring the runtime ``nui_flow_unknown_component`` code),
    so callers get a precise location instead of a runtime round-trip.
    Returns the required capability tuple when valid. Only capabilities owned
    by ``service`` are gated against ``capabilities``; renderer-owned
    capabilities (e.g. the canvas point/line pipeline) are reported in the
    return value but negotiated separately by the render-bound helpers.
    """
    required = required_capabilities_for_flow(source)
    if capabilities is not None:
        gated = tuple(name for name in required if capability_owner(name) == service)
        gaps = capabilities.missing(*gated)
        if gaps:
            raise CapabilityError(gaps, service=service)
    for line in _content_lines(source):
        head = line.tokens[0]
        if head.startswith("@") or head in _ACCEPTED_HEADS:
            continue
        raise FlowValidationError(
            f"component is outside the closed Flow vocabulary: {head}",
            line=line.number,
            column=line.raw.index(head) + 1,
            code_runtime="nui_flow_unknown_component",
        )
    return required


def describe_capabilities(client: Any, targets: tuple[str, ...] = ("ui-runtime", "wgpu-runtime")) -> CapabilitySet:
    """Query the connected runtime and build the advertised capability set."""
    return CapabilitySet.from_descriptions(client.describe(target) for target in targets)
