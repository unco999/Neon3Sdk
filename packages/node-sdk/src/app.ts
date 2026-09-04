/** Generic application façade for the Stage 007 vertical slice. */
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { EventClient } from "./event.js";
import { NeonClient } from "./client.js";
import { RenderClient } from "./render.js";
import { RuntimeConfig, RuntimeSession } from "./runtime.js";
import { AndroidConfig, AndroidSession } from "./android.js";
import { IntentRouter } from "./routing.js";
import { UiSession } from "./session.js";
import { ObservableStore } from "./store.js";
import { UiClient, UiProgram } from "./ui.js";

export interface InboundOutcome { response: Record<string, unknown>; publication?: unknown; intent?: string; replayed?: boolean; error?: unknown; }

export class NeonAppUi {
  constructor(private readonly app: NeonApp, readonly session: UiSession) {}
  get client(): UiClient { return this.session.ui; }
  get activeProgram(): UiProgram | null { return this.session.program; }
  mountFlow(source: string, options: { validate?: boolean; idempotencyKey?: string } = {}): Promise<UiProgram> { return this.app.mountFlow(source, options); }
  mountFlowFile(path: string, options: { validate?: boolean; idempotencyKey?: string } = {}): Promise<UiProgram> { return this.app.mountFlowFile(path, options); }
  bind(nodeKey: string, source: any, options: any = {}): Promise<any> { return this.app.bind(nodeKey, source, options); }
  collection(nodeKey: string, options: { source: any; fallback?: "list" | "reject"; [key: string]: unknown }): Promise<any> { return this.app.bind(nodeKey, options.source, options); }
  dragSource(key: string, options: { payload?: (item: any) => Record<string, unknown>; kindOf?: (item: any) => string } = {}): any { return this.app.router.dragSource(key, options); }
  dropTarget(key: string, intent: string, accepts: string[] = []): any { return this.app.router.dropTarget(key, intent, accepts); }
  publish(changes: any[] = [], options: { requestId?: string } = {}): Promise<unknown> { return this.session.publish(changes, options); }
  flush(): { program_revision: number; input_revision: number; renderer_epoch: number; frame_sequence: number | null } { return this.session.flush(); }
}

export class NeonApp {
  readonly router = new IntentRouter();
  readonly ui: NeonAppUi;
  readonly bindings: any[] = [];
  readonly origin: string;
  store: ObservableStore | null;
  runtime: RuntimeSession | null = null;
  android: AndroidSession | null = null;
  client: NeonClient | any;
  render: RenderClient | null = null;
  events: EventClient | null = null;
  private readonly dedupe = new Map<string, InboundOutcome>();

  private constructor(readonly config: RuntimeConfig, origin: string, store?: ObservableStore, client?: any, readonly external = false) {
    this.origin = origin;
    this.store = store ?? null;
    this.client = client;
    const uiClient = new UiClient(client);
    const session = new UiSession(uiClient);
    this.ui = new NeonAppUi(this, session);
  }

  static async start(options: RuntimeConfig & { origin?: string; store?: ObservableStore; external?: boolean; transport?: "loopback" | "android"; android?: AndroidConfig } = {}): Promise<NeonApp> {
    const { origin = "neon3-app", store, external = false, transport = "loopback", android: androidConfig, ...runtimeOptions } = options;
    const config: RuntimeConfig = runtimeOptions;
    const app = new NeonApp(config, origin, store, undefined, external);
    if (transport === "android") {
      // The Android host runs inside an APK foreground service. No local
      // runtime processes are spawned; the SDK connects to the device through
      // adb forward (or a direct device IP) and talks to the single headless
      // endpoint as if it were both ui-runtime and wgpu-runtime.
      const session = new AndroidSession(androidConfig ?? {});
      await session.start();
      app.android = session;
      try {
        app.client = new NeonClient(session.endpoint, { origin, kind: "app_host", allowNonLoopback: true });
        app.render = new RenderClient(new NeonClient(session.endpoint, { origin, kind: "app_host", allowNonLoopback: true }));
        // The single Android endpoint answers service.health/describe, ui.*,
        // and wgpu.*; there is no separate eventd stream.
        app.events = null;
        (app.ui as any).session.ui = new UiClient(app.client, "wgpu-runtime");
        return app;
      } catch (error) { await app.stop(); throw error; }
    }
    if (!external) { app.runtime = new RuntimeSession(config); await app.runtime.start(); }
    try {
      app.client = new NeonClient(config.ui ?? "127.0.0.1:39102", { origin, kind: "app_host" });
      app.render = new RenderClient(new NeonClient(config.wgpu ?? "127.0.0.1:39103", { origin, kind: "app_host" }));
      app.events = new EventClient(config.eventd ?? "127.0.0.1:39101", { origin, kind: "app_host" });
      (app.ui as any).session.ui = new UiClient(app.client);
      return app;
    } catch (error) { await app.stop(); throw error; }
  }

  static offline(options: { origin?: string; store?: ObservableStore; client: any }): NeonApp {
    return new NeonApp({ mode: "headless", ...options.client.config }, options.origin ?? "neon3-app-offline", options.store, options.client, true);
  }

  get session(): UiSession { return this.ui.session; }
  async mountFlow(source: string, options: { validate?: boolean; idempotencyKey?: string } = {}): Promise<UiProgram> { return this.session.mountFlow(source, options); }
  async mountFlowFile(path: string, options: { validate?: boolean; idempotencyKey?: string } = {}): Promise<UiProgram> { return this.mountFlow(await readFile(path, "utf8"), options); }
  intent(name: string): (handler: any) => any { return this.router.on(name) as (handler: any) => any; }
  async bind(nodeKey: string, source: any, options: any = {}): Promise<any> {
    const { fallback = "list", ...bindingOptions } = options;
    const binding = await this.session.ui.collection(nodeKey, source, { ...bindingOptions, fallback });
    this.bindings.push(binding);
    (this.router as any).addBinding?.(binding);
    return binding;
  }
  async runOnce(events: Array<Record<string, unknown>>): Promise<InboundOutcome[]> {
    const results: InboundOutcome[] = [];
    for (const entry of events) results.push(await this.handleInbound(entry));
    return results;
  }
  async handleInbound(inbound: Record<string, any>): Promise<InboundOutcome> {
    const event = (inbound.event ?? {}) as Record<string, any>;
    const eventId = String(event.event_id ?? "");
    const cached = this.dedupe.get(eventId);
    if (cached) return { ...cached, replayed: true };
    try {
      const resolved = this.router.resolveInbound(inbound);
      const intent = resolved.intent ?? "";
      const handler = () => this.router.handlerFor(intent)(resolved);
      const result = this.store ? await this.store.transaction(handler) : await handler();
      const publication = this.store && this.session.program
        ? this.store.buildPublication(this.session.program.program_revision as any, Number(event.input_revision ?? this.session.inputRevision), eventId || randomUUID())
        : undefined;
      if (this.store && publication) this.store.markApplied();
      const nextRevision = Number(event.input_revision ?? this.session.inputRevision) + 1;
      if (this.external) this.session.inputRevision = Math.max(this.session.inputRevision, nextRevision);
      const response: Record<string, unknown> = { request_id: event.request_id ?? eventId, status: "accepted", revision: nextRevision, result: publication ?? result ?? null, snapshot: this.store?.toWire() ?? null, error: null };
      const outcome = { response, publication, intent };
      this.dedupe.set(eventId, outcome);
      return outcome;
    } catch (error: any) {
      return { response: { request_id: event.request_id ?? eventId, status: "rejected", revision: null, result: null, snapshot: null, error: { code: error.code ?? "domain_rejected", message: error.message } }, error };
    }
  }
  async stop(): Promise<void> { if (this.runtime) { await this.runtime.stop(); this.runtime = null; } if (this.android) { await this.android.stop(); this.android = null; } }
}
