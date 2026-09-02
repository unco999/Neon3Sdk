import { NeonClient } from "./client.js";
import { ProtocolError } from "./errors.js";

export type SurfaceKind = "screen_ui" | "world_ui";
export type ColorSpace = "srgb" | "linear";

export interface Camera3D {
  cameraId: string;
  worldSpaceId: string;
  position: [number, number, number];
  orientationXyzw: [number, number, number, number];
  verticalFovRadians: number;
  near: number;
  far: number;
  producerEpoch: number;
  sequence: number;
}

export interface WorldInformation {
  worldSpaceId: string;
  revision: number;
  coordinateSystem?: string;
  unitsPerMeter?: number;
  precisionMode?: string;
}

export interface WorldPlacement {
  anchorId?: string | null;
  position?: [number, number, number] | null;
  rotation?: [number, number, number] | null;
  scale?: [number, number, number] | null;
  billboard?: boolean;
  occlusion?: string;
}

export interface SurfaceTarget {
  targetId: string;
  kind: "color" | "id";
  format: string;
}

export interface SurfaceOpen {
  sessionId: string;
  surfaceId: string;
  kind: SurfaceKind;
  width: number;
  height: number;
  format?: string;
  colorSpace?: ColorSpace;
  depth?: boolean;
  bufferCount?: number;
  placement?: WorldPlacement;
  targets?: SurfaceTarget[];
}

export interface SurfaceDescriptor {
  [key: string]: unknown;
  generation?: number;
}

export interface FrameDescriptor {
  [key: string]: unknown;
}

export interface PointerEventWire {
  event_type: string;
  surface_id: string;
  pixel: [number, number];
  delta: [number, number];
  delta_mode: "pixel";
  button: string | null;
  buttons: string[];
  modifiers: string[];
  pointer_id: number;
  sequence: number;
  generation: number;
  frame_sequence: number;
  timestamp_monotonic_ns: number;
}

const POINTER_EVENT_TYPES = new Set(["enter", "leave", "move", "down", "up", "wheel", "cancel"]);

export class PointerEvent {
  constructor(
    readonly eventType: string,
    readonly surfaceId: string,
    readonly pixel: [number, number],
    readonly pointerId: number,
    readonly sequence: number,
    readonly generation: number,
    readonly frameSequence: number,
    readonly button: string | null = null,
    readonly delta: [number, number] = [0, 0],
    readonly modifiers: string[] = [],
    readonly timestampMonotonicNs: number | null = null,
  ) {}

  toWire(): PointerEventWire {
    if (!POINTER_EVENT_TYPES.has(this.eventType)) throw new Error("invalid pointer event type");
    return {
      event_type: this.eventType,
      surface_id: this.surfaceId,
      pixel: this.pixel,
      delta: this.delta,
      delta_mode: "pixel",
      button: this.button,
      buttons: this.button ? [this.button] : [],
      modifiers: this.modifiers,
      pointer_id: this.pointerId,
      sequence: this.sequence,
      generation: this.generation,
      frame_sequence: this.frameSequence,
      timestamp_monotonic_ns: this.timestampMonotonicNs ?? Number(process.hrtime.bigint()),
    };
  }
}

export interface BackendNegotiation {
  sessionId: string;
  preferredBackends: string[];
  requiredFeatures?: string[];
  hostKind?: string;
  pluginVersion?: string;
  adapter?: Record<string, unknown>;
}

export class RenderClient {
  constructor(readonly client: NeonClient, readonly target = "wgpu-runtime") {}

  async diagnostics(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.diagnostics")).result; }
  async graphSnapshot(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.graph.snapshot")).result; }

  async negotiateBackend(negotiation: BackendNegotiation): Promise<unknown> {
    return (await this.client.call(this.target, "render.backend.negotiate", {
      session_id: negotiation.sessionId,
      preferred_backends: negotiation.preferredBackends,
      required_features: negotiation.requiredFeatures ?? [],
      host: {
        kind: negotiation.hostKind ?? "custom",
        pid: process.pid,
        adapter: negotiation.adapter ?? {},
        plugin_version: negotiation.pluginVersion ?? "0.1.0",
      },
    })).result;
  }

  async configureWorld(world: WorldInformation): Promise<unknown> {
    return (await this.client.call(this.target, "wgpu.world.info.configure", {
      world_space_id: world.worldSpaceId,
      revision: world.revision,
      coordinate_system: world.coordinateSystem ?? "right_handed_y_up_negative_z_forward",
      units_per_meter: world.unitsPerMeter ?? 1,
      precision_mode: world.precisionMode ?? "camera_relative_f64",
    }, { idempotencyKey: `world:${world.worldSpaceId}:${world.revision}` })).result;
  }

  async submitCamera(camera: Camera3D): Promise<unknown> {
    return (await this.client.call(this.target, "wgpu.world.camera.submit_frame", {
      camera_id: camera.cameraId,
      world_space_id: camera.worldSpaceId,
      producer_epoch: camera.producerEpoch,
      sequence: camera.sequence,
      timestamp_monotonic_ns: Number(process.hrtime.bigint()),
      payload: {
        kind: "three_dimensional",
        position: camera.position,
        orientation: camera.orientationXyzw,
        vertical_fov_radians: camera.verticalFovRadians,
        near: camera.near,
        far: camera.far,
      },
    }, { idempotencyKey: `camera:${camera.cameraId}:${camera.sequence}` })).result;
  }

  async capture(path: string, target = "ui.color.v1", redraw = true): Promise<unknown> {
    return (await this.client.call(this.target, "wgpu.render.target.capture", { target, path, redraw })).result;
  }

  async pointer(event: PointerEvent | PointerEventWire): Promise<unknown> {
    const wire = event instanceof PointerEvent ? event.toWire() : event;
    return (await this.client.call(this.target, "ui.host.pointer_event", { event: wire })).result;
  }

  async openSurface(open: SurfaceOpen): Promise<ExternalSurface> {
    if (open.kind === "world_ui" && !open.placement) throw new Error("world-ui surfaces require placement");
    if (open.bufferCount !== undefined && ![1, 2, 3].includes(open.bufferCount)) throw new Error("buffer_count must be between 1 and 3");
    const result = await this.client.call<SurfaceDescriptor>(this.target, "render.surface.open", {
      session_id: open.sessionId,
      surface_id: open.surfaceId,
      kind: open.kind,
      size: { width: open.width, height: open.height },
      format: open.format ?? "rgba8unorm",
      color_space: open.colorSpace ?? "srgb",
      depth: open.depth ?? false,
      buffer_count: open.bufferCount ?? 1,
      placement: open.placement
        ? {
            anchor_id: open.placement.anchorId ?? null,
            position: open.placement.position ?? null,
            rotation: open.placement.rotation ?? null,
            scale: open.placement.scale ?? null,
            billboard: open.placement.billboard ?? false,
            occlusion: open.placement.occlusion ?? "depth_test",
          }
        : null,
      targets: (open.targets ?? []).map((target) => ({ target_id: target.targetId, kind: target.kind, format: target.format })),
    }, { idempotencyKey: `surface-open:${open.surfaceId}` });
    if (result.result === null || typeof result.result !== "object") throw new ProtocolError("render.surface.open returned a non-object result");
    return new ExternalSurface(this, open.surfaceId, result.result);
  }
}

export class ExternalSurface {
  constructor(readonly renderer: RenderClient, readonly surfaceId: string, readonly descriptor: SurfaceDescriptor) {}

  get generation(): number {
    if (typeof this.descriptor.generation !== "number") throw new ProtocolError("surface descriptor is missing generation");
    return this.descriptor.generation;
  }

  async acquire(pid = process.pid): Promise<unknown> {
    return (await this.renderer.client.call(this.renderer.target, "render.surface.acquire", { surface_id: this.surfaceId, pid })).result;
  }

  async frame(): Promise<FrameDescriptor | null> {
    return (await this.renderer.client.call<FrameDescriptor | null>(this.renderer.target, "render.surface.frame", { surface_id: this.surfaceId })).result;
  }
}
