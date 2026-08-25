"""Stable SDK exception types."""

from __future__ import annotations

from typing import Any


class NeonError(Exception):
    """Base exception for Neon3 SDK failures."""


class TransportError(NeonError):
    """A loopback connection, timeout, or frame transport failure."""


class ProtocolError(NeonError):
    """A peer violated the Neon3 RPC framing or envelope contract."""


class RemoteError(NeonError):
    """A Neon3 service rejected or failed an RPC request."""

    def __init__(self, request_id: str, status: str, error: dict[str, Any] | None) -> None:
        self.request_id = request_id
        self.status = status
        self.error = error or {}
        code = self.error.get("code", "unknown_remote_error")
        message = self.error.get("message", "The service returned no error message.")
        super().__init__(f"{code}: {message} (request_id={request_id}, status={status})")
