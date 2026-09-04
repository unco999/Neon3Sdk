"""Shared surface texture + PNG save contract test (Windows GPU).

Spawns the Neon3 headless external GPU server (DX12, no window), opens a
shared surface through the public SDK API, saves the surface texture to a
PNG file, and verifies the artifact. Skips cleanly when the runtime binary
is unavailable or the integration flag is not set, so non-GPU CI stays green.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from neon3_sdk import NeonClient, RenderClient, SurfaceKind, SurfaceOpen, SurfaceSize

INTEGRATION = os.environ.get("NEON3_SURFACE_PNG_INTEGRATION") == "1"
ENDPOINT = "127.0.0.1:43114"
PORT = 43114


def _runtime_bin() -> str | None:
    override = os.environ.get("NEON3_RUNTIME_BIN")
    if override:
        return override
    candidates = [
        Path(r"D:\Neon3\target\debug\neon-wgpu-runtime.exe"),
        Path(os.environ.get("LOCALAPPDATA", ""), "Neon3Sdk", "runtime", "latest", "neon-wgpu-runtime.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


@unittest.skipUnless(INTEGRATION and os.name == "nt", "set NEON3_SURFACE_PNG_INTEGRATION=1 on Windows with a DX12 GPU")
class SurfacePngIntegrationTests(unittest.TestCase):
    def test_open_surface_and_save_png(self) -> None:
        bin_path = _runtime_bin()
        if not bin_path:
            self.skipTest("neon-wgpu-runtime binary not found (NEON3_RUNTIME_BIN?)")
        server = subprocess.Popen(
            [bin_path, "--headless-external-server", ENDPOINT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        client: NeonClient | None = None
        with tempfile.TemporaryDirectory(prefix="neon3-surface-png-") as directory:
            png_path = str(Path(directory) / "surface.png")
            try:
                deadline = time.monotonic() + 15.0
                while time.monotonic() < deadline:
                    try:
                        probe = NeonClient.connect(ENDPOINT, origin="surface-png-test", kind="cli", timeout_seconds=1.0)
                        if probe.health("wgpu-runtime").status == "healthy":
                            client = NeonClient.connect(ENDPOINT, origin="surface-png-test", kind="cli", timeout_seconds=8.0)
                            break
                    except Exception:
                        time.sleep(0.2)
                self.assertIsNotNone(client, "headless external server did not become healthy in time")
                assert client is not None
                renderer = RenderClient(client)

                flow = client.call("wgpu-runtime", "ui.flow.submit", {"source": "version 1\nsurface example revision 1\nsurface root\n"})
                self.assertEqual(flow.status, "accepted")

                surface = renderer.open_surface(
                    SurfaceOpen(
                        session_id="test-session",
                        surface_id="example",
                        kind=SurfaceKind.SCREEN_UI,
                        size=SurfaceSize(width=320, height=200),
                        buffer_count=2,
                    )
                )
                self.assertGreaterEqual(surface.generation, 0)

                time.sleep(1.2)
                capture = surface.save_png(png_path)
                self.assertIsInstance(capture, dict)
                self.assertIsInstance(capture.get("artifact_path"), str)
                self.assertTrue(Path(png_path).is_file(), "PNG artifact must exist on disk")
                header = Path(png_path).read_bytes()[:8]
                self.assertEqual(header, b"\x89PNG\r\n\x1a\n", "artifact must be a valid PNG")
            finally:
                if client is not None:
                    try:
                        client.call("wgpu-runtime", "service.shutdown", {}, raise_for_status=False)
                    except Exception:
                        pass
                server.kill()
                try:
                    server.wait(timeout=5)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()