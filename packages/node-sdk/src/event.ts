import net from "node:net";
import { ProtocolError, TransportError } from "./errors.js";
import { EVENT_PROTOCOL, EventEnvelope, PROTOCOL_VERSION } from "./protocol.js";

export interface EventFilter {
  name?: string;
  name_prefix?: string;
  publisher_kinds?: string[];
}

const MAX_FRAME_SIZE = 64 * 1024;

export class EventSubscription {
  constructor(
    private readonly socket: net.Socket,
    private readonly reader: FrameReader,
    readonly filters: EventFilter[],
    readonly timeoutMs: number,
  ) {}

  async recv(timeoutMs?: number): Promise<EventEnvelope> {
    const value = await this.reader.next(timeoutMs ?? this.timeoutMs);
    if (value.kind !== "delivery") throw new ProtocolError(`expected event delivery, got ${String(value.kind)}`);
    return value.event as EventEnvelope;
  }

  /** Bounded receive: at most `maxEvents`, returning early on aggregate timeout. */
  async receive(maxEvents: number, timeoutMs?: number): Promise<EventEnvelope[]> {
    if (!Number.isInteger(maxEvents) || maxEvents <= 0) throw new TypeError("maxEvents must be a positive integer");
    const events: EventEnvelope[] = [];
    const start = Date.now();
    const budget = timeoutMs ?? this.timeoutMs;
    while (events.length < maxEvents) {
      const remaining = budget - (Date.now() - start);
      if (remaining <= 0) break;
      try {
        events.push(await this.recv(remaining));
      } catch (error) {
        if (error instanceof TransportError && error.message === "event recv timeout") break;
        throw error;
      }
    }
    return events;
  }

  async nextFileDrop(imagesOnly = true, timeoutMs?: number): Promise<EventEnvelope> {
    for (;;) {
      const event = await this.recv(timeoutMs);
      if (event.name !== "ui.file_drop.accepted") continue;
      const payload = event.payload as { is_image?: boolean };
      if (imagesOnly && !payload.is_image) continue;
      return event;
    }
  }

  async *typedEvents(name: string, timeoutMs?: number): AsyncGenerator<EventEnvelope> {
    for (;;) {
      try {
        const event = await this.recv(timeoutMs);
        if (event.name === name) yield event;
      } catch (error) {
        if (error instanceof TransportError && error.message === "event recv timeout") return;
        throw error;
      }
    }
  }

  close(): void { this.socket.destroy(); }
}

export class EventClient {
  constructor(readonly endpoint: string, readonly options: { origin?: string; kind?: string; instanceId?: string; timeoutMs?: number } = {}) {}

  async subscribe(filter: EventFilter): Promise<EventSubscription> {
    if (!filter.name && !filter.name_prefix) throw new TypeError("name or name_prefix is required");
    const timeoutMs = this.options.timeoutMs ?? 10000;
    const socket = await connect(this.endpoint, timeoutMs);
    const instanceId = this.options.instanceId ?? "neon3-event-client";
    await writeFrame(socket, {
      kind: "subscribe", protocol: EVENT_PROTOCOL, version: PROTOCOL_VERSION,
      request_id: `neon3-event-subscribe-${instanceId}`,
      client: { kind: this.options.kind ?? "external_host", instance_id: instanceId, pid: process.pid, origin: this.options.origin ?? "neon3-node-sdk" },
      filters: [filter], replay_from_sequence: null, max_rate_hz: null,
    });
    const reader = new FrameReader(socket);
    const ack = await reader.next(timeoutMs);
    if (ack.kind !== "ack" || ack.status !== "accepted") { socket.destroy(); throw new ProtocolError(`event subscription rejected: ${JSON.stringify(ack)}`); }
    return new EventSubscription(socket, reader, [filter], timeoutMs);
  }
}

function connect(endpoint: string, timeoutMs: number): Promise<net.Socket> {
  const match = endpoint.match(/^([^:]+):(\d+)$/);
  if (!match || (!match[1].startsWith("127.") && match[1] !== "localhost")) throw new TypeError("endpoint must be loopback host:port");
  const port = Number(match[2]);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new TypeError("endpoint port must be between 1 and 65535");
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host: match[1], port });
    const timer = setTimeout(() => { socket.destroy(); reject(new TransportError("event timeout")); }, timeoutMs);
    socket.once("connect", () => { clearTimeout(timer); resolve(socket); });
    socket.once("error", error => { clearTimeout(timer); reject(error); });
  });
}

function writeFrame(socket: net.Socket, value: unknown): Promise<void> {
  const payload = Buffer.from(JSON.stringify(value));
  if (payload.length > MAX_FRAME_SIZE) return Promise.reject(new TransportError("event frame_too_large"));
  return new Promise((resolve, reject) => socket.write(Buffer.concat([u32(payload.length), payload]), error => error ? reject(error) : resolve()));
}

class FrameReader {
  private buffer = Buffer.alloc(0);
  private waiters: Array<{ resolve: (value: any) => void; reject: (error: Error) => void; timer: NodeJS.Timeout | null }> = [];
  private failure: Error | undefined;

  constructor(private readonly socket: net.Socket) {
    socket.on("data", chunk => { this.buffer = Buffer.concat([this.buffer, chunk]); this.pump(); });
    socket.on("error", error => this.fail(error instanceof Error ? error : new Error(String(error))));
    socket.on("close", () => this.fail(new TransportError("event connection closed")));
  }

  next(timeoutMs?: number): Promise<any> {
    if (this.failure) return Promise.reject(this.failure);
    const value = this.take();
    if (value !== undefined) return Promise.resolve(value);
    return new Promise((resolve, reject) => {
      let timer: NodeJS.Timeout | null = null;
      if (timeoutMs !== undefined) {
        timer = setTimeout(() => {
          const index = this.waiters.findIndex(waiter => waiter.resolve === resolve);
          if (index >= 0) this.waiters.splice(index, 1);
          reject(new TransportError("event recv timeout"));
        }, timeoutMs);
      }
      this.waiters.push({ resolve, reject, timer });
    });
  }

  private take(): any | undefined {
    if (this.buffer.length < 4) return undefined;
    const size = this.buffer.readUInt32BE(0);
    if (size > MAX_FRAME_SIZE) throw new ProtocolError("event frame_too_large");
    if (this.buffer.length < size + 4) return undefined;
    const body = this.buffer.subarray(4, size + 4);
    this.buffer = this.buffer.subarray(size + 4);
    return JSON.parse(body.toString("utf8"));
  }

  private pump(): void {
    while (this.waiters.length) {
      try {
        const value = this.take();
        if (value === undefined) return;
        const waiter = this.waiters.shift()!;
        if (waiter.timer) clearTimeout(waiter.timer);
        waiter.resolve(value);
      } catch (error) { this.fail(error instanceof Error ? error : new Error(String(error))); return; }
    }
  }

  private fail(error: Error): void {
    if (this.failure) return;
    this.failure = error;
    for (const waiter of this.waiters.splice(0)) {
      if (waiter.timer) clearTimeout(waiter.timer);
      waiter.reject(error);
    }
  }
}

function u32(value: number): Buffer { const result = Buffer.allocUnsafe(4); result.writeUInt32BE(value); return result; }
