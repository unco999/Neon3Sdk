import net from "node:net";
import { EVENT_PROTOCOL, EventEnvelope, PROTOCOL_VERSION } from "./protocol.js";

export interface EventFilter {
  name?: string;
  name_prefix?: string;
  publisher_kinds?: string[];
}

export class EventSubscription {
  constructor(private readonly socket: net.Socket, private readonly reader: FrameReader, readonly filters: EventFilter[]) {}

  async recv(): Promise<EventEnvelope> {
    const value = await this.reader.next();
    if (value.kind !== "delivery") throw new Error(`expected event delivery, got ${String(value.kind)}`);
    return value.event as EventEnvelope;
  }

  async nextFileDrop(imagesOnly = true): Promise<EventEnvelope> {
    for (;;) {
      const event = await this.recv();
      if (event.name !== "ui.file_drop.accepted") continue;
      const payload = event.payload as { is_image?: boolean };
      if (imagesOnly && !payload.is_image) continue;
      return event;
    }
  }

  close(): void { this.socket.destroy(); }
}

export class EventClient {
  constructor(readonly endpoint: string, readonly options: { origin?: string; kind?: string; instanceId?: string; timeoutMs?: number } = {}) {}

  async subscribe(filter: EventFilter): Promise<EventSubscription> {
    if (!filter.name && !filter.name_prefix) throw new TypeError("name or name_prefix is required");
    const socket = await connect(this.endpoint, this.options.timeoutMs ?? 10000);
    const instanceId = this.options.instanceId ?? "neon3-event-client";
    await writeFrame(socket, {
      kind: "subscribe", protocol: EVENT_PROTOCOL, version: PROTOCOL_VERSION,
      request_id: `neon3-event-subscribe-${instanceId}`,
      client: { kind: this.options.kind ?? "external_host", instance_id: instanceId, pid: process.pid, origin: this.options.origin ?? "neon3-node-sdk" },
      filters: [filter], replay_from_sequence: null, max_rate_hz: null,
    });
    const reader = new FrameReader(socket);
    const ack = await reader.next();
    if (ack.kind !== "ack" || ack.status !== "accepted") { socket.destroy(); throw new Error(`event subscription rejected: ${JSON.stringify(ack)}`); }
    return new EventSubscription(socket, reader, [filter]);
  }
}

function connect(endpoint: string, timeoutMs: number): Promise<net.Socket> {
  const match = endpoint.match(/^([^:]+):(\d+)$/);
  if (!match || (!match[1].startsWith("127.") && match[1] !== "localhost")) throw new TypeError("endpoint must be loopback host:port");
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host: match[1], port: Number(match[2]) });
    const timer = setTimeout(() => { socket.destroy(); reject(new Error("event timeout")); }, timeoutMs);
    socket.once("connect", () => { clearTimeout(timer); resolve(socket); });
    socket.once("error", error => { clearTimeout(timer); reject(error); });
  });
}

function writeFrame(socket: net.Socket, value: unknown): Promise<void> {
  const payload = Buffer.from(JSON.stringify(value));
  return new Promise((resolve, reject) => socket.write(Buffer.concat([u32(payload.length), payload]), error => error ? reject(error) : resolve()));
}

class FrameReader {
  private buffer = Buffer.alloc(0);
  private waiters: Array<{ resolve: (value: any) => void; reject: (error: Error) => void }> = [];
  private failure: Error | undefined;

  constructor(private readonly socket: net.Socket) {
    socket.on("data", chunk => { this.buffer = Buffer.concat([this.buffer, chunk]); this.pump(); });
    socket.on("error", error => this.fail(error instanceof Error ? error : new Error(String(error))));
    socket.on("close", () => this.fail(new Error("event connection closed")));
  }

  next(): Promise<any> {
    if (this.failure) return Promise.reject(this.failure);
    const value = this.take();
    if (value !== undefined) return Promise.resolve(value);
    return new Promise((resolve, reject) => this.waiters.push({ resolve, reject }));
  }

  private take(): any | undefined {
    if (this.buffer.length < 4) return undefined;
    const size = this.buffer.readUInt32BE(0);
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
        this.waiters.shift()!.resolve(value);
      } catch (error) { this.fail(error instanceof Error ? error : new Error(String(error))); return; }
    }
  }

  private fail(error: Error): void {
    if (this.failure) return;
    this.failure = error;
    for (const waiter of this.waiters.splice(0)) waiter.reject(error);
  }
}

function u32(value: number): Buffer { const result = Buffer.allocUnsafe(4); result.writeUInt32BE(value); return result; }
