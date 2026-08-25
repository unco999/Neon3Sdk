"""One-command local Neon3 lifecycle commands driven by the Python SDK."""

from __future__ import annotations

import argparse
import json
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .calculator import CalculatorServer, send_calculator_event, submit_calculator
from .client import NeonClient
from .errors import NeonError
from .models import AssetRef
from .nui import ComponentGallery


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    endpoint: str
    executable: Path
    arguments: tuple[str, ...]


class NeonDevelopmentSession:
    """Owns a local headless Neon3 process set started by this Python process."""

    def __init__(self, neon_root: Path, eventd_endpoint: str, ui_endpoint: str, wgpu_endpoint: str, *, windowed: bool = False) -> None:
        self.neon_root = neon_root.resolve()
        debug = self.neon_root / "target" / "debug"
        self.specs = (
            ServiceSpec("eventd", eventd_endpoint, debug / "neon-eventd.exe", ("--server", eventd_endpoint, "1")),
            ServiceSpec(
                "wgpu-runtime",
                wgpu_endpoint,
                debug / "neon-wgpu-runtime.exe",
                ("--window-server", wgpu_endpoint, ui_endpoint) if windowed else ("--headless-server", wgpu_endpoint),
            ),
            ServiceSpec(
                "ui-runtime",
                ui_endpoint,
                debug / "neon-ui-runtime.exe",
                ("--forward-server", ui_endpoint, wgpu_endpoint, "127.0.0.1:39104", "--eventd", eventd_endpoint),
            ),
        )
        self.processes: list[tuple[ServiceSpec, subprocess.Popen[str]]] = []

    def start(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for spec in self.specs:
            if not spec.executable.is_file():
                raise FileNotFoundError(f"required Neon3 binary was not found: {spec.executable}")
            if endpoint_in_use(spec.endpoint):
                raise RuntimeError(f"endpoint is already in use: {spec.endpoint}; do not attach this launcher to unmanaged services")
            process = subprocess.Popen(
                [str(spec.executable), *spec.arguments],
                cwd=self.neon_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self.processes.append((spec, process))
            records.append({"service": spec.name, "endpoint": spec.endpoint, "pid": process.pid})
        return records

    def wait_healthy(self, timeout_seconds: float) -> list[dict[str, Any]]:
        results = []
        for spec in self.specs:
            target = spec.name
            deadline = time.monotonic() + timeout_seconds
            last_error = "not attempted"
            while time.monotonic() < deadline:
                process = next(process for candidate, process in self.processes if candidate == spec)
                if process.poll() is not None:
                    raise RuntimeError(f"{spec.name} exited before health check (return_code={process.returncode})")
                try:
                    client = NeonClient.connect(spec.endpoint, origin="neon3-sdk-dev", timeout_seconds=0.5)
                    health = client.health(target)
                    description = client.describe(target)
                    if health.status == "healthy":
                        results.append({"service": target, "endpoint": spec.endpoint, "epoch": health.epoch, "capabilities": list(description.capabilities)})
                        break
                    last_error = f"health status was {health.status}"
                except NeonError as error:
                    last_error = str(error)
                time.sleep(0.1)
            else:
                raise RuntimeError(f"health timeout for {target} at {spec.endpoint}: {last_error}")
        return results

    def stop(self) -> list[dict[str, Any]]:
        records = []
        for spec, process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            records.append({"service": spec.name, "pid": process.pid, "return_code": process.returncode})
        self.processes.clear()
        return records


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "dev" and args.dev_command == "up":
        return dev_up(args)
    if args.command == "calculator":
        return calculator_demo(args)
    raise AssertionError("argument parser accepted an unsupported command")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="neon3-sdk", description="Python-operated local Neon3 development lifecycle.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    dev = subparsers.add_parser("dev", help="manage a local headless Neon3 service set")
    dev_commands = dev.add_subparsers(dest="dev_command", required=True)
    up = dev_commands.add_parser("up", help="start Neon3 services and communicate through the Python SDK")
    up.add_argument("--neon-root", type=Path, default=Path("D:/Neon3"))
    up.add_argument("--eventd-endpoint", default="127.0.0.1:39101")
    up.add_argument("--ui-endpoint", default="127.0.0.1:39102")
    up.add_argument("--wgpu-endpoint", default="127.0.0.1:39103")
    up.add_argument("--timeout-seconds", type=float, default=15.0)
    up.add_argument("--gallery", action="store_true", help="submit Neon3's complete ImGui component-gallery NUI after startup")
    up.add_argument("--once", action="store_true", help="stop after health checks and optional gallery submission")
    calculator = subparsers.add_parser("calculator", help="run the Python-owned calculator protocol scenario")
    calculator.add_argument("--neon-root", type=Path, default=Path("D:/Neon3"))
    calculator.add_argument("--eventd-endpoint", default="127.0.0.1:39101")
    calculator.add_argument("--ui-endpoint", default="127.0.0.1:39102")
    calculator.add_argument("--wgpu-endpoint", default="127.0.0.1:39103")
    calculator.add_argument("--calculator-endpoint", default="127.0.0.1:39104")
    calculator.add_argument("--timeout-seconds", type=float, default=15.0)
    calculator.add_argument("--headless", action="store_true", help="use a headless renderer for CI")
    calculator.add_argument("--once", action="store_true", help="exit after the protocol scenario instead of keeping the window open")
    return parser.parse_args(argv)


def dev_up(args: argparse.Namespace) -> int:
    run_id = str(uuid.uuid4())
    session = NeonDevelopmentSession(args.neon_root, args.eventd_endpoint, args.ui_endpoint, args.wgpu_endpoint)
    try:
        for record in session.start():
            emit(run_id, "service.start", "started", **record)
        for record in session.wait_healthy(args.timeout_seconds):
            emit(run_id, "service.ready", "passed", **record)
        if args.gallery:
            gallery = ComponentGallery(args.neon_root)
            asset = AssetRef("sdk-dev-project", 1, 1, "image")
            result = gallery.submit(args.ui_endpoint, asset, timeout_seconds=args.timeout_seconds)
            emit(run_id, "gallery.submit", "passed", endpoint=args.ui_endpoint, source=str(gallery.source_path), return_code=result.return_code)
        emit(run_id, "session", "ready", ui_endpoint=args.ui_endpoint, wgpu_endpoint=args.wgpu_endpoint)
        if not args.once:
            wait_for_interrupt()
        return 0
    except (OSError, RuntimeError, NeonError, subprocess.TimeoutExpired) as error:
        emit(run_id, "session", "failed", error_type=type(error).__name__, error=str(error))
        return 1
    finally:
        for record in session.stop():
            emit(run_id, "service.stop", "stopped", **record)


def calculator_demo(args: argparse.Namespace) -> int:
    run_id = str(uuid.uuid4())
    if endpoint_in_use(args.calculator_endpoint):
        emit(run_id, "calculator", "failed", error_type="RuntimeError", error=f"calculator endpoint is already in use: {args.calculator_endpoint}")
        return 1
    domain_server = CalculatorServer(args.calculator_endpoint)
    domain_thread = __import__("threading").Thread(target=domain_server.serve, daemon=True)
    session = NeonDevelopmentSession(args.neon_root, args.eventd_endpoint, args.ui_endpoint, args.wgpu_endpoint, windowed=not args.headless)
    try:
        domain_thread.start()
        if not domain_server.ready.wait(timeout=2):
            raise RuntimeError("calculator domain did not bind within 2 seconds")
        if domain_server.start_error is not None:
            raise RuntimeError(f"calculator domain failed to bind: {domain_server.start_error}")
        emit(run_id, "calculator.start", "started", endpoint=args.calculator_endpoint, pid=None)
        for record in session.start():
            emit(run_id, "service.start", "started", **record)
        for record in session.wait_healthy(args.timeout_seconds):
            emit(run_id, "service.ready", "passed", **record)
        calculator = NeonClient.connect(args.calculator_endpoint, origin="neon3-sdk-calculator", timeout_seconds=1.0)
        health = calculator.health("calculator-python")
        emit(run_id, "calculator.health", "passed", epoch=health.epoch)
        ui = NeonClient.connect(args.ui_endpoint, origin="neon3-sdk-calculator", timeout_seconds=args.timeout_seconds)
        submitted = submit_calculator(ui)
        program_revision = submitted["program_revision"]
        input_revision = 0
        emit(run_id, "calculator.flow.submit", "passed", surface_id=submitted["surface_id"], program_revision=program_revision, input_schema=submitted["input_schema"])
        # A real window starts with the authoritative Python state at zero. The
        # deterministic 1 + 2 scenario belongs only to CI/one-shot execution;
        # running it before an operator clicks made manual input append to 3.
        if not args.once and not args.headless:
            emit(run_id, "calculator.window", "ready", initial_state=domain_server.domain.state.__dict__.copy(), instruction="Press Ctrl+C to stop the Python domain and Neon3 services.")
            wait_for_interrupt()
            return 0
        steps = [
            ("calculator.number.one", "one"),
            ("calculator.operator.add", "add"),
            ("calculator.number.one", "one"),
            ("calculator.equals", "equals"),
            ("calculator.operator.add", "add"),
            ("calculator.number.one", "one"),
            ("calculator.equals", "equals"),
        ]
        for intent, source in steps:
            response = send_calculator_event(ui, program_revision, input_revision, intent, source)
            # RPC response revision is the presentation fragment revision. The
            # calculator event contract is revisioned against scalar input state.
            input_revision += 1
            emit(run_id, "calculator.event", "passed", intent=intent, source_node_key=source, request_id=response.request_id, input_revision=input_revision, state=domain_server.domain.state.__dict__.copy())
        passed = domain_server.domain.state.display == 3.0
        renderer = NeonClient.connect(args.wgpu_endpoint, origin="neon3-sdk-calculator-probe", timeout_seconds=args.timeout_seconds)
        fragment = renderer.call(
            "wgpu-runtime",
            "wgpu.ui.fragment.snapshot",
            {"fragment_id": "surface.calculator"},
            request_id=f"calculator-render-probe-{run_id}",
        )
        fragment_data = fragment.result if isinstance(fragment.result, dict) else {}
        rendered_text = "3" in json.dumps(fragment_data.get("fragment", {}), sort_keys=True)
        passed = passed and rendered_text
        emit(run_id, "calculator.renderer.verify", "passed" if rendered_text else "failed", request_id=fragment.request_id, producer={"domain_revision": domain_server.domain.state.revision, "ui_input_revision": input_revision}, consumer={"fragment_revision": fragment_data.get("fragment_revision"), "fragment_sequence": fragment_data.get("sequence")}, expected_text="3", rendered_text_found=rendered_text)
        emit(run_id, "calculator.result", "passed" if passed else "failed", scenario="1 + 1 = + 1 =", expected=3.0, actual=domain_server.domain.state.display, domain_revision=domain_server.domain.state.revision, ui_input_revision=input_revision, windowed=not args.headless)
        return 0 if passed else 1
    except (OSError, RuntimeError, NeonError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        emit(run_id, "calculator", "failed", error_type=type(error).__name__, error=str(error))
        return 1
    finally:
        domain_server.stop()
        for record in session.stop():
            emit(run_id, "service.stop", "stopped", **record)


def endpoint_in_use(endpoint: str) -> bool:
    host, port_text = endpoint.rsplit(":", 1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.settimeout(0.2)
        return stream.connect_ex((host, int(port_text))) == 0


def wait_for_interrupt() -> None:
    interrupted = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True

    previous = signal.signal(signal.SIGINT, request_stop)
    try:
        while not interrupted:
            time.sleep(0.2)
    finally:
        signal.signal(signal.SIGINT, previous)


def emit(run_id: str, stage: str, status: str, **data: Any) -> None:
    print(json.dumps({"run_id": run_id, "stage": stage, "status": status, **data}, ensure_ascii=True), flush=True)
