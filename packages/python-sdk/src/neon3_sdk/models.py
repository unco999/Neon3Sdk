"""Typed public values corresponding to Neon3 protocol schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssetRef:
    project_id: str
    asset_id: int
    revision: int
    kind: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "asset_id": self.asset_id,
            "revision": self.revision,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ClientIdentity:
    kind: str
    instance_id: str
    pid: int
    origin: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "instance_id": self.instance_id,
            "pid": self.pid,
            "origin": self.origin,
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ClientIdentity":
        return cls(**value)


@dataclass(frozen=True)
class RpcResponse:
    request_id: str
    status: str
    revision: int | None
    result: Any | None
    snapshot: Any | None
    error: dict[str, Any] | None

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "RpcResponse":
        required = {"request_id", "status", "revision", "result", "snapshot", "error"}
        unexpected = set(value) - required
        missing = required - set(value)
        if missing or unexpected:
            raise ValueError(f"invalid RpcResponse fields: missing={sorted(missing)}, unexpected={sorted(unexpected)}")
        return cls(**value)


@dataclass(frozen=True)
class ServiceHealth:
    service: str
    status: str
    epoch: int

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ServiceHealth":
        return cls(service=value["service"], status=value["status"], epoch=value["epoch"])


@dataclass(frozen=True)
class ServiceDescription:
    service: str
    protocol_version: dict[str, int]
    endpoint: str
    epoch: int
    capabilities: tuple[str, ...]

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ServiceDescription":
        return cls(
            service=value["service"],
            protocol_version=value["protocol_version"],
            endpoint=value["endpoint"],
            epoch=value["epoch"],
            capabilities=tuple(value["capabilities"]),
        )


@dataclass(frozen=True)
class EventEnvelope:
    protocol: str
    version: dict[str, int]
    event_id: str
    name: str
    schema_version: int
    epoch: int
    sequence: int
    timestamp_unix_ms: int
    publisher: ClientIdentity
    payload: Any

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "EventEnvelope":
        return cls(
            protocol=value["protocol"],
            version=value["version"],
            event_id=value["event_id"],
            name=value["name"],
            schema_version=value["schema_version"],
            epoch=value["epoch"],
            sequence=value["sequence"],
            timestamp_unix_ms=value["timestamp_unix_ms"],
            publisher=ClientIdentity.from_wire(value["publisher"]),
            payload=value["payload"],
        )


@dataclass(frozen=True)
class UiFileDropPayload:
    drop_sequence: int
    source_path: str
    file_name: str
    extension: str
    media_type: str
    is_image: bool
    renderer_epoch: int
    frame_sequence: int

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "UiFileDropPayload":
        return cls(**value)


@dataclass(frozen=True)
class InputSlot:
    """One scalar slot of a compiled ``input_schema`` (UiInputSlot)."""

    key: str
    kind: dict[str, Any]
    default_value: dict[str, Any]
    update_class: str
    semantic_label: str
    packing: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "default_value": self.default_value,
            "update_class": self.update_class,
            "semantic_label": self.semantic_label,
            "packing": self.packing,
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "InputSlot":
        return cls(
            key=value["key"],
            kind=value["kind"],
            default_value=value["default_value"],
            update_class=value["update_class"],
            semantic_label=value["semantic_label"],
            packing=value["packing"],
        )


@dataclass(frozen=True)
class ResolvedInputValue:
    """A host-resolved input value with provenance (UiResolvedInputValue)."""

    value: dict[str, Any]
    source: str
    last_update_revision: int

    def to_wire(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source, "last_update_revision": self.last_update_revision}

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ResolvedInputValue":
        return cls(value=value["value"], source=value["source"], last_update_revision=value["last_update_revision"])


@dataclass(frozen=True)
class ResolvedInputs:
    """Complete resolved scalar input state for one program revision."""

    program_revision: dict[str, Any]
    input_revision: int
    values: dict[str, ResolvedInputValue]
    changed_slots: tuple[str, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "program_revision": self.program_revision,
            "input_revision": self.input_revision,
            "values": {key: value.to_wire() for key, value in sorted(self.values.items())},
            "changed_slots": list(self.changed_slots),
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ResolvedInputs":
        return cls(
            program_revision=value["program_revision"],
            input_revision=value["input_revision"],
            values={key: ResolvedInputValue.from_wire(item) for key, item in value["values"].items()},
            changed_slots=tuple(value["changed_slots"]),
        )


@dataclass(frozen=True)
class ProgramInputSnapshot:
    """Result of ``debug.ui.host.snapshot`` (UiProgramInputSnapshot)."""

    scalar_inputs: ResolvedInputs
    grid_inputs: tuple[dict[str, Any], ...]

    def to_wire(self) -> dict[str, Any]:
        return {"scalar_inputs": self.scalar_inputs.to_wire(), "grid_inputs": [dict(frame) for frame in self.grid_inputs]}

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ProgramInputSnapshot":
        return cls(
            scalar_inputs=ResolvedInputs.from_wire(value["scalar_inputs"]),
            grid_inputs=tuple(dict(frame) for frame in value["grid_inputs"]),
        )


@dataclass(frozen=True)
class DebugSnapshot:
    """Result of ``debug.snapshot.get`` (DebugSnapshot envelope)."""

    service: str
    epoch: int
    revision: int
    health: str
    capabilities: tuple[str, ...]
    active_jobs: tuple[str, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "epoch": self.epoch,
            "revision": self.revision,
            "health": self.health,
            "capabilities": list(self.capabilities),
            "active_jobs": list(self.active_jobs),
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "DebugSnapshot":
        return cls(
            service=value["service"],
            epoch=value["epoch"],
            revision=value["revision"],
            health=value["health"],
            capabilities=tuple(value["capabilities"]),
            active_jobs=tuple(value["active_jobs"]),
        )


@dataclass(frozen=True)
class SemanticInteractionMetadata:
    """Renderer-owned interaction identity carried by every semantic event."""

    interaction_id: str
    sequence: int
    renderer_epoch: int

    def to_wire(self) -> dict[str, Any]:
        return {"interaction_id": self.interaction_id, "sequence": self.sequence, "renderer_epoch": self.renderer_epoch}

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "SemanticInteractionMetadata":
        return cls(interaction_id=value["interaction_id"], sequence=value["sequence"], renderer_epoch=value["renderer_epoch"])


@dataclass(frozen=True)
class UiProgramRevisionInfo:
    """The ``program_revision`` object exchanged on the wire (UiProgramRevision)."""

    program_id: str
    revision: int
    schema_version: int
    capabilities: tuple[dict[str, Any], ...] = ()

    def to_wire(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "capabilities": [dict(item) for item in self.capabilities],
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "UiProgramRevisionInfo":
        return cls(
            program_id=value["program_id"],
            revision=value["revision"],
            schema_version=value["schema_version"],
            capabilities=tuple(dict(item) for item in value["capabilities"]),
        )


@dataclass(frozen=True)
class InputChange:
    """One typed key/value change inside an input frame."""

    key: str
    value: dict[str, Any]

    def to_wire(self) -> dict[str, Any]:
        if self.value.get("kind") not in {
            "bool", "i32", "u32", "f32", "vec2", "vec4", "color",
            "enum", "text_handle", "asset_handle", "canvas_data",
        }:
            raise ValueError(f"invalid UiInputValue kind: {self.value.get('kind')!r}")
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "InputChange":
        return cls(key=value["key"], value=value["value"])


@dataclass(frozen=True)
class RevisionState:
    """Cross-language revision bookkeeping for the active program.

    ``frame_sequence`` is observed from renderer snapshots and must never be
    invented by the business layer.
    """

    program_revision: int
    input_revision: int
    renderer_epoch: int
    frame_sequence: int | None = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "program_revision": self.program_revision,
            "input_revision": self.input_revision,
            "renderer_epoch": self.renderer_epoch,
            "frame_sequence": self.frame_sequence,
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "RevisionState":
        return cls(
            program_revision=value["program_revision"],
            input_revision=value["input_revision"],
            renderer_epoch=value["renderer_epoch"],
            frame_sequence=value.get("frame_sequence"),
        )


@dataclass(frozen=True)
class UiTraceRecord:
    """One journal entry from ``debug.trace.query`` (UiEventTraceRecord)."""

    sequence: int
    event_id: str
    intent: str
    source_node_key: str
    program_revision: int
    input_revision: int
    renderer_epoch: int
    result: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "intent": self.intent,
            "source_node_key": self.source_node_key,
            "program_revision": self.program_revision,
            "input_revision": self.input_revision,
            "renderer_epoch": self.renderer_epoch,
            "result": self.result,
        }

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "UiTraceRecord":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__})


@dataclass(frozen=True)
class UiSnapshot:
    """Typed view over the debug snapshot pair (service + host inputs)."""

    service: DebugSnapshot
    host_inputs: ProgramInputSnapshot | None

    @classmethod
    def from_wire(cls, service: dict[str, Any], host_inputs: dict[str, Any] | None) -> "UiSnapshot":
        return cls(
            service=DebugSnapshot.from_wire(service),
            host_inputs=ProgramInputSnapshot.from_wire(host_inputs) if host_inputs is not None else None,
        )

    @property
    def revision_state(self) -> RevisionState:
        scalar = self.host_inputs.scalar_inputs if self.host_inputs else None
        return RevisionState(
            program_revision=scalar.program_revision["revision"] if scalar else 0,
            input_revision=scalar.input_revision if scalar else 0,
            renderer_epoch=self.service.epoch,
            frame_sequence=None,
        )
