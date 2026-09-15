import { NeonClient } from "./client.js";
import { animationMethod, AnimationAction, method as rpcMethod } from "./constants.js";
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

/** Bounded custom-shader material package. Mirrors `UiShaderPackage`. */
export interface ShaderParameter {
  key: string;
  kind: "f32" | "vec2" | "vec4" | "color";
  default_value?: unknown;
  range?: [number, number];
}

export interface ShaderPackage {
  package_id: string;
  version: number;
  /** FNV-1a 64-bit hex fingerprint of `source_bytes`; see shaderSourceDigest. */
  source_digest: string;
  /** WGSL source as a byte array (bounded; JSON-safe array). */
  source_bytes: number[];
  entry_point: string;
  fallback: string;
  parameters: ShaderParameter[];
}

/** Deterministic FNV-1a 64-bit fingerprint (hex) matching the runtime. */
export function shaderSourceDigest(bytes: Uint8Array | number[]): string {
  let big = 0xcbf29ce484222325n;
  for (const byte of bytes) {
    big ^= BigInt(byte);
    big = (big * 0x100000001b3n) & 0xffffffffffffffffn;
  }
  return big.toString(16).padStart(16, "0");
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
  /**
   * @param client control-plane client (service.* / wgpu.* / debug.*)
   * @param target service name, defaults to wgpu-runtime
   * @param externalClient optional client that identifies as an external GPU
   *   host. `render.surface.open/acquire/frame/capture_png` require the
   *   `external_host` client kind, so callers that share one `NeonClient`
   *   (e.g. an app hosted by a native engine) pass a dedicated host client
   *   here. When omitted, surface calls fall back to `client`.
   */
  constructor(readonly client: NeonClient, readonly target = "wgpu-runtime", readonly externalClient?: NeonClient) {}

  get surfaceClient(): NeonClient {
    return this.externalClient ?? this.client;
  }

  async diagnostics(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.diagnostics")).result; }
  async graphSnapshot(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.graph.snapshot")).result; }

  /**
   * Register a validated custom-shader material package (`UiShaderPackage`).
   * The runtime re-computes the digest, enforces the source budget, and caches
   * the package for later material binding. See `shaderSourceDigest`.
   */
  async registerShader(pkg: ShaderPackage): Promise<unknown> {
    return (await this.client.call(this.target, "wgpu.shader.register", { package: pkg })).result;
  }

  /** Structured snapshot of every registered shader package. */
  async shaderState(): Promise<unknown> {
    return (await this.client.call(this.target, "wgpu.shader.state")).result;
  }

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
    const result = await this.surfaceClient.call<SurfaceDescriptor>(this.target, "render.surface.open", {
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

  /**
   * Upload 10 groups of vec4 to the shader's `view.extras[0..9]` uniform
   * (`wgpu.ui.set_view_extras`, v0.2.7). `extras` may have 1..=10 rows;
   * missing rows are zero-padded to 10.
   */
  async setViewExtras(extras: number[][]): Promise<unknown> {
    if (extras.length < 1 || extras.length > 10) {
      throw new Error(`extras must have 1..=10 rows, got ${extras.length}`);
    }
    const padded: number[][] = [];
    for (const row of extras) {
      if (row.length !== 4) throw new Error(`each extras row must have 4 components, got ${row.length}`);
      for (const v of row) {
        if (!Number.isFinite(v)) throw new Error("view extras must contain only finite f32 values");
      }
      padded.push([...row]);
    }
    while (padded.length < 10) padded.push([0, 0, 0, 0]);
    return (await this.client.call(this.target, rpcMethod.WGPU_UI_SET_VIEW_EXTRAS, { extras: padded })).result;
  }

  /** Pause a renderer-owned animation timeline (`wgpu.ui.animation.pause`, v0.2.10). */
  async animationPause(nodePath: string): Promise<unknown> {
    return this._animationControl("pause", nodePath, undefined);
  }

  /** Resume a paused animation timeline (`wgpu.ui.animation.resume`). */
  async animationResume(nodePath: string): Promise<unknown> {
    return this._animationControl("resume", nodePath, undefined);
  }

  /** Cancel an animation timeline (`wgpu.ui.animation.cancel`). */
  async animationCancel(nodePath: string): Promise<unknown> {
    return this._animationControl("cancel", nodePath, undefined);
  }

  /** Seek an animation timeline to `progress` in [0, 1] (`wgpu.ui.animation.seek`). */
  async animationSeek(nodePath: string, progress: number): Promise<unknown> {
    if (!Number.isFinite(progress) || progress < 0 || progress > 1) {
      throw new Error(`animation progress must be finite in [0, 1], got ${progress}`);
    }
    return this._animationControl("seek", nodePath, progress);
  }

  private async _animationControl(action: AnimationAction, nodePath: string, progress: number | undefined): Promise<unknown> {
    if (!nodePath || !nodePath.trim()) throw new Error("node_path must be non-empty");
    const params: Record<string, unknown> = { node_path: nodePath };
    if (progress !== undefined) params.progress = progress;
    // The runtime rejects animation control without an envelope-level
    // idempotency key (see neon-wgpu-runtime v0.2.10 lib.rs).
    const idempotencyKey = `anim:${nodePath}:${action}:${crypto.randomUUID()}`;
    return (await this.client.call(
      this.target,
      animationMethod(action),
      params,
      { idempotencyKey },
    )).result;
  }
}

export class ExternalSurface {
  constructor(readonly renderer: RenderClient, readonly surfaceId: string, readonly descriptor: SurfaceDescriptor) {}

  get generation(): number {
    if (typeof this.descriptor.generation !== "number") throw new ProtocolError("surface descriptor is missing generation");
    return this.descriptor.generation;
  }

  async acquire(pid = process.pid): Promise<unknown> {
    return (await this.renderer.surfaceClient.call(this.renderer.target, "render.surface.acquire", { surface_id: this.surfaceId, pid })).result;
  }

  async frame(): Promise<FrameDescriptor | null> {
    return (await this.renderer.surfaceClient.call<FrameDescriptor | null>(this.renderer.target, "render.surface.frame", { surface_id: this.surfaceId })).result;
  }

  /**
   * Save the latest completed frame of this shared surface to a PNG file.
   * The wgpu runtime readbacks the surface texture and writes the artifact;
   * never exposes native handles over the protocol. Throws with
   * `backend_not_available` on hosts without a GPU surface export path.
   */
  async savePng(path: string): Promise<unknown> {
    return (await this.renderer.surfaceClient.call(this.renderer.target, "render.surface.capture_png", {
      surface_id: this.surfaceId,
      path,
    })).result;
  }
}
