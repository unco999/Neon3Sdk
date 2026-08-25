"""Run the canonical component gallery through actual local Neon3 services.

Each JSONL record includes the stable request ID or process identity needed to
correlate the Python client, UI runtime, and renderer journals.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from neon3_sdk.client import NeonClient
from neon3_sdk.errors import NeonError
from neon3_sdk.models import AssetRef
from neon3_sdk.nui import ComponentGallery


def main() -> int:
    args = parse_args()
    run_id = str(uuid.uuid4())
    processes: list[subprocess.Popen[str]] = []
    outcome = "failed"
    try:
        neon_root = args.neon_root.resolve()
        executables = {
            "eventd": neon_root / "target" / "debug" / "neon-eventd.exe",
            "wgpu-runtime": neon_root / "target" / "debug" / "neon-wgpu-runtime.exe",
            "ui-runtime": neon_root / "target" / "debug" / "neon-ui-runtime.exe",
            "nui-flow-demo": neon_root / "target" / "debug" / "nui_flow_demo.exe",
        }
        missing = [str(path) for path in executables.values() if not path.is_file()]
        if missing:
            emit(run_id, "setup", "failed", missing_binaries=missing)
            return 2
        endpoints = {
            "eventd": args.eventd_endpoint,
            "ui-runtime": args.ui_endpoint,
            "wgpu-runtime": args.wgpu_endpoint,
        }
        processes = start_services(executables, endpoints, neon_root, run_id)
        ui = wait_for_health(args.ui_endpoint, "ui-runtime", args.timeout_seconds, run_id)
        wgpu = wait_for_health(args.wgpu_endpoint, "wgpu-runtime", args.timeout_seconds, run_id)
        wait_for_health(args.eventd_endpoint, "eventd", args.timeout_seconds, run_id)
        description = ui.describe("ui-runtime")
        emit(
            run_id,
            "ui.describe",
            "passed",
            endpoint=args.ui_endpoint,
            service=description.service,
            epoch=description.epoch,
            capabilities=list(description.capabilities),
        )
        gallery = ComponentGallery(neon_root, executables["nui-flow-demo"])
        asset = AssetRef("sdk-probe-project", 1, 1, "image")
        submission = gallery.submit(args.ui_endpoint, asset, timeout_seconds=args.timeout_seconds)
        emit(
            run_id,
            "gallery.submit",
            "passed",
            endpoint=args.ui_endpoint,
            source=str(gallery.source_path),
            executable=str(submission.executable),
            input_asset=asset.to_wire(),
            return_code=submission.return_code,
        )
        diagnostics = wgpu.diagnostics()
        graph = wgpu.call("wgpu-runtime", "wgpu.render.graph.snapshot", request_id=f"sdk-gallery-graph-{run_id}")
        expected_fragment = "nui-flow-case-component-gallery"
        fragment = wgpu.call(
            "wgpu-runtime",
            "wgpu.ui.fragment.snapshot",
            {"fragment_id": expected_fragment},
            request_id=f"sdk-gallery-fragment-{run_id}",
        )
        fragment_count = diagnostics.get("fragment_count") if isinstance(diagnostics, dict) else None
        graph_data = graph.result if isinstance(graph.result, dict) else {}
        fragment_data = fragment.result if isinstance(fragment.result, dict) else {}
        submitted_id = fragment_data.get("fragment", {}).get("fragment_id")
        passed = fragment_count is not None and fragment_count >= 1 and submitted_id == expected_fragment
        emit(
            run_id,
            "renderer.verify",
            "passed" if passed else "failed",
            endpoint=args.wgpu_endpoint,
            request_id=fragment.request_id,
            producer={"ui_runtime_epoch": description.epoch, "nui_source": str(gallery.source_path)},
            consumer={"wgpu_runtime_epoch": wgpu.health("wgpu-runtime").epoch, "fragment_count": fragment_count},
            expected_fragment_id=expected_fragment,
            submitted_fragment_id=submitted_id,
            fragment_revision=fragment_data.get("fragment_revision"),
            fragment_sequence=fragment_data.get("sequence"),
            graph_revision=graph_data.get("graph_revision"),
        )
        if not passed:
            return 1
        outcome = "passed"
        return 0
    except (NeonError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        emit(run_id, "probe", "failed", error_type=type(error).__name__, error=str(error))
        return 1
    finally:
        stop_services(processes, run_id)
        emit(run_id, "result", outcome)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit and verify Neon3's complete ImGui component gallery.")
    parser.add_argument("--neon-root", type=Path, default=Path("D:/Neon3"))
    parser.add_argument("--eventd-endpoint", default="127.0.0.1:39101")
    parser.add_argument("--ui-endpoint", default="127.0.0.1:39102")
    parser.add_argument("--wgpu-endpoint", default="127.0.0.1:39103")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    return parser.parse_args()


def start_services(executables: dict[str, Path], endpoints: dict[str, str], cwd: Path, run_id: str) -> list[subprocess.Popen[str]]:
    commands = [
        ("eventd", [str(executables["eventd"]), "--server", endpoints["eventd"], "1"]),
        ("wgpu-runtime", [str(executables["wgpu-runtime"]), "--headless-server", endpoints["wgpu-runtime"]]),
        (
            "ui-runtime",
            [
                str(executables["ui-runtime"]),
                "--forward-server",
                endpoints["ui-runtime"],
                endpoints["wgpu-runtime"],
                "127.0.0.1:39104",
                "--eventd",
                endpoints["eventd"],
            ],
        ),
    ]
    processes = []
    for name, command in commands:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        processes.append(process)
        emit(run_id, "service.start", "started", service=name, pid=process.pid, endpoint=endpoints.get(name))
    return processes


def wait_for_health(endpoint: str, target: str, timeout_seconds: float, run_id: str) -> NeonClient:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        client = NeonClient.connect(endpoint, origin="neon3-component-gallery-probe", timeout_seconds=0.5)
        try:
            health = client.health(target)
            if health.status == "healthy":
                emit(run_id, "service.health", "passed", service=target, endpoint=endpoint, epoch=health.epoch)
                return client
            last_error = f"unexpected health status: {health.status}"
        except NeonError as error:
            last_error = str(error)
        time.sleep(0.1)
    raise RuntimeError(f"health timeout for {target} at {endpoint}: {last_error}")


def stop_services(processes: list[subprocess.Popen[str]], run_id: str) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        emit(run_id, "service.stop", "stopped", pid=process.pid, return_code=process.returncode)


def emit(run_id: str, stage: str, status: str, **data: Any) -> None:
    print(json.dumps({"run_id": run_id, "stage": stage, "status": status, **data}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())
