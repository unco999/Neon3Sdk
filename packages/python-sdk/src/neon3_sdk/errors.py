"""Stable SDK exception types with frozen cross-language error codes.

The semantic codes are defined in ``docs/sdk-wire-contract.md`` §6. Both SDKs
must map the same runtime code to the same SDK code; the mapping table lives
in :data:`RUNTIME_CODE_MAP` here and ``errorCodes`` in the Node errors module.
"""

from __future__ import annotations

from typing import Any

# Frozen SDK-level semantic codes (Stage 000).
STALE_REVISION = "stale_revision"
UNKNOWN_TARGET = "unknown_target"
UNSUPPORTED_INTENT = "unsupported_intent"
CAPABILITY_UNAVAILABLE = "capability_unavailable"
DUPLICATE_EVENT = "duplicate_event"
INVALID_PUBLICATION = "invalid_publication"
INVALID_PROGRAM = "invalid_program"

CORE_ERROR_CODES = (
    STALE_REVISION,
    UNKNOWN_TARGET,
    UNSUPPORTED_INTENT,
    CAPABILITY_UNAVAILABLE,
    DUPLICATE_EVENT,
    INVALID_PUBLICATION,
)

# runtime code -> (SDK code, retryable). Unmapped codes pass through verbatim.
RUNTIME_CODE_MAP: dict[str, tuple[str, bool]] = {
    "ui_program_stale_input_revision": (STALE_REVISION, True),
    "ui_host_stale_semantic_intent": (STALE_REVISION, True),
    "ui_host_stale_drag_drop": (STALE_REVISION, True),
    "ui_host_renderer_epoch_mismatch": (STALE_REVISION, True),
    "ui_host_invalid_drag_drop": (UNKNOWN_TARGET, False),
    "ui_host_invalid_semantic_intent": (UNKNOWN_TARGET, False),
    "ui_host_invalid_publication": (INVALID_PUBLICATION, False),
    "ui_flow_submit_failed": (INVALID_PROGRAM, False),
    "ui_program_invalid_input_schema": (INVALID_PROGRAM, False),
    "ui_program_duplicate_input_key": (INVALID_PROGRAM, False),
    "ui_program_invalid_default": (INVALID_PROGRAM, False),
    "ui_program_invalid_input_snapshot": (INVALID_PROGRAM, False),
    "nui_flow_invalid_node": (INVALID_PROGRAM, False),
    "nui_flow_unknown_component": (INVALID_PROGRAM, False),
    "nui_flow_invalid_key": (INVALID_PROGRAM, False),
}

# Codes whose message points at an undeclared key rather than malformed data.
_TARGET_DIAGNOSTIC_HINTS = ("is not declared", "unknown target", "no such node")


def normalize_error_code(code: str, message: str = "") -> tuple[str, bool]:
    """Map a runtime error code onto the frozen SDK code.

    Returns ``(sdk_code, retryable)``. Unknown codes pass through unchanged so
    diagnostics are never swallowed; ``ui_host_invalid_semantic_intent`` is
    disambiguated between ``unknown_target`` and ``invalid_publication`` via
    its message because the runtime shares one code for both shapes.
    """
    entry = RUNTIME_CODE_MAP.get(code)
    if entry is None:
        return (code, False)
    sdk_code, retryable = entry
    if code == "ui_host_invalid_semantic_intent" and not any(hint in message.lower() for hint in _TARGET_DIAGNOSTIC_HINTS):
        sdk_code = INVALID_PUBLICATION
    return (sdk_code, retryable)


class NeonError(Exception):
    """Base exception for Neon3 SDK failures."""

    code: str = "neon_error"
    retryable: bool = False

    def __init__(self, message: str = "", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class TransportError(NeonError):
    """A loopback connection, timeout, or frame transport failure."""

    code = "transport_error"
    retryable = True


class ProtocolError(NeonError):
    """A peer violated the Neon3 RPC framing or envelope contract."""

    code = "protocol_error"
    retryable = False


class RemoteError(NeonError):
    """A Neon3 service rejected or failed an RPC request.

    ``sdk_code`` is the frozen cross-language code (see
    ``docs/sdk-wire-contract.md`` §6); ``code`` keeps the raw runtime code for
    diagnostics.
    """

    def __init__(self, request_id: str, status: str, error: dict[str, Any] | None) -> None:
        self.request_id = request_id
        self.status = status
        self.error = error or {}
        raw_code = str(self.error.get("code", "unknown_remote_error"))
        message = str(self.error.get("message", "The service returned no error message."))
        self.code_runtime = raw_code
        self.code = raw_code
        self.sdk_code, self.retryable = normalize_error_code(raw_code, message)
        details = dict(self.error.get("details") or {})
        details.setdefault("runtime_code", raw_code)
        details.setdefault("status", status)
        super().__init__(f"{raw_code}: {message} (request_id={request_id}, status={status})", details=details)
        self.message = message


class CapabilityError(NeonError):
    """A required runtime capability is not advertised by the connected runtime."""

    code = CAPABILITY_UNAVAILABLE
    retryable = False

    def __init__(self, missing: tuple[str, ...] | list[str], *, service: str = "", message: str = "") -> None:
        self.missing = tuple(missing)
        self.service = service
        super().__init__(
            message or f"runtime is missing required capabilities: {', '.join(self.missing)}",
            details={"missing": list(self.missing), "service": service},
        )


class StaleRevisionError(NeonError):
    """The active program/input revision is older than the runtime expects."""

    code = STALE_REVISION
    retryable = True

    def __init__(self, message: str = "revision is stale", *, expected: Any = None, actual: Any = None, refreshed: bool = False, runtime_code: str = "") -> None:
        super().__init__(message, details={"expected": expected, "actual": actual, "refreshed": refreshed, "runtime_code": runtime_code})
        self.expected = expected
        self.actual = actual
        self.refreshed = refreshed
        self.runtime_code = runtime_code


class UnknownTargetError(NeonError):
    """A node/drag/drop key is not declared by the active program."""

    code = UNKNOWN_TARGET
    retryable = False

    def __init__(self, key: str, *, kind: str = "node", message: str = "") -> None:
        self.key = key
        super().__init__(message or f"{kind} key is not declared by the active program: {key}", details={"key": key, "kind": kind})


class UnsupportedIntentError(NeonError):
    """No route exists for the dispatched intent."""

    code = UNSUPPORTED_INTENT
    retryable = False

    def __init__(self, intent: str, *, message: str = "") -> None:
        self.intent = intent
        super().__init__(message or f"no handler is registered for intent: {intent}", details={"intent": intent})


class DuplicateEventError(NeonError):
    """An event id was already processed and replay does not match."""

    code = DUPLICATE_EVENT
    retryable = False

    def __init__(self, event_id: str, *, message: str = "") -> None:
        self.event_id = event_id
        super().__init__(message or f"duplicate event replay: {event_id}", details={"event_id": event_id})


class InvalidPublicationError(NeonError):
    """A host publication cannot be applied to the active fragment."""

    code = INVALID_PUBLICATION
    retryable = False

    def __init__(self, message: str = "publication is not valid for the active program", *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details=details)


class FlowValidationError(NeonError):
    """A Flow document failed static validation before submission."""

    code = INVALID_PROGRAM
    retryable = False

    def __init__(self, message: str, *, line: int | None = None, column: int | None = None, code_runtime: str = "nui_flow_invalid", missing_capabilities: tuple[str, ...] = ()) -> None:
        self.line = line
        self.column = column
        self.code_runtime = code_runtime
        self.missing_capabilities = missing_capabilities
        location = f" (line {line}, column {column})" if line is not None else ""
        super().__init__(f"{message}{location}", details={"line": line, "column": column, "flow_code": code_runtime, "missing": list(missing_capabilities)})
