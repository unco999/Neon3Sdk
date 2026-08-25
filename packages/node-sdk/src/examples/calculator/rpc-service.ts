import net from "node:net";
import { CalculatorDomain } from "./domain.js";

export class CalculatorService {
  private server?: net.Server;
  readonly domain = new CalculatorDomain();
  constructor(readonly host = "127.0.0.1", readonly port = 39104) {}

  async start(): Promise<void> {
    this.server = net.createServer((socket) => this.handle(socket));
    await new Promise<void>((resolve, reject) => { this.server!.once("error", reject); this.server!.listen(this.port, this.host, () => resolve()); });
  }

  async stop(): Promise<void> { await new Promise<void>((resolve) => this.server ? this.server.close(() => resolve()) : resolve()); this.server = undefined; }

  private handle(socket: net.Socket): void {
    let buffer = Buffer.alloc(0);
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      if (buffer.length < 4) return;
      const size = buffer.readUInt32BE(0);
      if (buffer.length < size + 4) return;
      const request = JSON.parse(buffer.subarray(4, size + 4).toString("utf8")) as Record<string, any>;
      socket.end(frame(this.dispatch(request)));
    });
  }

  private dispatch(request: Record<string, any>): Record<string, any> {
    const id = request.request_id;
    if (request.method === "service.health") return response(id, "accepted", { service: "calculator-node", status: "healthy", epoch: 1 });
    if (request.method === "service.describe") return response(id, "accepted", { service: "calculator-node", protocol_version: { major: 1, minor: 0 }, endpoint: `${this.host}:${this.port}`, epoch: 1, capabilities: ["calculator.evaluate.v1", "ui.host.publication.v1"] });
    if (request.method === "debug.snapshot.get") return response(id, "accepted", { service: "calculator-node", epoch: 1, revision: this.domain.state.revision, state: this.domain.state });
    if (request.method !== "ui.host.inbound") return response(id, "rejected", undefined, { code: "unsupported_method", message: "method is not supported" });
    try {
      const event = request.params.event;
      const publication = this.domain.apply(event, event.program_revision, event.input_revision);
      return { ...response(id, "accepted", undefined, undefined, event.input_revision + 1), result: publication, snapshot: this.domain.state };
    } catch (error) { return response(id, "rejected", undefined, { code: "calculator_rejected", message: String(error) }); }
  }
}

function response(requestId: string, status: string, result?: unknown, error?: unknown, revision: number | null = null): Record<string, any> { return { request_id: requestId, status, revision, result: result ?? null, snapshot: null, error: error ?? null }; }
function frame(value: unknown): Buffer { const body = Buffer.from(JSON.stringify(value)); const header = Buffer.alloc(4); header.writeUInt32BE(body.length); return Buffer.concat([header, body]); }
