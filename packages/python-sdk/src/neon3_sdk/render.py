"""Typed rendering, camera, external-surface, and pointer APIs."""

from __future__ import annotations

import enum
import math
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from .client import NeonClient
from .errors import ProtocolError


class SurfaceKind(str, enum.Enum):
    SCREEN_UI = "screen_ui"
    WORLD_UI = "world_ui"


class ColorSpace(str, enum.Enum):
    SRGB = "srgb"
    LINEAR = "linear"


class Backend(str, enum.Enum):
    DX12 = "dx12"
    VULKAN = "vulkan"
    METAL = "metal"
    GL = "gl"


@dataclass(frozen=True)
class BackendNegotiation:
    session_id: str
    preferred_backends: tuple[Backend, ...]
    required_features: tuple[str, ...] = ()
    host_kind: str = "custom"
    plugin_version: str = "0.1.0"
    adapter: dict[str, Any] | None = None

    def to_wire(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "preferred_backends": [backend.value for backend in self.preferred_backends], "required_features": list(self.required_features), "host": {"kind": self.host_kind, "pid": os.getpid(), "adapter": self.adapter or {}, "plugin_version": self.plugin_version}}


@dataclass(frozen=True)
class WorldInformation:
    world_space_id: str
    revision: int
    coordinate_system: str = "right_handed_y_up_negative_z_forward"
    units_per_meter: float = 1.0
    precision_mode: str = "camera_relative_f64"

    def to_wire(self) -> dict[str, Any]:
        if self.units_per_meter <= 0:
            raise ValueError("units_per_meter must be positive")
        return {"world_space_id": self.world_space_id, "revision": self.revision, "coordinate_system": self.coordinate_system, "units_per_meter": self.units_per_meter, "precision_mode": self.precision_mode}


@dataclass(frozen=True)
class SurfaceSize:
    width: int
    height: int

    def to_wire(self) -> dict[str, int]:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("surface dimensions must be positive")
        return {"width": self.width, "height": self.height}


@dataclass(frozen=True)
class SurfaceTarget:
    target_id: str
    kind: str = "color"
    format: str = "rgba8unorm"

    def to_wire(self) -> dict[str, str]:
        if self.kind not in {"color", "id"}:
            raise ValueError("surface target kind must be 'color' or 'id'")
        return {"target_id": self.target_id, "kind": self.kind, "format": self.format}


@dataclass(frozen=True)
class WorldPlacement:
    anchor_id: str | None = None
    position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float] | None = None
    scale: tuple[float, float, float] | None = None
    billboard: bool = False
    occlusion: str = "depth_test"

    def to_wire(self) -> dict[str, Any]:
        return {"anchor_id": self.anchor_id, "position": self.position, "rotation": self.rotation, "scale": self.scale, "billboard": self.billboard, "occlusion": self.occlusion}


@dataclass(frozen=True)
class SurfaceOpen:
    session_id: str
    surface_id: str
    kind: SurfaceKind
    size: SurfaceSize
    format: str = "rgba8unorm"
    color_space: ColorSpace = ColorSpace.SRGB
    depth: bool = False
    buffer_count: int = 1
    placement: WorldPlacement | None = None
    targets: tuple[SurfaceTarget, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        if self.kind is SurfaceKind.WORLD_UI and self.placement is None:
            raise ValueError("world-ui surfaces require placement")
        if self.buffer_count not in {1, 2, 3}:
            raise ValueError("buffer_count must be between 1 and 3")
        return {
            "session_id": self.session_id,
            "surface_id": self.surface_id,
            "kind": self.kind.value,
            "size": self.size.to_wire(),
            "format": self.format,
            "color_space": self.color_space.value,
            "depth": self.depth,
            "buffer_count": self.buffer_count,
            "placement": self.placement.to_wire() if self.placement else None,
            "targets": [target.to_wire() for target in self.targets],
        }


@dataclass(frozen=True)
class Camera3D:
    camera_id: str
    world_space_id: str
    position: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    vertical_fov_radians: float
    near: float
    far: float
    producer_epoch: int
    sequence: int
    timestamp_monotonic_ns: int | None = None

    def to_wire(self) -> dict[str, Any]:
        if not 0 < self.vertical_fov_radians < math.pi or self.near <= 0 or self.far <= self.near:
            raise ValueError("camera projection values are invalid")
        if len(self.position) != 3 or len(self.orientation_xyzw) != 4:
            raise ValueError("camera position/orientation dimensions are invalid")
        return {
            "camera_id": self.camera_id,
            "world_space_id": self.world_space_id,
            "producer_epoch": self.producer_epoch,
            "sequence": self.sequence,
            "timestamp_monotonic_ns": self.timestamp_monotonic_ns or time.monotonic_ns(),
            "payload": {"kind": "three_dimensional", "position": self.position, "orientation": self.orientation_xyzw, "vertical_fov_radians": self.vertical_fov_radians, "near": self.near, "far": self.far},
        }


@dataclass(frozen=True)
class PointerEvent:
    event_type: str
    surface_id: str
    pixel: tuple[float, float]
    pointer_id: int
    sequence: int
    generation: int
    frame_sequence: int
    button: str | None = None
    delta: tuple[float, float] = (0.0, 0.0)
    modifiers: tuple[str, ...] = ()
    timestamp_monotonic_ns: int | None = None

    def to_wire(self) -> dict[str, Any]:
        if self.event_type not in {"enter", "leave", "move", "down", "up", "wheel", "cancel"}:
            raise ValueError("invalid pointer event type")
        return {"event_type": self.event_type, "surface_id": self.surface_id, "pixel": self.pixel, "delta": self.delta, "delta_mode": "pixel", "button": self.button, "buttons": [self.button] if self.button else [], "modifiers": list(self.modifiers), "pointer_id": self.pointer_id, "sequence": self.sequence, "generation": self.generation, "frame_sequence": self.frame_sequence, "timestamp_monotonic_ns": self.timestamp_monotonic_ns or time.monotonic_ns()}


class RenderClient:
    """High-level wrapper for the WGPU runtime control-plane contract."""

    def __init__(self, client: NeonClient, target: str = "wgpu-runtime") -> None:
        self.client = client
        self.target = target

    def diagnostics(self) -> Any:
        return self.client.call(self.target, "wgpu.render.diagnostics").result

    def negotiate_external(self, negotiation: BackendNegotiation) -> Any:
        """Negotiate native interop before opening a shared surface."""
        return self.client.call(self.target, "render.backend.negotiate", negotiation.to_wire()).result

    def graph_snapshot(self) -> Any:
        return self.client.call(self.target, "wgpu.render.graph.snapshot").result

    def capture(self, path: str, *, target: str = "ui.color.v1", redraw: bool = True) -> Any:
        return self.client.call(self.target, "wgpu.render.target.capture", {"target": target, "path": path, "redraw": redraw}).result

    def submit_camera(self, camera: Camera3D, *, idempotency_key: str | None = None) -> Any:
        return self.client.call(self.target, "wgpu.world.camera.submit_frame", camera.to_wire(), idempotency_key=idempotency_key or f"camera:{camera.camera_id}:{camera.sequence}").result

    def configure_world(self, world: WorldInformation, *, idempotency_key: str | None = None) -> Any:
        return self.client.call(self.target, "wgpu.world.info.configure", world.to_wire(), idempotency_key=idempotency_key or f"world:{world.world_space_id}:{world.revision}").result

    def pointer(self, event: PointerEvent) -> Any:
        return self.client.call(self.target, "ui.host.pointer_event", {"event": event.to_wire()}).result

    def open_surface(self, surface: SurfaceOpen) -> "ExternalSurface":
        result = self.client.call(self.target, "render.surface.open", surface.to_wire(), idempotency_key=f"surface-open:{surface.surface_id}").result
        if not isinstance(result, dict):
            raise ProtocolError("render.surface.open returned a non-object result")
        return ExternalSurface(self, surface, result)


class ExternalSurface:
    """Descriptor-backed shared surface. Native handles are never interpreted by Python."""

    def __init__(self, renderer: RenderClient, request: SurfaceOpen, descriptor: dict[str, Any]) -> None:
        self.renderer = renderer
        self.request = request
        self.descriptor = descriptor

    @property
    def generation(self) -> int:
        return int(self.descriptor["generation"])

    def acquire(self, pid: int) -> Any:
        return self.renderer.client.call(self.renderer.target, "render.surface.acquire", {"surface_id": self.request.surface_id, "pid": pid}).result

    def acquire_current_process(self) -> Any:
        return self.acquire(os.getpid())

    def frame(self) -> Any:
        return self.renderer.client.call(self.renderer.target, "render.surface.frame", {"surface_id": self.request.surface_id}).result
