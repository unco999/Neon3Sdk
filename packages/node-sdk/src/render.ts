import { NeonClient } from "./client.js";

export type SurfaceKind = "screen_ui" | "world_ui";
export interface Camera3D { cameraId: string; worldSpaceId: string; position: [number, number, number]; orientationXyzw: [number, number, number, number]; verticalFovRadians: number; near: number; far: number; producerEpoch: number; sequence: number; }
export interface WorldInformation { worldSpaceId: string; revision: number; coordinateSystem?: string; unitsPerMeter?: number; precisionMode?: string; }
export interface SurfaceOpen { sessionId: string; surfaceId: string; kind: SurfaceKind; width: number; height: number; format?: string; colorSpace?: "srgb" | "linear"; depth?: boolean; bufferCount?: number; placement?: Record<string, unknown>; targets?: Array<{ targetId: string; kind: "color" | "id"; format: string }>; }

export class RenderClient {
  constructor(readonly client: NeonClient, readonly target = "wgpu-runtime") {}
  async diagnostics(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.diagnostics")).result; }
  async graphSnapshot(): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.graph.snapshot")).result; }
  async configureWorld(world: WorldInformation): Promise<unknown> { return (await this.client.call(this.target, "wgpu.world.info.configure", { world_space_id: world.worldSpaceId, revision: world.revision, coordinate_system: world.coordinateSystem ?? "right_handed_y_up_negative_z_forward", units_per_meter: world.unitsPerMeter ?? 1, precision_mode: world.precisionMode ?? "camera_relative_f64" }, { idempotencyKey: `world:${world.worldSpaceId}:${world.revision}` })).result; }
  async submitCamera(camera: Camera3D): Promise<unknown> { return (await this.client.call(this.target, "wgpu.world.camera.submit_frame", { camera_id: camera.cameraId, world_space_id: camera.worldSpaceId, producer_epoch: camera.producerEpoch, sequence: camera.sequence, timestamp_monotonic_ns: Number(process.hrtime.bigint()), payload: { kind: "three_dimensional", position: camera.position, orientation: camera.orientationXyzw, vertical_fov_radians: camera.verticalFovRadians, near: camera.near, far: camera.far } }, { idempotencyKey: `camera:${camera.cameraId}:${camera.sequence}` })).result; }
  async capture(path: string, target = "ui.color.v1"): Promise<unknown> { return (await this.client.call(this.target, "wgpu.render.target.capture", { target, path, redraw: true })).result; }
  async pointer(event: unknown): Promise<unknown> { return (await this.client.call(this.target, "ui.host.pointer_event", { event })).result; }
  async openSurface(open: SurfaceOpen): Promise<ExternalSurface> { const result = (await this.client.call(this.target, "render.surface.open", { session_id: open.sessionId, surface_id: open.surfaceId, kind: open.kind, size: { width: open.width, height: open.height }, format: open.format ?? "rgba8unorm", color_space: open.colorSpace ?? "srgb", depth: open.depth ?? false, buffer_count: open.bufferCount ?? 1, placement: open.placement ?? null, targets: (open.targets ?? []).map((target) => ({ target_id: target.targetId, kind: target.kind, format: target.format })) }, { idempotencyKey: `surface-open:${open.surfaceId}` })).result as Record<string, unknown>; return new ExternalSurface(this, open.surfaceId, result); }
}

export class ExternalSurface {
  constructor(readonly renderer: RenderClient, readonly surfaceId: string, readonly descriptor: Record<string, unknown>) {}
  async acquire(pid = process.pid): Promise<unknown> { return (await this.renderer.client.call(this.renderer.target, "render.surface.acquire", { surface_id: this.surfaceId, pid })).result; }
  async frame(): Promise<unknown> { return (await this.renderer.client.call(this.renderer.target, "render.surface.frame", { surface_id: this.surfaceId })).result; }
}
