"""Typed public values corresponding to Neon3 protocol schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssetRef:
    project_id: str
    asset_id: int
    revision: int
    kind: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "asset_id": self.asset_id,
            "revision": self.revision,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class ClientIdentity:
    kind: str
    instance_id: str
    pid: int
    origin: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "instance_id": self.instance_id,
            "pid": self.pid,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class RpcResponse:
    request_id: str
    status: str
    revision: int | None
    result: Any | None
    snapshot: Any | None
    error: dict[str, Any] | None

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "RpcResponse":
        required = {"request_id", "status", "revision", "result", "snapshot", "error"}
        unexpected = set(value) - required
        missing = required - set(value)
        if missing or unexpected:
            raise ValueError(f"invalid RpcResponse fields: missing={sorted(missing)}, unexpected={sorted(unexpected)}")
        return cls(**value)


@dataclass(frozen=True)
class ServiceHealth:
    service: str
    status: str
    epoch: int

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ServiceHealth":
        return cls(service=value["service"], status=value["status"], epoch=value["epoch"])


@dataclass(frozen=True)
class ServiceDescription:
    service: str
    protocol_version: dict[str, int]
    endpoint: str
    epoch: int
    capabilities: tuple[str, ...]

    @classmethod
    def from_wire(cls, value: dict[str, Any]) -> "ServiceDescription":
        return cls(
            service=value["service"],
            protocol_version=value["protocol_version"],
            endpoint=value["endpoint"],
            epoch=value["epoch"],
            capabilities=tuple(value["capabilities"]),
        )
