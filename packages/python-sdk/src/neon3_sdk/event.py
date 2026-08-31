"""Persistent client for the canonical ``neon3.event`` protocol."""

from __future__ import annotations

import json
import socket
import struct
from dataclasses import dataclass
from typing import Any, Iterator

from .client import _parse_loopback_endpoint
from .errors import ProtocolError, TransportError
from .models import ClientIdentity, EventEnvelope, UiFileDropPayload

EVENT_PROTOCOL = "neon3.event"
PROTOCOL_VERSION = {"major": 1, "minor": 0}
MAX_FRAME_SIZE = 64 * 1024


@dataclass(frozen=True)
class EventFilter:
    name: str | None = None
    name_prefix: str | None = None
    publisher_kinds: tuple[str, ...] | None = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "name_prefix": self.name_prefix,
            "publisher_kinds": list(self.publisher_kinds) if self.publisher_kinds else None,
        }


class EventSubscription:
    def __init__(self, stream: socket.socket, reader: "_FrameReader", client: ClientIdentity, filters: list[EventFilter]) -> None:
        self._stream = stream
        self._reader = reader
        self.client = client
        self.filters = filters

    def recv(self) -> EventEnvelope:
        response = self._reader.read()
        if response.get("kind") != "delivery":
            raise ProtocolError(f"expected event delivery, got {response.get('kind')}")
        return EventEnvelope.from_wire(response["event"])

    def file_drops(self, *, images_only: bool = True) -> Iterator[UiFileDropPayload]:
        while True:
            event = self.recv()
            if event.name != "ui.file_drop.accepted":
                continue
            payload = UiFileDropPayload.from_wire(event.payload)
            if images_only and not payload.is_image:
                continue
            yield payload

    def close(self) -> None:
        self._stream.close()

    def __enter__(self) -> "EventSubscription":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()


class EventClient:
    def __init__(self, endpoint: tuple[str, int], identity: ClientIdentity, timeout_seconds: float = 10.0) -> None:
        self.endpoint = endpoint
        self.identity = identity
        self.timeout_seconds = timeout_seconds

    @classmethod
    def connect(
        cls,
        endpoint: str | tuple[str, int],
        *,
        origin: str = "neon3-python-sdk",
        kind: str = "external_host",
        instance_id: str = "neon3-event-client",
        timeout_seconds: float = 10.0,
    ) -> "EventClient":
        parsed = _parse_loopback_endpoint(endpoint)
        return cls(parsed, ClientIdentity(kind, instance_id, 0, origin), timeout_seconds)

    def subscribe(
        self,
        *,
        name: str | None = None,
        name_prefix: str | None = None,
        publisher_kinds: tuple[str, ...] | None = None,
        replay_from_sequence: int | None = None,
        max_rate_hz: int | None = None,
    ) -> EventSubscription:
        if not name and not name_prefix:
            raise ValueError("name or name_prefix is required")
        stream = socket.create_connection(self.endpoint, timeout=self.timeout_seconds)
        stream.settimeout(self.timeout_seconds)
        request_id = f"neon3-event-subscribe-{self.identity.instance_id}"
        _write_frame(stream, {
            "kind": "subscribe",
            "protocol": EVENT_PROTOCOL,
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "client": self.identity.to_wire(),
            "filters": [EventFilter(name, name_prefix, publisher_kinds).to_wire()],
            "replay_from_sequence": replay_from_sequence,
            "max_rate_hz": max_rate_hz,
        })
        reader = _FrameReader(stream)
        ack = reader.read()
        if ack.get("kind") != "ack" or ack.get("status") != "accepted":
            stream.close()
            raise ProtocolError(f"event subscription rejected: {ack}")
        return EventSubscription(stream, reader, self.identity, [EventFilter(name, name_prefix, publisher_kinds)])


def _write_frame(stream: socket.socket, value: dict[str, Any]) -> None:
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(payload) > MAX_FRAME_SIZE:
        raise TransportError("event frame_too_large")
    stream.sendall(struct.pack(">I", len(payload)) + payload)


def _read_frame(stream: socket.socket) -> dict[str, Any]:
    header = _recv_exact(stream, 4)
    size = struct.unpack(">I", header)[0]
    if size > MAX_FRAME_SIZE:
        raise ProtocolError("event frame_too_large")
    try:
        decoded = json.loads(_recv_exact(stream, size).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolError(f"invalid event JSON: {error}") from error
    if not isinstance(decoded, dict):
        raise ProtocolError("event frame must be a JSON object")
    return decoded


class _FrameReader:
    """Length-prefixed reader that preserves multiple frames in one recv."""

    def __init__(self, stream: socket.socket) -> None:
        self.stream = stream
        self.buffer = bytearray()

    def read(self) -> dict[str, Any]:
        while True:
            if len(self.buffer) >= 4:
                size = struct.unpack(">I", self.buffer[:4])[0]
                if size > MAX_FRAME_SIZE:
                    raise ProtocolError("event frame_too_large")
                if len(self.buffer) >= size + 4:
                    payload = bytes(self.buffer[4:size + 4])
                    del self.buffer[:size + 4]
                    try:
                        decoded = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ProtocolError(f"invalid event JSON: {error}") from error
                    if not isinstance(decoded, dict):
                        raise ProtocolError("event frame must be a JSON object")
                    return decoded
            chunk = self.stream.recv(64 * 1024)
            if not chunk:
                raise TransportError("connection_closed")
            self.buffer.extend(chunk)


def _recv_exact(stream: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = stream.recv(remaining)
        if not chunk:
            raise TransportError("connection_closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
