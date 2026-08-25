"""Input contracts. Pointer injection is available; keyboard requires a negotiated runtime capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import NeonClient
from .errors import RemoteError
from .render import PointerEvent


@dataclass(frozen=True)
class KeyEvent:
    key: str
    action: str
    modifiers: tuple[str, ...] = ()
    repeat: bool = False

    def to_wire(self) -> dict[str, Any]:
        if self.action not in {"down", "up"}:
            raise ValueError("keyboard action must be down or up")
        return {"key": self.key, "action": self.action, "modifiers": list(self.modifiers), "repeat": self.repeat}


class InputClient:
    def __init__(self, client: NeonClient, target: str = "wgpu-runtime") -> None:
        self.client = client
        self.target = target

    def pointer(self, event: PointerEvent) -> Any:
        return self.client.call(self.target, "ui.host.pointer_event", {"event": event.to_wire()}).result

    def keyboard(self, event: KeyEvent) -> Any:
        """Send a typed keyboard event when the runtime advertises that contract."""
        description = self.client.describe(self.target)
        if "wgpu.ui.keyboard.v1" not in description.capabilities:
            raise RemoteError("keyboard-capability", "rejected", {"code": "keyboard_capability_unavailable", "message": "The connected Neon3 runtime does not advertise wgpu.ui.keyboard.v1."})
        return self.client.call(self.target, "ui.host.keyboard_event", {"event": event.to_wire()}).result

    def debug_snapshot(self) -> Any:
        return self.client.call(self.target, "debug.window.input.snapshot").result
