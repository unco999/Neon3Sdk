import net from "node:net";
import { ProtocolError, RemoteError, TransportError } from "./errors.js";
import { parseRpcResponse, PROTOCOL_VERSION, ProtocolShapeError, RPC_PROTOCOL, RpcResponse, ServiceDescription, ServiceHealth } from "./protocol.js";

export interface ClientOptions {
  origin?: string;
  kind?: string;
  instanceId?: string;
  timeoutMs?: number;
  maxFrameSize?: number;
}

const DEFAULT_MAX_FRAME_SIZE = 128 * 1024 * 1024;

function parseEndpoint(endpoint: string): { host: string; port: number } {
  const split = endpoint.match(/^([^:]+):(\d+)$/);
  if (!split) throw new TypeError("endpoint must be host:port");
  const host = split[1];
  const port = Number(split[2]);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new TypeError("endpoint port must be between 1 and 65535");
  if (!host.startsWith("127.") && host !== "localhost" && host !== "::1") throw new TypeError("endpoint must be loopback");
  return { host, port };
}

export class NeonClient {
  readonly host: string;
  readonly port: number;
  readonly options: Required<ClientOptions>;

  constructor(endpoint: string, options: ClientOptions = {}) {
    ({ host: this.host, port: this.port } = parseEndpoint(endpoint));
    const timeoutMs = options.timeoutMs ?? 5000;
    if (!(timeoutMs > 0)) throw new TypeError("timeoutMs must be positive");
    const maxFrameSize = options.maxFrameSize ?? DEFAULT_MAX_FRAME_SIZE;
    if (Number.isInteger(maxFrameSize) && maxFrameSize > 0) {
      // keep
    } else {
      throw new TypeError("maxFrameSize must be a positive integer");
    }
    this.options = {
      origin: options.origin ?? "neon3-node-sdk",
      kind: options.kind ?? "cli",
      instanceId: options.instanceId ?? crypto.randomUUID(),
      timeoutMs,
      maxFrameSize,
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

  async health(target: string): Promise<ServiceHealth> {
    const response = await this.call<ServiceHealth>(target, "service.health");
    if (response.result === null || typeof response.result !== "object") throw new ProtocolError("service.health returned a non-object result");
    return response.result;
  }

  async describe(target: string): Promise<ServiceDescription> {
    const response = await this.call<ServiceDescription>(target, "service.describe");
    if (response.result === null || typeof response.result !== "object") throw new ProtocolError("service.describe returned a non-object result");
    return response.result;
  }

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
        if (expected === undefined && all.length >= 4) {
          expected = all.readUInt32BE(0);
          if (expected > this.options.maxFrameSize) {
            clearTimeout(timer); socket.destroy();
            return reject(new ProtocolError(`frame_too_large: ${expected} exceeds ${this.options.maxFrameSize}`));
          }
        }
        if (expected !== undefined && all.length >= expected + 4) {
          clearTimeout(timer); socket.end();
          try {
            resolve(parseRpcResponse<T>(JSON.parse(all.subarray(4, expected + 4).toString("utf8"))));
          } catch (error) {
            if (error instanceof ProtocolShapeError) reject(new ProtocolError(error.message));
            else reject(new ProtocolError(`invalid_json: ${String(error)}`));
          }
        }
      });
      socket.on("error", (error) => { clearTimeout(timer); reject(new TransportError(error.message)); });
      socket.on("close", () => clearTimeout(timer));
    });
  }
}

function u32(value: number): Buffer { const result = Buffer.allocUnsafe(4); result.writeUInt32BE(value); return result; }
