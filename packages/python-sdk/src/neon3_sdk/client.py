"""Synchronous Neon3 RPC client using the canonical loopback framing."""

from __future__ import annotations

import json
import os
import socket
import struct
import uuid
from dataclasses import dataclass
from typing import Any

from .errors import ProtocolError, RemoteError, TransportError
from .models import ClientIdentity, RpcResponse, ServiceDescription, ServiceHealth

RPC_PROTOCOL = "neon3.rpc"
PROTOCOL_VERSION = {"major": 1, "minor": 0}
DEFAULT_MAX_FRAME_SIZE = 128 * 1024 * 1024


@dataclass
class NeonClient:
    """A one-request-per-connection client compatible with ``neon-ipc::RpcClient``."""

    endpoint: tuple[str, int]
    identity: ClientIdentity
    timeout_seconds: float = 5.0
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE

    @classmethod
    def connect(
        cls,
        endpoint: str | tuple[str, int],
        *,
        origin: str = "neon3-python-sdk",
        kind: str = "cli",
        instance_id: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> "NeonClient":
        host, port = _parse_loopback_endpoint(endpoint)
        return cls(
            endpoint=(host, port),
            identity=ClientIdentity(kind, instance_id or str(uuid.uuid4()), os.getpid(), origin),
            timeout_seconds=timeout_seconds,
        )

    def call(
        self,
        target: str,
        method: str,
        params: Any | None = None,
        *,
        expected_revision: int | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
        raise_for_status: bool = True,
    ) -> RpcResponse:
        request_id = request_id or str(uuid.uuid4())
        request = {
            "protocol": RPC_PROTOCOL,
            "version": PROTOCOL_VERSION,
            "request_id": request_id,
            "client": self.identity.to_wire(),
            "target": target,
            "method": method,
            "params": {} if params is None else params,
            "expected_revision": expected_revision,
            "idempotency_key": idempotency_key,
        }
        response = self._exchange(request)
        if response.request_id != request_id:
            raise ProtocolError(f"request_id_mismatch: expected {request_id}, got {response.request_id}")
        if raise_for_status and response.status != "accepted":
            raise RemoteError(response.request_id, response.status, response.error)
        return response

    def health(self, target: str) -> ServiceHealth:
        response = self.call(target, "service.health")
        if not isinstance(response.result, dict):
            raise ProtocolError("service.health returned a non-object result")
        return ServiceHealth.from_wire(response.result)

    def describe(self, target: str) -> ServiceDescription:
        response = self.call(target, "service.describe")
        if not isinstance(response.result, dict):
            raise ProtocolError("service.describe returned a non-object result")
        return ServiceDescription.from_wire(response.result)

    def diagnostics(self, target: str = "wgpu-runtime") -> Any:
        return self.call(target, "wgpu.render.diagnostics").result

    def _exchange(self, request: dict[str, Any]) -> RpcResponse:
        payload = json.dumps(request, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(payload) > self.max_frame_size:
            raise TransportError(f"frame_too_large: {len(payload)} exceeds {self.max_frame_size}")
        try:
            with socket.create_connection(self.endpoint, timeout=self.timeout_seconds) as stream:
                stream.settimeout(self.timeout_seconds)
                stream.sendall(struct.pack(">I", len(payload)) + payload)
                size = struct.unpack(">I", _recv_exact(stream, 4))[0]
                if size > self.max_frame_size:
                    raise ProtocolError(f"frame_too_large: {size} exceeds {self.max_frame_size}")
                decoded = json.loads(_recv_exact(stream, size).decode("utf-8"))
        except (OSError, TimeoutError) as error:
            raise TransportError(f"transport_io: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolError(f"invalid_json: {error}") from error
        if not isinstance(decoded, dict):
            raise ProtocolError("response must be a JSON object")
        try:
            return RpcResponse.from_wire(decoded)
        except (KeyError, TypeError, ValueError) as error:
            raise ProtocolError(str(error)) from error


def _parse_loopback_endpoint(endpoint: str | tuple[str, int]) -> tuple[str, int]:
    if isinstance(endpoint, tuple):
        host, port = endpoint
    else:
        host, separator, port_text = endpoint.rpartition(":")
        if not separator or not host or not port_text.isdigit():
            raise ValueError("endpoint must be host:port")
        port = int(port_text)
    try:
        address = socket.gethostbyname(host)
    except OSError as error:
        raise ValueError(f"endpoint host cannot be resolved: {host}") from error
    if not address.startswith("127.") and address != "::1":
        raise ValueError("endpoint must resolve to loopback")
    if not 0 < port < 65536:
        raise ValueError("endpoint port must be between 1 and 65535")
    return host, port


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
