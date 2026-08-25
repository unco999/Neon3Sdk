import net from "node:net";
import { ProtocolError, RemoteError, TransportError } from "./errors.js";
import { PROTOCOL_VERSION, RPC_PROTOCOL, RpcResponse, ServiceDescription, ServiceHealth } from "./protocol.js";

export interface ClientOptions {
  origin?: string;
  kind?: string;
  instanceId?: string;
  timeoutMs?: number;
  maxFrameSize?: number;
}

export class NeonClient {
  readonly host: string;
  readonly port: number;
  readonly options: Required<ClientOptions>;

  constructor(endpoint: string, options: ClientOptions = {}) {
    const split = endpoint.match(/^([^:]+):(\d+)$/);
    if (!split) throw new TypeError("endpoint must be host:port");
    this.host = split[1];
    this.port = Number(split[2]);
    if (!this.host.startsWith("127.") && this.host !== "localhost") throw new TypeError("endpoint must be loopback");
    this.options = {
      origin: options.origin ?? "neon3-node-sdk",
      kind: options.kind ?? "cli",
      instanceId: options.instanceId ?? crypto.randomUUID(),
      timeoutMs: options.timeoutMs ?? 5000,
      maxFrameSize: options.maxFrameSize ?? 128 * 1024 * 1024,
    };
  }

  async call<T = unknown>(target: string, method: string, params: unknown = {}, options: { expectedRevision?: number; idempotencyKey?: string; requestId?: string; raiseForStatus?: boolean } = {}): Promise<RpcResponse<T>> {
    const requestId = options.requestId ?? crypto.randomUUID();
    const request = {
      protocol: RPC_PROTOCOL,
      version: PROTOCOL_VERSION,
      request_id: requestId,
      client: { kind: this.options.kind, instance_id: this.options.instanceId, pid: process.pid, origin: this.options.origin },
      target,
      method,
      params,
      expected_revision: options.expectedRevision ?? null,
      idempotency_key: options.idempotencyKey ?? null,
    };
    const response = await this.exchange<T>(request);
    if (response.request_id !== requestId) throw new ProtocolError(`request_id_mismatch: expected ${requestId}, got ${response.request_id}`);
    if ((options.raiseForStatus ?? true) && response.status !== "accepted") throw new RemoteError(response.request_id, response.status, response.error);
    return response;
  }

  async health(target: string): Promise<ServiceHealth> { return (await this.call<ServiceHealth>(target, "service.health")).result!; }
  async describe(target: string): Promise<ServiceDescription> { return (await this.call<ServiceDescription>(target, "service.describe")).result!; }

  private exchange<T>(request: object): Promise<RpcResponse<T>> {
    return new Promise((resolve, reject) => {
      const payload = Buffer.from(JSON.stringify(request));
      if (payload.length > this.options.maxFrameSize) return reject(new TransportError("frame_too_large"));
      const socket = net.createConnection({ host: this.host, port: this.port });
      const chunks: Buffer[] = [];
      let expected: number | undefined;
      const timer = setTimeout(() => { socket.destroy(); reject(new TransportError("timeout")); }, this.options.timeoutMs);
      socket.on("connect", () => socket.write(Buffer.concat([u32(payload.length), payload])));
      socket.on("data", (chunk: Buffer) => {
        chunks.push(chunk);
        const all = Buffer.concat(chunks);
        if (expected === undefined && all.length >= 4) expected = all.readUInt32BE(0);
        if (expected !== undefined && all.length >= expected + 4) {
          clearTimeout(timer); socket.end();
          try { resolve(JSON.parse(all.subarray(4, expected + 4).toString("utf8")) as RpcResponse<T>); }
          catch (error) { reject(new ProtocolError(`invalid_json: ${String(error)}`)); }
        }
      });
      socket.on("error", (error) => { clearTimeout(timer); reject(new TransportError(error.message)); });
      socket.on("close", () => clearTimeout(timer));
    });
  }
}

function u32(value: number): Buffer { const result = Buffer.allocUnsafe(4); result.writeUInt32BE(value); return result; }
