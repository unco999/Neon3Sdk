/**
 * Typed observable store and UI publication building (Stage 004).
 *
 * Generic domain-state layer only: keyed collections, typed scalars and
 * selections with diff tracking, transactions, and canonical
 * `UiHostPublication` construction. Mirrors `neon3_sdk/store.py`; the
 * cross-language store wire digest is asserted identically in both suites.
 *
 * Business code mutates inside a transaction, builds one publication per
 * operation, and calls `markApplied` on runtime acceptance. A rejection leaves
 * local confirm state untouched.
 */

import { InvalidPublicationError } from "./errors.js";
import { InputValue } from "./protocol.js";

const VALUE_KINDS = new Set([
  "bool", "i32", "u32", "f32", "vec2", "vec4", "color", "enum", "text_handle", "asset_handle",
]);

/** Coerce a JS value into a canonical `UiInputValue` envelope. */
export function typedValue(value: unknown): InputValue {
  if (value !== null && typeof value === "object" && !Array.isArray(value) && VALUE_KINDS.has(String((value as Record<string, unknown>).kind))) {
    const { kind, ...rest } = value as Record<string, unknown>;
    return { kind, ...rest } as InputValue;
  }
  if (typeof value === "boolean") return { kind: "bool", value };
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new InvalidPublicationError("non-finite numbers are not representable");
    if (Number.isInteger(value)) {
      if (value >= -2147483648 && value < 2147483648) return { kind: "i32", value };
      if (value >= 0 && value < 4294967296) return { kind: "u32", value };
      throw new InvalidPublicationError(`integer out of wire range: ${value}`);
    }
    return { kind: "f32", value };
  }
  if (typeof value === "string") {
    if (!value.trim()) throw new InvalidPublicationError("enum values must be non-empty strings");
    return { kind: "enum", value };
  }
  if (Array.isArray(value) && (value.length === 2 || value.length === 4) && value.every((component) => typeof component === "number")) {
    return { kind: value.length === 2 ? "vec2" : "vec4", value: value.map((component) => Number(component)) };
  }
  throw new InvalidPublicationError(`value type is outside the wire vocabulary: ${typeof value}`);
}

export interface GridCell {
  value: unknown;
  display: { id: number; generation: number };
  presentation_override?: Record<string, unknown> | null;
}

export type CellsOf = (collection: CollectionStore, item: any) => Record<string, GridCell>;

export class ScalarStore {
  private valueWire: InputValue | null = null;
  private dirty = false;
  constructor(readonly key: string, private readonly owner?: ObservableStore) {}

  get current(): InputValue | null { return this.valueWire; }

  get(): InputValue | null { return this.valueWire; }

  set(value: unknown): void {
    const coerced = typedValue(value);
    if (JSON.stringify(coerced) === JSON.stringify(this.valueWire)) return;
    this.valueWire = coerced;
    this.dirty = true;
    this.owner?.touchScalar(this.key);
  }

  isDirty(): boolean { return this.dirty; }

  markApplied(): void { this.dirty = false; }

  toWire(): unknown { return this.valueWire; }
}

export class CollectionStore {
  private itemsList: any[] = [];
  keyOf: (item: any) => string = (item) => (item && typeof item === "object" && "key" in item ? String(item.key) : String(item));
  private dirtyKeys = new Set<string>();
  structureDirty = false;
  listRevision = 0;
  windowRows: number | null = null;

  constructor(readonly name: string, private readonly owner?: ObservableStore) {}

  get items(): any[] { return [...this.itemsList]; }

  keys(): string[] { return this.itemsList.map((item) => this.keyOf(item)); }

  indexOf(key: string): number {
    const index = this.itemsList.findIndex((item) => this.keyOf(item) === key);
    if (index < 0) throw new Error(`KeyError: ${key}`);
    return index;
  }

  get(key: string): any { return this.itemsList[this.indexOf(key)]; }

  get length(): number { return this.itemsList.length; }

  setKeyOf(keyOf: (item: any) => string): void { this.keyOf = keyOf; }

  private bump(structure: boolean, ...keys: string[]): void {
    this.listRevision += 1;
    if (structure) this.structureDirty = true;
    for (const key of keys) this.dirtyKeys.add(key);
    this.owner?.touchCollection(this.name);
  }

  add(key: string, item?: any, options: { index?: number } = {}): void {
    if (this.itemsList.some((existing) => this.keyOf(existing) === key)) throw new Error(`duplicate collection key: ${key}`);
    const payload = item ?? { key };
    if (this.keyOf(payload) !== key) throw new Error("item key must match the add() key");
    if (options.index === undefined) this.itemsList.push(payload);
    else this.itemsList.splice(options.index, 0, payload);
    this.bump(true, key);
  }

  remove(key: string): any {
    const index = this.indexOf(key);
    const [removed] = this.itemsList.splice(index, 1);
    this.bump(true, key);
    return removed;
  }

  update(key: string, item: any): void {
    const index = this.indexOf(key);
    if (this.keyOf(item) !== key) throw new Error("update must preserve the stable key");
    this.itemsList[index] = item;
    this.bump(false, key);
  }

  move(key: string, targetIndex: number): void {
    if (targetIndex < 0 || targetIndex >= this.itemsList.length) throw new RangeError(`target_index ${targetIndex} out of range`);
    const index = this.indexOf(key);
    if (index === targetIndex) return;
    const [moved] = this.itemsList.splice(index, 1);
    this.itemsList.splice(targetIndex, 0, moved);
    this.bump(true, key);
  }

  replace(items: any[]): void {
    const previousByKey = new Map(this.itemsList.map((item) => [this.keyOf(item), item]));
    const nextByKey = new Map(items.map((item) => [this.keyOf(item), item]));
    if (nextByKey.size !== items.length) throw new Error("replacement list contains duplicate keys");
    const previousOrder = [...previousByKey.keys()];
    const nextOrder = [...nextByKey.keys()];
    const orderChanged = JSON.stringify(previousOrder) !== JSON.stringify(nextOrder);
    const membershipChanged = previousByKey.size !== nextByKey.size || previousOrder.some((key, index) => nextOrder[index] !== key);
    const changed = new Set<string>();
    for (const key of previousByKey.keys()) if (!nextByKey.has(key)) changed.add(key);
    for (const key of nextByKey.keys()) if (!previousByKey.has(key)) changed.add(key);
    for (const [key, next] of nextByKey) {
      if (previousByKey.has(key) && JSON.stringify(previousByKey.get(key)) !== JSON.stringify(next)) changed.add(key);
    }
    this.itemsList = [...items];
    this.listRevision += 1;
    for (const key of changed) this.dirtyKeys.add(key);
    if (orderChanged || membershipChanged) this.structureDirty = true;
    this.owner?.touchCollection(this.name);
  }

  dirtyKeysList(): string[] { return [...this.dirtyKeys].sort(); }

  hasPendingChanges(): boolean { return this.dirtyKeys.size > 0 || this.structureDirty; }

  markApplied(): void { this.dirtyKeys.clear(); this.structureDirty = false; }

  window(rows?: number | null): any[] {
    const cap = rows === undefined ? this.windowRows : rows;
    return cap === null || cap === undefined ? this.items : this.items.slice(0, cap);
  }

  toWire(): Record<string, unknown> {
    return { name: this.name, list_revision: this.listRevision, items: [...this.itemsList] };
  }
}

export class SelectionStore {
  private selected: string | null = null;
  private dirty = false;
  selectionRevision = 0;
  constructor(readonly name: string, private readonly owner?: ObservableStore) {}

  get current(): string | null { return this.selected; }

  get(): string | null { return this.selected; }

  set(key: string | null): void {
    if (key === this.selected) return;
    this.selected = key;
    this.dirty = true;
    this.selectionRevision += 1;
    this.owner?.touchSelection(this.name);
  }

  isDirty(): boolean { return this.dirty; }

  markApplied(): void { this.dirty = false; }
}

export interface PublicationProgramRevision {
  program_id: string;
  revision: number;
  schema_version: number;
  capabilities: unknown[];
}

export interface UiPublication {
  scalar_frame: {
    program_revision: PublicationProgramRevision;
    expected_input_revision: number;
    request_id: string;
    idempotency_key: string;
    changes: Array<{ key: string; value: InputValue }>;
  };
  grid_inputs: Array<Record<string, unknown>>;
  presentation_update: null;
}

export class ObservableStore {
  readonly domainRevision = { value: 0 };
  private readonly scalars = new Map<string, ScalarStore>();
  private readonly collections = new Map<string, CollectionStore>();
  private readonly selections = new Map<string, SelectionStore>();
  private readonly dirtyScalars = new Set<string>();
  private readonly dirtyCollections = new Set<string>();
  private readonly dirtySelections = new Set<string>();
  private transactionDepth = 0;

  constructor(initial?: Record<string, unknown>) {
    for (const [key, value] of Object.entries(initial ?? {})) {
      if (Array.isArray(value)) {
        const collection = this.collection(key);
        collection.replace(value);
        collection.markApplied();
      } else {
        const scalar = this.value(key);
        if (value !== null && value !== undefined) scalar.set(value);
        scalar.markApplied();
      }
    }
  }

  get domain_revision(): number { return this.domainRevision.value; }

  value(key: string): ScalarStore {
    let store = this.scalars.get(key);
    if (!store) { store = new ScalarStore(key, this); this.scalars.set(key, store); }
    return store;
  }

  collection(name: string): CollectionStore {
    let store = this.collections.get(name);
    if (!store) { store = new CollectionStore(name, this); this.collections.set(name, store); }
    return store;
  }

  selection(name: string): SelectionStore {
    let store = this.selections.get(name);
    if (!store) { store = new SelectionStore(name, this); this.selections.set(name, store); }
    return store;
  }

  /** @internal */ touchScalar(key: string): void { this.dirtyScalars.add(key); }
  /** @internal */ touchCollection(name: string): void { this.dirtyCollections.add(name); }
  /** @internal */ touchSelection(name: string): void { this.dirtySelections.add(name); }

  /**
   * Group mutations so one business operation yields one publication. On a
   * throw, scalar/selection values, collection contents and diff sets revert
   * to their pre-transaction state and slots created during the transaction
   * are removed, so no half publication escapes.
   */
  async transaction<T>(body: (store: ObservableStore) => T | Promise<T>): Promise<T> {
    const scalars = new Map([...this.scalars].map(([name, store]) => [name, { value: store.current, dirty: store.isDirty() }]));
    const selections = new Map([...this.selections].map(([name, store]) => [name, { key: store.current, dirty: store.isDirty(), revision: store.selectionRevision }]));
    const collections = new Map([...this.collections].map(([name, store]) => [name, {
      items: store.items, listRevision: store.listRevision, dirtyKeys: new Set(store.dirtyKeysList()), structureDirty: store.structureDirty,
    }]));
    const dirty = { scalars: new Set(this.dirtyScalars), collections: new Set(this.dirtyCollections), selections: new Set(this.dirtySelections) };
    this.transactionDepth += 1;
    try {
      const result = await body(this);
      this.transactionDepth -= 1;
      return result;
    } catch (error) {
      this.transactionDepth -= 1;
      for (const name of [...this.scalars.keys()]) {
        const snapshot = scalars.get(name);
        if (!snapshot) this.scalars.delete(name);
        else { const store = this.scalars.get(name)!; (store as any).valueWire = snapshot.value; (store as any).dirty = snapshot.dirty; }
      }
      for (const name of [...this.selections.keys()]) {
        const snapshot = selections.get(name);
        if (!snapshot) this.selections.delete(name);
        else { const store = this.selections.get(name)!; (store as any).selected = snapshot.key; (store as any).dirty = snapshot.dirty; store.selectionRevision = snapshot.revision; }
      }
      for (const name of [...this.collections.keys()]) {
        const snapshot = collections.get(name);
        if (!snapshot) this.collections.delete(name);
        else {
          const store = this.collections.get(name)!;
          (store as any).itemsList = snapshot.items;
          store.listRevision = snapshot.listRevision;
          (store as any).dirtyKeys = snapshot.dirtyKeys;
          store.structureDirty = snapshot.structureDirty;
        }
      }
      this.dirtyScalars.clear(); for (const name of dirty.scalars) this.dirtyScalars.add(name);
      this.dirtyCollections.clear(); for (const name of dirty.collections) this.dirtyCollections.add(name);
      this.dirtySelections.clear(); for (const name of dirty.selections) this.dirtySelections.add(name);
      throw error;
    }
  }

  changedScalars(): Array<{ key: string; value: InputValue }> {
    return [...this.dirtyScalars].sort().map((name) => ({ name, store: this.scalars.get(name)! }))
      .filter(({ store }) => store.isDirty() && store.current !== null)
      .map(({ name, store }) => ({ key: name, value: store.current as InputValue }));
  }

  changedCollections(): CollectionStore[] {
    return [...this.dirtyCollections].sort().map((name) => this.collections.get(name)!).filter((store) => store.hasPendingChanges());
  }

  changedSelections(): string[] {
    return [...this.dirtySelections].sort().filter((name) => this.selections.get(name)!.isDirty());
  }

  hasPendingChanges(): boolean {
    return [...this.scalars.values()].some((store) => store.isDirty())
      || [...this.selections.values()].some((store) => store.isDirty())
      || [...this.collections.values()].some((store) => store.hasPendingChanges());
  }

  /**
   * Produce one canonical `UiHostPublication` covering all pending diffs.
   * Structural-aware grid reconciliation: scalar-only updates publish exactly
   * the dirty rows; add/remove/move/replace that change order or membership
   * publish the bounded current window. `first_row` stays 0 until Stage 006
   * paging against `ui.data_grid.window.v1`.
   */
  buildPublication(
    programRevision: PublicationProgramRevision,
    expectedInputRevision: number,
    requestId: string,
    options: { cellsOf?: CellsOf; windowRows?: number | null; selectionSlots?: Record<string, string> } = {},
  ): UiPublication {
    const changes = this.changedScalars();
    for (const name of this.changedSelections()) {
      const slot = options.selectionSlots?.[name];
      const selected = this.selections.get(name)?.get();
      if (slot && selected !== null && selected !== undefined) changes.push({ key: slot, value: { kind: "enum", value: selected } });
    }
    changes.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
    const gridInputs: Array<Record<string, unknown>> = [];
    if (options.cellsOf) {
      for (const collection of this.changedCollections()) {
        let sourceRows: any[];
        if (collection.structureDirty) {
          sourceRows = collection.window(options.windowRows);
        } else {
          const capped = collection.items.filter((entry) => collection.dirtyKeysList().includes(collection.keyOf(entry)));
          sourceRows = options.windowRows !== undefined && options.windowRows !== null ? capped.slice(0, options.windowRows) : capped;
        }
        const windowRows = sourceRows.map((entry) => {
          const cells: Record<string, Record<string, unknown>> = {};
          for (const column of Object.keys(options.cellsOf!(collection, entry)).sort()) {
            const cell = options.cellsOf!(collection, entry)[column];
            const value = typeof (cell.value as any)?.kind === "string" && VALUE_KINDS.has((cell.value as any).kind) ? cell.value : typedValue(cell.value);
            const built: Record<string, unknown> = { value, display: cell.display };
            if (cell.presentation_override !== undefined && cell.presentation_override !== null) built.presentation_override = cell.presentation_override;
            cells[column] = built;
          }
          return { stable_row_key: collection.keyOf(entry), cells };
        });
        gridInputs.push({
          source_key: collection.name,
          frame: {
            list_revision: collection.listRevision,
            total_rows: collection.length,
            first_row: 0,
            window_rows: windowRows,
            expected_program_revision: programRevision,
          },
        });
      }
    }
    return {
      scalar_frame: {
        program_revision: programRevision,
        expected_input_revision: expectedInputRevision,
        request_id: requestId,
        idempotency_key: `publication:${requestId}`,
        changes,
      },
      grid_inputs: gridInputs,
      presentation_update: null,
    };
  }

  markApplied(): void {
    for (const name of this.dirtyScalars) this.scalars.get(name)?.markApplied();
    for (const name of this.dirtyCollections) this.collections.get(name)?.markApplied();
    for (const name of this.dirtySelections) this.selections.get(name)?.markApplied();
    this.dirtyScalars.clear();
    this.dirtyCollections.clear();
    this.dirtySelections.clear();
    this.domainRevision.value += 1;
  }

  /** Rejection path: pending diffs stay dirty so a rebuild can retry. */
  rejectPending(): void { /* deliberate no-op for API symmetry */ }

  toWire(): Record<string, unknown> {
    const scalars: Record<string, unknown> = {}; for (const [name, store] of [...this.scalars].sort()) scalars[name] = store.toWire();
    const collections: Record<string, unknown> = {}; for (const [name, store] of [...this.collections].sort()) collections[name] = store.toWire();
    const selections: Record<string, unknown> = {}; for (const [name, store] of [...this.selections].sort()) selections[name] = store.get();
    return { domain_revision: this.domainRevision.value, scalars, collections, selections };
  }

  static fromWire(value: Record<string, any>): ObservableStore {
    const store = new ObservableStore();
    store.domainRevision.value = value.domain_revision;
    for (const [name, raw] of Object.entries((value.scalars ?? {}) as Record<string, unknown>)) {
      (store.value(name) as any).valueWire = raw;
    }
    for (const [name, raw] of Object.entries((value.collections ?? {}) as Record<string, any>)) {
      const collection = store.collection(name);
      collection.listRevision = raw.list_revision;
      (collection as any).itemsList = [...raw.items];
    }
    for (const [name, key] of Object.entries((value.selections ?? {}) as Record<string, unknown>)) {
      (store.selection(name) as any).selected = key ?? null;
    }
    return store;
  }
}
