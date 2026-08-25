import { readFile } from "node:fs/promises";
import { NeonClient } from "./client.js";

export interface UiProgram { surface_id: string; program_revision: Record<string, unknown>; input_schema: Record<string, unknown>; }

export class UiClient {
  constructor(readonly client: NeonClient, readonly target = "ui-runtime") {}
  async submitFlow(source: string): Promise<UiProgram> {
    const result = (await this.client.call<UiProgram>(this.target, "ui.flow.submit", { source }, { idempotencyKey: `ui-flow:${crypto.randomUUID()}` })).result;
    if (!result) throw new Error("ui.flow.submit returned no program");
    return result;
  }
  async submitFlowFile(path: string): Promise<UiProgram> { return this.submitFlow(await readFile(path, "utf8")); }
  async applyInput(programRevision: Record<string, unknown>, expectedInputRevision: number, changes: unknown[]): Promise<unknown> {
    const requestId = crypto.randomUUID();
    return (await this.client.call(this.target, "ui.input.frame", { program_revision: programRevision, expected_input_revision: expectedInputRevision, request_id: requestId, idempotency_key: `ui-input:${requestId}`, changes }, { requestId, idempotencyKey: `ui-input:${requestId}` })).result;
  }
  async hostInbound(event: unknown): Promise<unknown> { return (await this.client.call(this.target, "ui.host.inbound", event, { idempotencyKey: `ui-host:${crypto.randomUUID()}` })).result; }
  async snapshot(): Promise<unknown> { return (await this.client.call(this.target, "debug.snapshot.get")).result; }
}
