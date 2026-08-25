"""Executable JSONL probe for the public multi-mode SDK API."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from ..client import NeonClient
from ..errors import NeonError
from ..render import Camera3D, RenderClient, SurfaceKind, SurfaceOpen, SurfaceSize, SurfaceTarget, WorldInformation
from ..runtime import RuntimeConfig, RuntimeEndpoints, RuntimeMode, RuntimeSession, default_neon_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--neon-root", type=Path, default=default_neon_root())
    parser.add_argument("--external-surface", action="store_true")
    args = parser.parse_args()
    run_id = str(uuid.uuid4())
    mode = RuntimeMode.EXTERNAL_SURFACE if args.external_surface else RuntimeMode.HEADLESS
    config = RuntimeConfig(neon_root=str(args.neon_root), mode=mode, endpoints=RuntimeEndpoints())
    try:
        with RuntimeSession(config):
            rpc = NeonClient.connect(config.endpoints.wgpu, origin="neon3-sdk-api-probe", kind="external_host" if args.external_surface else "cli")
            description = rpc.describe("wgpu-runtime")
            emit(run_id, "describe", "passed", service=description.service, capabilities=list(description.capabilities), epoch=description.epoch)
            renderer = RenderClient(rpc)
            if args.external_surface:
                surface = renderer.open_surface(SurfaceOpen("api-probe-session", "api-probe-surface", SurfaceKind.SCREEN_UI, SurfaceSize(320, 180), targets=(SurfaceTarget("api-probe-color"),)))
                emit(run_id, "surface.open", "passed", descriptor=surface.descriptor)
                emit(run_id, "surface.acquire", "passed", handles=surface.acquire_current_process())
                emit(run_id, "surface.frame", "passed", frame=surface.frame())
            world = WorldInformation("api-probe-world", 1)
            world_result = renderer.configure_world(world)
            emit(run_id, "world.configure", "passed", input=world.to_wire(), result=world_result)
            camera = Camera3D("api-probe-camera", "api-probe-world", (0.0, 1.0, 3.0), (0.0, 0.0, 0.0, 1.0), 1.0, 0.1, 100.0, description.epoch, 1)
            camera_result = renderer.submit_camera(camera)
            emit(run_id, "camera.submit", "passed", input=camera.to_wire(), result=camera_result)
            diagnostics = renderer.diagnostics()
            graph = renderer.graph_snapshot()
            emit(run_id, "render.inspect", "passed", diagnostics=diagnostics, graph=graph)
        emit(run_id, "result", "passed", modes=[mode.value for mode in RuntimeMode], external_surface_contract="negotiated_only")
        return 0
    except (NeonError, OSError, RuntimeError, TimeoutError, ValueError) as error:
        emit(run_id, "result", "failed", error_type=type(error).__name__, error=str(error))
        return 1


def emit(run_id: str, stage: str, status: str, **data: object) -> None:
    print(json.dumps({"run_id": run_id, "stage": stage, "status": status, **data}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())
