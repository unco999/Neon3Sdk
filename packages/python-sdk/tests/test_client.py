from __future__ import annotations

import json
import socket
import struct
import threading
import unittest

from neon3_sdk import NeonClient, ProtocolError
from neon3_sdk.calculator import CalculatorDomain
from neon3_sdk.render import Backend, BackendNegotiation, Camera3D, PointerEvent, SurfaceKind, SurfaceOpen, SurfaceSize, WorldInformation
from neon3_sdk.runtime import RuntimeConfig, RuntimeMode
from neon3_sdk.cli import parse_args


class ClientWireTests(unittest.TestCase):
    def test_public_render_contracts_encode_canonical_shapes(self) -> None:
        camera = Camera3D("camera", "world", (0.0, 1.0, 2.0), (0.0, 0.0, 0.0, 1.0), 1.0, 0.1, 100.0, 4, 9)
        self.assertEqual(camera.to_wire()["payload"]["kind"], "three_dimensional")
        surface = SurfaceOpen("session", "surface", SurfaceKind.SCREEN_UI, SurfaceSize(1280, 720))
        self.assertEqual(surface.to_wire()["kind"], "screen_ui")
        pointer = PointerEvent("down", "surface", (10.0, 20.0), 1, 2, 3, 4, "primary")
        self.assertEqual(pointer.to_wire()["event_type"], "down")
        self.assertEqual(WorldInformation("world", 1).to_wire()["world_space_id"], "world")
        self.assertEqual(BackendNegotiation("session", (Backend.DX12,)).to_wire()["preferred_backends"], ["dx12"])

    def test_runtime_modes_select_correct_renderer_process(self) -> None:
        self.assertEqual(RuntimeConfig(mode=RuntimeMode.WINDOWED).wgpu_arguments[0], "--window-server")
        self.assertEqual(RuntimeConfig(mode=RuntimeMode.HEADLESS).wgpu_arguments[0], "--headless-server")
        self.assertEqual(RuntimeConfig(mode=RuntimeMode.EXTERNAL_SURFACE).wgpu_arguments[0], "--window-server")

    def test_python_domain_calculates_and_emits_revisioned_input_changes(self) -> None:
        domain = CalculatorDomain()
        program = {"program_id": "calculator", "revision": 1, "schema_version": 1, "capabilities": []}
        revision = 0
        for event_id, intent in [("1", "calculator.number.one"), ("+", "calculator.operator.add"), ("2", "calculator.number.two"), ("=", "calculator.equals")]:
            publication = domain.apply_event({"event_id": event_id, "intent": intent}, program, revision)
            revision += 1
            self.assertEqual(publication["scalar_frame"]["expected_input_revision"], revision - 1)
        self.assertEqual(domain.state.display, 3.0)
        self.assertEqual(domain.state.revision, 4)

    def test_python_domain_does_not_double_apply_after_equals(self) -> None:
        domain = CalculatorDomain()
        program = {"program_id": "calculator", "revision": 1, "schema_version": 1, "capabilities": []}
        sequence = [
            "calculator.number.one",
            "calculator.operator.add",
            "calculator.number.one",
            "calculator.equals",
            "calculator.operator.add",
            "calculator.number.one",
            "calculator.equals",
        ]
        for revision, intent in enumerate(sequence):
            domain.apply_event({"event_id": str(revision), "intent": intent}, program, revision)
        self.assertEqual(domain.state.display, 3.0)
        self.assertTrue(domain.state.awaiting_operand)

    def test_dev_up_command_parses_gallery_and_once(self) -> None:
        args = parse_args(["dev", "up", "--gallery", "--once"])
        self.assertEqual(args.command, "dev")
        self.assertEqual(args.dev_command, "up")
        self.assertTrue(args.gallery)
        self.assertTrue(args.once)

    def test_health_uses_canonical_framing_and_envelope(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        endpoint = listener.getsockname()
        observed: dict[str, object] = {}

        def server() -> None:
            stream, _ = listener.accept()
            with stream:
                size = struct.unpack(">I", receive(stream, 4))[0]
                request = json.loads(receive(stream, size))
                observed.update(request)
                response = {
                    "request_id": request["request_id"],
                    "status": "accepted",
                    "revision": None,
                    "result": {"service": "ui-runtime", "status": "healthy", "epoch": 7},
                    "snapshot": None,
                    "error": None,
                }
                encoded = json.dumps(response, separators=(",", ":")).encode()
                stream.sendall(struct.pack(">I", len(encoded)) + encoded)
            listener.close()

        thread = threading.Thread(target=server)
        thread.start()
        health = NeonClient.connect(endpoint, origin="test").health("ui-runtime")
        thread.join(timeout=2)

        self.assertEqual(health.epoch, 7)
        self.assertEqual(observed["protocol"], "neon3.rpc")
        self.assertEqual(observed["version"], {"major": 1, "minor": 0})
        self.assertEqual(observed["client"]["kind"], "cli")
        self.assertEqual(observed["target"], "ui-runtime")
        self.assertEqual(observed["method"], "service.health")

    def test_mismatched_request_id_is_rejected(self) -> None:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        endpoint = listener.getsockname()

        def server() -> None:
            stream, _ = listener.accept()
            with stream:
                size = struct.unpack(">I", receive(stream, 4))[0]
                receive(stream, size)
                response = {"request_id": "wrong", "status": "accepted", "revision": None, "result": None, "snapshot": None, "error": None}
                encoded = json.dumps(response).encode()
                stream.sendall(struct.pack(">I", len(encoded)) + encoded)
            listener.close()

        thread = threading.Thread(target=server)
        thread.start()
        with self.assertRaises(ProtocolError):
            NeonClient.connect(endpoint).call("ui-runtime", "service.health")
        thread.join(timeout=2)


def receive(stream: socket.socket, length: int) -> bytes:
    parts = []
    while length:
        part = stream.recv(length)
        if not part:
            raise RuntimeError("connection closed")
        parts.append(part)
        length -= len(part)
    return b"".join(parts)
