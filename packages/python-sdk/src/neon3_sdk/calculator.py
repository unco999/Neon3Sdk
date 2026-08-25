"""Python-owned calculator domain connected to the Neon3 UI runtime."""

from __future__ import annotations

import json
import socket
import struct
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import NeonClient
from .errors import ProtocolError, RemoteError, TransportError

CALCULATOR_FLOW = (Path(__file__).with_name("fixtures") / "calculator.nui").read_text(encoding="utf-8")


@dataclass
class CalculatorState:
    display: float = 0.0
    accumulator: float = 0.0
    pending: float = 0.0
    operation: str = "add"
    awaiting_operand: bool = True
    revision: int = 0


class CalculatorDomain:
    """Owns calculator rules and returns only typed UI input publications."""

    def __init__(self) -> None:
        self.state = CalculatorState()
        self._lock = threading.Lock()
        self._seen: dict[str, dict[str, Any]] = {}

    def apply_event(self, event: dict[str, Any], program_revision: dict[str, Any], input_revision: int) -> dict[str, Any]:
        event_id = event.get("event_id", "")
        with self._lock:
            if event_id in self._seen:
                return self._seen[event_id]
            intent = event.get("intent", "")
            if intent.startswith("calculator.number."):
                digit = {
                    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
                    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                }[intent.rsplit(".", 1)[1]]
                self.state.display = digit if self.state.awaiting_operand else self.state.display * 10 + digit
                self.state.awaiting_operand = False
            elif intent == "calculator.clear":
                self.state = CalculatorState()
            elif intent.startswith("calculator.operator."):
                if not self.state.awaiting_operand:
                    self.state.accumulator = (
                        self._calculate(self.state.accumulator, self.state.display, self.state.operation)
                        if self.state.pending
                        else self.state.display
                    )
                    self.state.pending = self.state.accumulator
                self.state.operation = intent.rsplit(".", 1)[1]
                self.state.awaiting_operand = True
            elif intent == "calculator.equals":
                if not self.state.awaiting_operand and self.state.pending:
                    self.state.display = self._calculate(self.state.accumulator, self.state.display, self.state.operation)
                    self.state.accumulator = self.state.display
                    self.state.pending = self.state.display
                self.state.awaiting_operand = True
            else:
                raise ValueError(f"unsupported calculator intent: {intent}")
            self.state.revision += 1
            publication = self._publication(program_revision, input_revision, event_id)
            self._seen[event_id] = publication
            return publication

    @staticmethod
    def _calculate(left: float, right: float, operation: str) -> float:
        if operation == "add":
            return left + right
        if operation == "subtract":
            return left - right
        if operation == "multiply":
            return left * right
        if operation == "divide":
            if right == 0:
                raise ValueError("division by zero")
            return left / right
        return right

    def _publication(self, program_revision: dict[str, Any], input_revision: int, request_id: str) -> dict[str, Any]:
        next_input_revision = input_revision + 1
        return {
            "scalar_frame": {
                "program_revision": program_revision,
                "expected_input_revision": input_revision,
                "request_id": request_id,
                "idempotency_key": f"calculator-input:{self.state.revision}",
                "changes": [
                    {"key": "display", "value": {"kind": "f32", "value": self.state.display}},
                    {"key": "accumulator", "value": {"kind": "f32", "value": self.state.accumulator}},
                    {"key": "pending", "value": {"kind": "f32", "value": self.state.pending}},
                    {"key": "operation", "value": {"kind": "enum", "value": self.state.operation}},
                ],
            },
            "grid_inputs": [],
            "presentation_update": None,
            "calculator": {"revision": self.state.revision, "input_revision": next_input_revision, "state": self.state.__dict__.copy()},
        }


class CalculatorServer:
    """Length-prefixed JSON Neon RPC server for the Python calculator domain."""

    def __init__(self, endpoint: str, domain: CalculatorDomain | None = None) -> None:
        host, port = endpoint.rsplit(":", 1)
        self.endpoint = (host, int(port))
        self.domain = domain or CalculatorDomain()
        self._listener: socket.socket | None = None
        self._stop = threading.Event()
        self.ready = threading.Event()
        self.start_error: Exception | None = None

    def serve(self) -> None:
        try:
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(self.endpoint)
            listener.listen(16)
            listener.settimeout(0.2)
            self._listener = listener
            self.ready.set()
            while not self._stop.is_set():
                try:
                    stream, _ = listener.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._handle, args=(stream,), daemon=True).start()
        except OSError as error:
            self.start_error = error
            self.ready.set()
        finally:
            if self._listener is not None:
                self._listener.close()

    def stop(self) -> None:
        self._stop.set()
        if self._listener is not None:
            self._listener.close()

    def _handle(self, stream: socket.socket) -> None:
        with stream:
            try:
                request = json.loads(_recv_frame(stream).decode("utf-8"))
                response = self._dispatch(request)
                _send_frame(stream, json.dumps(response, separators=(",", ":")).encode("utf-8"))
            except Exception as error:
                request_id = request.get("request_id", "unknown") if isinstance(request, dict) else "unknown"
                response = _response(request_id, "failed", error={"code": "calculator_error", "message": str(error)})
                try:
                    _send_frame(stream, json.dumps(response, separators=(",", ":")).encode("utf-8"))
                except OSError:
                    pass

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request["request_id"]
        method = request["method"]
        if method == "service.health":
            return _response(request_id, "accepted", result={"service": "calculator-python", "status": "healthy", "epoch": 1})
        if method == "service.describe":
            return _response(request_id, "accepted", result={"service": "calculator-python", "protocol_version": {"major": 1, "minor": 0}, "endpoint": f"{self.endpoint[0]}:{self.endpoint[1]}", "epoch": 1, "capabilities": ["calculator.evaluate.v1", "ui.host.publication.v1"]})
        if method == "debug.snapshot.get":
            return _response(request_id, "accepted", result={"service": "calculator-python", "epoch": 1, "revision": self.domain.state.revision, "state": self.domain.state.__dict__.copy()})
        if method != "ui.host.inbound":
            return _response(request_id, "rejected", error={"code": "unsupported_method", "message": "method is not supported"})
        inbound = request["params"]
        event = inbound["event"]
        program_revision = event["program_revision"]
        input_revision = event["input_revision"]
        try:
            publication = self.domain.apply_event(event, program_revision, input_revision)
        except ValueError as error:
            return _response(request_id, "rejected", error={"code": "calculator_rejected", "message": str(error)})
        return _response(request_id, "accepted", revision=publication["calculator"]["input_revision"], result={k: v for k, v in publication.items() if k != "calculator"}, snapshot=publication["calculator"])


def submit_calculator(client: NeonClient, source: str = CALCULATOR_FLOW) -> dict[str, Any]:
    return client.call("ui-runtime", "ui.flow.submit", {"source": source}, idempotency_key="calculator-flow-v1").result


def send_calculator_event(client: NeonClient, program_revision: dict[str, Any], input_revision: int, intent: str, source_node_key: str) -> Any:
    event_id = str(uuid.uuid4())
    event = {
        "event_id": event_id,
        "kind": "activate",
        "intent": intent,
        "source_node_key": source_node_key,
        "payload": {},
        "program_revision": program_revision,
        "input_revision": input_revision,
        "request_id": event_id,
        "idempotency_key": f"calculator-event:{event_id}",
        "interaction": {"interaction_id": event_id, "sequence": 1, "renderer_epoch": 1},
    }
    return client.call("ui-runtime", "ui.host.inbound", {"kind": "semantic_intent", "event": event}, idempotency_key=f"calculator-host:{event_id}")


def _response(request_id: str, status: str, *, result: Any = None, snapshot: Any = None, revision: int | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"request_id": request_id, "status": status, "revision": revision, "result": result, "snapshot": snapshot, "error": error}


def _recv_frame(stream: socket.socket) -> bytes:
    header = _recv_exact(stream, 4)
    size = struct.unpack(">I", header)[0]
    return _recv_exact(stream, size)


def _recv_exact(stream: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise TransportError("connection_closed")
        data.extend(chunk)
    return bytes(data)


def _send_frame(stream: socket.socket, payload: bytes) -> None:
    stream.sendall(struct.pack(">I", len(payload)) + payload)
