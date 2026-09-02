import { NeonClient } from "./client.js";
import { RemoteError } from "./errors.js";
import { PointerEvent, PointerEventWire } from "./render.js";

export interface KeyEvent {
  key: string;
  action: "down" | "up";
  modifiers?: string[];
  repeat?: boolean;
}

export function keyEventToWire(event: KeyEvent): Record<string, unknown> {
  if (event.action !== "down" && event.action !== "up") throw new Error("keyboard action must be down or up");
  return { key: event.key, action: event.action, modifiers: event.modifiers ?? [], repeat: event.repeat ?? false };
}

export class InputClient {
  constructor(readonly client: NeonClient, readonly target = "wgpu-runtime") {}

  async pointer(event: PointerEvent | PointerEventWire): Promise<unknown> {
    const wire = event instanceof PointerEvent ? event.toWire() : event;
    return (await this.client.call(this.target, "ui.host.pointer_event", { event: wire })).result;
  }

  async keyboard(event: KeyEvent): Promise<unknown> {
    const description = await this.client.describe(this.target);
    if (!description.capabilities.includes("wgpu.ui.keyboard.v1")) {
      throw new RemoteError("keyboard-capability", "rejected", { code: "keyboard_capability_unavailable", message: "runtime does not advertise wgpu.ui.keyboard.v1" });
    }
    return (await this.client.call(this.target, "ui.host.keyboard_event", { event: keyEventToWire(event) })).result;
  }

  async debugSnapshot(): Promise<unknown> {
    return (await this.client.call(this.target, "debug.window.input.snapshot")).result;
  }
}
