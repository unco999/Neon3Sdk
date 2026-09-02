/**
 * Schema-driven collection/grid bindings (Stage 006).
 *
 * Binds a keyed `CollectionStore` to an NUI template or data grid so
 * arbitrary collections stop hand-rolling node updates. Nothing
 * domain-specific lives here. Mirrors `neon3_sdk/components.py`.
 *
 * - Stable identity: `<binding node key>:<stable item key>`; index is never
 *   identity.
 * - Minimal publication via `cellsOf` adapter (Stage 004 reconciliation).
 * - Windowed paging gated on `ui.data_grid.window.v1`; list fallback keeps the
 *   binding usable while paging throws, reject fallback throws at bind time.
 * - Presentation states empty/loading/error derived from source + flags.
 */

import { CapabilitySet } from "./capabilities.js";
import { CapabilityError } from "./errors.js";
import { CollectionStore, GridCell } from "./store.js";

export const DATA_GRID_WINDOW_CAPABILITY = "ui.data_grid.window.v1";

export type ColumnMapper = (item: any) => Record<string, GridCell>;

function readFlag(store: unknown): boolean {
  if (store === null || store === undefined) return false;
  let value: unknown = store;
  if (typeof value === "function") value = (value as () => unknown)();
  if (value && typeof (value as any).get === "function") value = (value as any).get();
  if (value && typeof value === "object" && "value" in (value as object)) value = (value as Record<string, unknown>).value;
  return Boolean(value);
}

export interface DragSpecSpec {
  intent: string;
  payloadFor?: (item: any) => Record<string, unknown>;
}

export class DragSpec {
  readonly intent: string;
  private readonly payloadFor?: (item: any) => Record<string, unknown>;
  constructor(intentOrOptions: string | DragSpecSpec, payloadFor?: (item: any) => Record<string, unknown>) {
    if (typeof intentOrOptions === "string") {
      this.intent = intentOrOptions;
      this.payloadFor = payloadFor;
    } else {
      this.intent = intentOrOptions.intent;
      this.payloadFor = intentOrOptions.payloadFor;
    }
  }
  payload(item: any, key: string, nodeKey: string): Record<string, unknown> {
    const base = this.payloadFor ? this.payloadFor(item) : { item_key: key, kind: nodeKey };
    return { ...base, source_node_key: `${nodeKey}:${key}`, intent: this.intent };
  }
}

export class DropSpec {
  readonly intent: string;
  readonly accepts: string[];
  constructor(intent: string, accepts: string[] = []) {
    this.intent = intent;
    this.accepts = accepts;
  }
}

export interface BindingPage {
  first_row: number;
  rows: Array<{ stable_row_key: string; cells: Record<string, GridCell> }>;
  list_revision: number;
  total_rows: number;
}

export interface CollectionBindingOptions {
  columns: ColumnMapper;
  itemTemplate?: string | null;
  keyOf?: (item: any) => string;
  selection?: unknown;
  drag?: DragSpec | null;
  drop?: DropSpec | null;
  windowed?: boolean;
  loading?: unknown;
  error?: unknown;
}

export class CollectionBinding {
  readonly nodeKey: string;
  readonly source: CollectionStore;
  readonly columns: ColumnMapper;
  readonly itemTemplate: string | null;
  readonly selection: unknown;
  readonly drag: DragSpec | null;
  readonly drop: DropSpec | null;
  windowed: boolean;
  readonly loading: unknown;
  readonly error: unknown;

  constructor(nodeKey: string, source: CollectionStore, options: CollectionBindingOptions) {
    if (!nodeKey) throw new Error("binding node_key must be non-empty");
    this.nodeKey = nodeKey;
    this.source = source;
    this.columns = options.columns;
    this.itemTemplate = options.itemTemplate ?? null;
    this.selection = options.selection;
    this.drag = options.drag ?? null;
    this.drop = options.drop ?? null;
    this.windowed = options.windowed ?? true;
    this.loading = options.loading;
    this.error = options.error;
    if (options.keyOf) source.setKeyOf(options.keyOf);
  }

  itemKey(item: any): string { return this.source.keyOf(item); }

  /** Fixed rule: binding node key + stable business key, never array index. */
  stableNodeKey(item: any): string { return `${this.nodeKey}:${this.itemKey(item)}`; }

  keyForNode(nodeKey: string): string | null {
    const prefix = `${this.nodeKey}:`;
    return nodeKey.startsWith(prefix) ? nodeKey.slice(prefix.length) : null;
  }

  selectedKey(): string | null {
    if (this.selection === null || this.selection === undefined) return null;
    let value: unknown = this.selection;
    if (typeof (value as any).get === "function") value = (value as any).get();
    if (value && typeof value === "object" && "value" in (value as object)) value = (value as Record<string, unknown>).value;
    return (value as string) ?? null;
  }

  /** Adapter for `ObservableStore.buildPublication({ cellsOf })`. */
  cellsOf() {
    return (_collection: CollectionStore, item: any) => this.columns(item);
  }

  buildRow(item: any): { stable_row_key: string; cells: Record<string, GridCell> } {
    return { stable_row_key: this.itemKey(item), cells: this.columns(item) };
  }

  presentationState(): "empty" | "loading" | "error" | "ready" {
    if (readFlag(this.error)) return "error";
    if (readFlag(this.loading)) return "loading";
    return this.source.length === 0 ? "empty" : "ready";
  }

  /** Resolve a renderer window request deterministically. */
  page(firstRow: number, maxRows: number): BindingPage {
    if (!this.windowed) throw new CapabilityError([DATA_GRID_WINDOW_CAPABILITY]);
    if (firstRow < 0 || maxRows <= 0) throw new Error("first_row must be >= 0 and maxRows > 0");
    const items = this.source.items.slice(firstRow, firstRow + maxRows);
    return {
      first_row: firstRow,
      rows: items.map((item: any) => this.buildRow(item)),
      list_revision: this.source.listRevision,
      total_rows: this.source.length,
    };
  }

  dragSourceSpec(routerSourceKey?: string): [string, (item: any) => Record<string, unknown>, (item: any) => string] {
    const payload = (item: any): Record<string, unknown> =>
      this.drag ? this.drag.payload(item, this.itemKey(item), this.nodeKey) : { item_key: this.itemKey(item), kind: this.nodeKey };
    const kindOf = (item: any): string => String(payload(item).kind ?? this.nodeKey);
    return [routerSourceKey ?? this.nodeKey, payload, kindOf];
  }

  dropTargetSpec(): [string, string, string[]] | null {
    if (!this.drop) return null;
    return [this.nodeKey, this.drop.intent, this.drop.accepts];
  }
}

export class CollectionBinder {
  readonly capabilities: CapabilitySet;
  readonly fallback: "list" | "reject";

  constructor(capabilities: CapabilitySet, options: { fallback?: "list" | "reject" } = {}) {
    const fallback = options.fallback ?? "list";
    if (fallback !== "list" && fallback !== "reject") throw new Error('fallback must be "list" or "reject"');
    this.capabilities = capabilities;
    this.fallback = fallback;
  }

  get windowed(): boolean { return this.capabilities.has(DATA_GRID_WINDOW_CAPABILITY); }

  bind(nodeKey: string, source: CollectionStore, options: Omit<CollectionBindingOptions, "windowed">): CollectionBinding {
    const windowed = this.windowed;
    if (!windowed && this.fallback === "reject") throw new CapabilityError([DATA_GRID_WINDOW_CAPABILITY]);
    return new CollectionBinding(nodeKey, source, { ...options, windowed });
  }
}
