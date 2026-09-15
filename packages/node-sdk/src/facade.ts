/**
 * React-hooks-style façade over the Neon3 SDK.
 *
 * This is the public "easy mode" API. It wraps `NeonApp` and `ObservableStore`
 * so a counter demo reads:
 *
 * ```ts
 * import { start, mount, state, on } from "@neon3/sdk";
 *
 * const app = await start({ mode: "windowed" });
 * await mount("counter.nui");
 * const count = state(0);
 *
 * on("btn.increment")(() => {
 *   count.value++;
 * });
 *
 * await app.run();
 * ```
 *
 * The lower-level `NeonApp` is still available as `app.neon` inside the
 * context if you need fine-grained control.
 */

import { NeonApp } from "./app.js";
import { ObservableStore } from "./store.js";

// ---------------------------------------------------------------------------
// Global "current app" context.
//
// The module-level `mount`/`state`/`on` helpers operate on the most recently
// started app. Call `start()` to set it; call `app.dispose()` to clear it.
// ---------------------------------------------------------------------------

let currentApp: FacadeApp | null = null;

export function getCurrentApp(): FacadeApp {
  if (!currentApp) {
    throw new Error(
      "No active Neon3 app. Call `await start(...)` before mount()/state()/on().",
    );
  }
  return currentApp;
}

// ---------------------------------------------------------------------------
// State<T>: a readable/writable scalar that auto-publishes on assignment.
// ---------------------------------------------------------------------------

export class State<T = unknown> {
  readonly key: string;

  constructor(key: string, private readonly app: FacadeApp) {
    this.key = key;
  }

  get value(): T {
    const raw = this.app.store.value(this.key).get();
    // Unwrap the wire envelope { kind, value } into the raw value.
    if (raw && typeof raw === "object" && "kind" in raw && "value" in raw) {
      return (raw as unknown as { value: T }).value;
    }
    return raw as T;
  }

  set value(v: T) {
    this.app.store.value(this.key).set(v);
    void this.app.publishNow();
  }
}

// ---------------------------------------------------------------------------
// Sub-namespaces.
// ---------------------------------------------------------------------------

class ShaderNamespace {
  private readonly handlers = new Map<number, (payload: number[]) => void>();

  constructor(private readonly app: FacadeApp) {}

  /** Register a handler for a specific shader event_id. */
  on(eventId: number, handler: (payload: number[]) => void): void {
    this.handlers.set(eventId, handler);
  }

  /** Internal: dispatch one decoded shader event. */
  dispatch(eventId: number, payload: number[]): void {
    const h = this.handlers.get(eventId);
    if (h) {
      try {
        h(payload);
      } catch {
        // A user handler must not kill the dispatch loop.
      }
    }
  }
}

class RendererNamespace {
  private lastFlush = 0;
  private pending: number[][] | null = null;

  constructor(private readonly app: FacadeApp) {}

  /** Upload 1..10 rows of vec4 to `view.extras[0..9]`. Throttled to 60 Hz. */
  viewExtras(...rows: number[][]): void {
    if (rows.length < 1 || rows.length > 10) {
      throw new Error(`view_extras expects 1..10 rows, got ${rows.length}`);
    }
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].length !== 4) {
        throw new Error(`row ${i} must have 4 floats, got ${rows[i].length}`);
      }
    }
    this.pending = rows.map((r) => [...r]);
    const now = performance.now();
    if (now - this.lastFlush >= 1000 / 60) {
      void this.flush();
    }
  }

  async flush(): Promise<void> {
    if (!this.pending) return;
    const rows = this.pending;
    this.pending = null;
    this.lastFlush = performance.now();
    if (this.app.neon.render) {
      await this.app.neon.render.setViewExtras(rows);
    }
  }
}

class AnimNamespace {
  constructor(private readonly app: FacadeApp) {}

  private renderClient() {
    if (!this.app.neon.render) {
      throw new Error("Capability not available: wgpu.ui.animation.control.v1");
    }
    return this.app.neon.render;
  }

  pause(nodePath: string): Promise<unknown> {
    return this.renderClient().animationPause(nodePath);
  }
  resume(nodePath: string): Promise<unknown> {
    return this.renderClient().animationResume(nodePath);
  }
  cancel(nodePath: string): Promise<unknown> {
    return this.renderClient().animationCancel(nodePath);
  }
  seek(nodePath: string, progress: number): Promise<unknown> {
    return this.renderClient().animationSeek(nodePath, progress);
  }
}

/** A rendered PNG returned by `app.surface.render(...)`. */
export class Png {
  constructor(readonly path: string) {}

  save(dest: string): Promise<void> {
    return import("node:fs/promises").then((fs) => fs.copyFile(this.path, dest));
  }

  bytes(): Promise<Buffer> {
    return import("node:fs/promises").then((fs) => fs.readFile(this.path));
  }
}

class SurfaceNamespace {
  constructor(private readonly app: FacadeApp) {}

  /** Render a NUI flow offscreen and return a PNG handle. */
  async render(
    nui: string,
    options: { size?: [number, number]; surfaceId?: string } = {},
  ): Promise<Png> {
    if (!this.app.neon.render) throw new Error("render client not available (offline?)");
    const [w, h] = options.size ?? [1280, 720];
    const sid = `${options.surfaceId ?? "facade-offscreen"}-${crypto.randomUUID().slice(0, 8)}`;
    const os = await import("node:os");
    const path = await import("node:path");
    const outPath = path.join(os.tmpdir(), `neon3-${crypto.randomUUID().slice(0, 8)}.png`);
    const surface = await this.app.neon.render.openSurface({
      session_id: this.app.neon.origin,
      surface_id: sid,
      kind: "screen_ui",
      size: { width: w, height: h },
      buffer_count: 1,
    } as never);
    await this.app.neon.ui.mountFlow(nui);
    await surface.savePng(outPath);
    return new Png(outPath);
  }
}

// ---------------------------------------------------------------------------
// FacadeApp: the high-level app object returned by start().
// ---------------------------------------------------------------------------

export class FacadeApp {
  readonly store: ObservableStore;
  readonly shader: ShaderNamespace;
  readonly renderer: RendererNamespace;
  readonly anim: AnimNamespace;
  readonly surface: SurfaceNamespace;

  private stateCounter = 0;

  private constructor(readonly neon: NeonApp) {
    this.store = neon.store ?? new ObservableStore();
    if (!neon.store) neon.store = this.store;
    this.shader = new ShaderNamespace(this);
    this.renderer = new RendererNamespace(this);
    this.anim = new AnimNamespace(this);
    this.surface = new SurfaceNamespace(this);
  }

  static async boot(options: Parameters<typeof NeonApp.start>[0] = {}): Promise<FacadeApp> {
    const neon = await NeonApp.start(options);
    const app = new FacadeApp(neon);
    currentApp = app;
    return app;
  }

  async mount(source: string): Promise<unknown> {
    return this.neon.ui.mountFlow(source);
  }

  state<T>(initial: T, node?: string): State<T> {
    this.stateCounter += 1;
    const key = node ?? `state_${this.stateCounter}`;
    const slot = this.store.value(key);
    slot.set(initial);
    slot.markApplied();
    return new State<T>(key, this);
  }

  on(intent: string, handler: (...args: unknown[]) => void): void {
    this.neon.router.on(intent, handler as never);
  }

  async run(): Promise<void> {
    // The Node runtime uses the same blocking serve loop; for now this is a
    // no-op because the NeonApp already serves on its own socket server.
  }

  async publishNow(): Promise<void> {
    try {
      await this.neon.ui.publish();
    } catch {
      // Offline apps / tests may not have a live connection.
    }
  }

  async dispose(): Promise<void> {
    await this.renderer.flush();
    this.neon.stop();
    if (currentApp === this) currentApp = null;
  }
}

// ---------------------------------------------------------------------------
// Module-level helpers.
// ---------------------------------------------------------------------------

export async function start(
  options: Parameters<typeof NeonApp.start>[0] = {},
): Promise<FacadeApp> {
  return FacadeApp.boot(options);
}

export async function mount(source: string): Promise<unknown> {
  return getCurrentApp().mount(source);
}

export function state<T>(initial: T, node?: string): State<T> {
  return getCurrentApp().state(initial, node);
}

export function on(intent: string, handler: (...args: unknown[]) => void): void {
  getCurrentApp().on(intent, handler);
}

// performance.now shim for non-browser runtimes
declare const performance: { now(): number };
