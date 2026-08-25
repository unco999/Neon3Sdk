import { NeonClient } from "./client.js";
import { RemoteError } from "./errors.js";

export interface KeyEvent { key: string; action: "down" | "up"; modifiers?: string[]; repeat?: boolean; }
export class InputClient {
  constructor(readonly client: NeonClient, readonly target = "wgpu-runtime") {}
  async pointer(event: unknown): Promise<unknown> { return (await this.client.call(this.target, "ui.host.pointer_event", { event })).result; }
  async keyboard(event: KeyEvent): Promise<unknown> { const description = await this.client.describe(this.target); if (!description.capabilities.includes("wgpu.ui.keyboard.v1")) throw new RemoteError("keyboard-capability", "rejected", { code: "keyboard_capability_unavailable", message: "runtime does not advertise wgpu.ui.keyboard.v1" }); return (await this.client.call(this.target, "ui.host.keyboard_event", { event })).result; }
}
