/**
 * Intent routing and drag/drop abstractions (Stage 005).
 *
 * `IntentRouter` turns any business semantic/drop event into a typed handler
 * call. It matches an exact intent first, then a registered prefix
 * (`domain.item.*`), then an optional default handler; an unmatched intent
 * throws a structured UnsupportedIntentError instead of being silently
 * dropped. Handlers may be sync or async.
 *
 * Drag/drop is declarative and generic. A `DragSource` binds a stable node key
 * to a payload factory; a `DropTarget` records which payload kinds it accepts
 * and which intent a completed drop dispatches. Mirrors `neon3_sdk/routing.py`
 * — nothing here knows about inventory, equipment or recipes.
 */

import { DropRejectedError, UnknownTargetError, UnsupportedIntentError } from "./errors.js";
import { DropEvent, IntentEvent } from "./protocol.js";

export interface DragSourceSpec {
  key: string;
  payloadFor: (item: unknown) => Record<string, unknown>;
  kindOf: (item: any) => string;
}

export interface DropTargetSpec {
  key: string;
  intent: string;
  accepts: string[];
}

export type IntentHandler = (event: IntentEvent | DropEvent) => unknown | Promise<unknown>;

const defaultPayloadFor = (item: any): Record<string, unknown> =>
  item && typeof item === "object" ? { ...item } : { key: item };
const defaultKindOf = (item: any): string =>
  item && typeof item === "object" && "kind" in item ? String(item.kind) : typeof item;

export class DragSource implements DragSourceSpec {
  constructor(readonly key: string, readonly payloadFor: (item: any) => Record<string, unknown> = defaultPayloadFor, readonly kindOf: (item: any) => string = defaultKindOf) {}
  payload(item: any): Record<string, unknown> { return { ...this.payloadFor(item) }; }
  kind(item: any): string { return this.kindOf(item); }
}

export class DropTarget implements DropTargetSpec {
  constructor(readonly key: string, readonly intent: string, readonly accepts: string[] = []) {}
  acceptsKind(kind: string): boolean { return this.accepts.length === 0 || this.accepts.includes(kind); }
}

export class IntentRouter {
  private readonly exact = new Map<string, IntentHandler>();
  private readonly prefixes: Array<[string, IntentHandler]> = [];
  private defaultHandler: IntentHandler | null = null;
  private readonly dragSources = new Map<string, DragSource>();
  private readonly dropTargets = new Map<string, DropTarget>();
  private catalog = new Map<string, any>();
  private readonly bindings: Array<any> = [];

  /** Register a handler for an exact intent or `prefix.*` (or `*` default). */
  on(intent: string, handler?: IntentHandler): IntentHandler | ((handler: IntentHandler) => IntentHandler) {
    const register = (function_: IntentHandler): IntentHandler => {
      if (intent.endsWith(".*")) this.prefixes.push([intent.slice(0, -1), function_]);
      else if (intent === "*") this.defaultHandler = function_;
      else this.exact.set(intent, function_);
      return function_;
    };
    return handler === undefined ? register : register(handler);
  }

  default(handler: IntentHandler): IntentHandler {
    this.defaultHandler = handler;
    return handler;
  }

  dragSource(key: string, options: { payload?: (item: any) => Record<string, unknown>; kindOf?: (item: any) => string } = {}): DragSource {
    const source = new DragSource(key, options.payload ?? defaultPayloadFor, options.kindOf ?? defaultKindOf);
    this.dragSources.set(key, source);
    return source;
  }

  dropTarget(key: string, intent: string, accepts?: string[]): DropTarget {
    const target = new DropTarget(key, intent, accepts ?? []);
    this.dropTargets.set(key, target);
    return target;
  }

  /** Bind stable node keys to domain items so drops can resolve payload. */
  setCatalog(items: Iterable<any>, keyOf: (item: any) => string): void {
    this.catalog = new Map();
    for (const item of items) this.catalog.set(keyOf(item), item);
  }

  setCatalogMap(items: Record<string, any>): void {
    this.catalog = new Map(Object.entries(items));
  }

  addBinding(binding: any): void { this.bindings.push(binding); }

  hasIntent(intent: string): boolean {
    if (this.exact.has(intent) || this.defaultHandler) return true;
    return this.prefixes.some(([prefix]) => intent.startsWith(prefix));
  }

  handlerFor(intent: string): IntentHandler {
    const exact = this.exact.get(intent);
    if (exact) return exact;
    for (const [prefix, handler] of this.prefixes) if (intent.startsWith(prefix)) return handler;
    if (this.defaultHandler) return this.defaultHandler;
    throw new UnsupportedIntentError(intent);
  }

  /**
   * Route one semantic or drop event to its handler. Accepts an IntentEvent,
   * a DropEvent, or a raw host inbound envelope. Returns the handler result
   * (a promise when the handler is async). Throws UnsupportedIntentError,
   * UnknownTargetError, or DropRejectedError for the three outcomes.
   */
  async dispatch(event: IntentEvent | DropEvent | Record<string, unknown>): Promise<unknown> {
    const resolved = event instanceof IntentEvent || event instanceof DropEvent ? event : this.resolveInbound(event as Record<string, unknown>);
    const intent = resolved instanceof DropEvent ? resolved.intent ?? "" : resolved.intent;
    const handler = this.handlerFor(intent);
    const result = handler(resolved);
    return result instanceof Promise ? await result : result;
  }

  /** Turn a raw host inbound envelope into a typed SDK event. */
  resolveInbound(inbound: Record<string, unknown>): IntentEvent | DropEvent {
    const kind = inbound.kind;
    const event = (inbound.event ?? {}) as Record<string, any>;
    if (kind === "semantic_intent") return IntentEvent.fromInbound(event);
    if (kind === "drag_drop") {
      const wire = (event.payload ?? {}) as Record<string, unknown>;
      const sourceKey = String(wire.source_key ?? "");
      const targetKey = String(wire.target_key ?? "");
      const target = this.dropTargets.get(targetKey);
      if (!target) throw new UnknownTargetError(targetKey, "drop");
      let payload: Record<string, unknown>;
      let kind2: string;
      const source = this.dragSources.get(sourceKey);
      if (source) {
        const item = this.catalog.get(sourceKey);
        payload = item !== undefined ? source.payload(item) : {};
        kind2 = String(payload.kind ?? source.kind(item));
      } else {
        const binding = this.bindings.find((candidate) => candidate.keyForNode(sourceKey) !== null);
        if (!binding) throw new UnknownTargetError(sourceKey, "drag");
        const itemKey = binding.keyForNode(sourceKey) as string;
        const item = binding.source.get(itemKey);
        const [, payloadFor, kindFor] = binding.dragSourceSpec();
        payload = payloadFor(item);
        kind2 = String(payload.kind ?? kindFor(item));
      }
      if (!target.acceptsKind(kind2)) {
        throw new DropRejectedError(`drop target '${targetKey}' does not accept kind '${kind2}'`, {
          sourceKey,
          targetKey,
          accepted: target.accepts,
        });
      }
      // The runtime enforces drop_record.intent == event.intent, so the
      // target's declared intent is authoritative when the envelope is terse.
      return DropEvent.fromInbound({ ...event, intent: event.intent ?? target.intent }, payload);
    }
    throw new UnsupportedIntentError(`<unknown inbound kind: ${String(kind)}>`);
  }

  get intents(): string[] { return [...this.exact.keys()].sort(); }

  get dropIntents(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const [key, target] of this.dropTargets) map[key] = target.intent;
    return map;
  }
}
