"""Android transport for the Neon3 Python SDK.

The Neon3 Android Host runs inside an APK foreground service on
127.0.0.1:43100 (headless, no window). This session locates the device,
establishes `adb forward` (or a direct device IP), waits for the headless
host health, and shuts it down cleanly on stop. The wire contract and
target semantics are identical to the desktop runtime; only the bootstrap
differs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .client import NeonClient

ANDROID_HOST_ENDPOINT = "127.0.0.1:43100"
ANDROID_HOST_PORT = 43100


@dataclass
class AndroidConfig:
    """Bootstrap configuration for an Android host session.

    Attributes:
        adb: adb executable. Defaults to ANDROID_HOME/platform-tools/adb
            or the adb found on PATH.
        device: device serial (e.g. emulator-5554). Defaults to the first
            connected device.
        use_forward: use `adb forward tcp:43100 tcp:43100`. Default True
            (loopback endpoint).
        host: direct device IP when not using adb forward. Requires
            allow_non_loopback on the client.
        port: host port when not using adb forward. Default 43100.
        timeout_seconds: wait budget for the host to become healthy.
            Default 15.0.
    """

    adb: str | None = None
    device: str | None = None
    use_forward: bool = True
    host: str | None = None
    port: int = ANDROID_HOST_PORT
    timeout_seconds: float = 15.0


@dataclass
class AndroidSessionHandle:
    """Resolved connection information after ``AndroidSession.start``."""

    endpoint: str
    device: str
    use_forward: bool


class AndroidSession:
    """Lifecycle for a Neon3 Android host connection."""

    def __init__(self, config: AndroidConfig | None = None) -> None:
        self.config = config or AndroidConfig()
        self.endpoint = ""
        self._adb = ""
        self._device = ""
        self._forward_active = False
        self._stopped = False

    def _resolve_adb(self) -> str:
        if self.config.adb:
            if not os.path.isfile(self.config.adb):
                raise RuntimeError(f"adb not found at {self.config.adb}")
            return self.config.adb
        sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if sdk_root:
            candidate = os.path.join(sdk_root, "platform-tools", "adb.exe" if os.name == "nt" else "adb")
            if os.path.isfile(candidate):
                return candidate
        found = shutil.which("adb")
        if found:
            return found
        raise RuntimeError("adb not found; set AndroidConfig.adb or ANDROID_HOME")

    def _run_adb(self, args: list[str], timeout_seconds: float) -> str:
        result = subprocess.run(
            [self._adb, *args],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"adb {' '.join(args)} failed: {(result.stderr or '').strip()}")
        return result.stdout

    def _resolve_device(self) -> str:
        output = self._run_adb(["devices"], 10.0)
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        devices = [
            line.split()[0]
            for line in lines[1:]
            if not line.endswith("offline") and not line.endswith("unauthorized")
        ]
        if self.config.device:
            if self.config.device not in devices:
                raise RuntimeError(f"adb device {self.config.device} is not connected")
            return self.config.device
        if not devices:
            raise RuntimeError("no adb devices found; start an emulator or connect a device")
        return devices[0]

    def _wait_healthy(self, endpoint: str) -> None:
        deadline = time.monotonic() + self.config.timeout_seconds
        last_error: Any = None
        while time.monotonic() < deadline:
            try:
                client = NeonClient.connect(
                    endpoint,
                    origin="neon3-python-android",
                    kind="cli",
                    timeout_seconds=1.0,
                    allow_non_loopback=True,
                )
                health = client.health("wgpu-runtime")
                if health.status == "healthy":
                    return
            except Exception as error:  # noqa: BLE001 - probing
                last_error = error
            time.sleep(0.15)
        raise RuntimeError(f"Timed out waiting for Neon3 Android host at {endpoint}: {last_error}")

    def start(self) -> AndroidSessionHandle:
        """Locate the device, establish the endpoint, and wait for host health."""
        self._adb = self._resolve_adb()
        use_forward = self.config.use_forward
        if not use_forward and self.config.host:
            self._device = self.config.device or self.config.host
            endpoint = f"{self.config.host}:{self.config.port}"
        else:
            self._device = self._resolve_device()
            if self.config.device and self._device != self.config.device:
                raise RuntimeError(f"adb device {self.config.device} is not connected")
            self._run_adb(
                ["-s", self._device, "forward", f"tcp:{ANDROID_HOST_PORT}", f"tcp:{ANDROID_HOST_PORT}"],
                15.0,
            )
            self._forward_active = True
            endpoint = ANDROID_HOST_ENDPOINT
        self._wait_healthy(endpoint)
        self.endpoint = endpoint
        return AndroidSessionHandle(endpoint=endpoint, device=self._device, use_forward=use_forward)

    def stop(self) -> None:
        """Stop the host cleanly (service.shutdown) and remove adb forward."""
        if self._stopped:
            return
        self._stopped = True
        try:
            client = NeonClient.connect(
                ANDROID_HOST_ENDPOINT,
                origin="neon3-python-android",
                kind="cli",
                timeout_seconds=3.0,
                allow_non_loopback=True,
            )
            client.call("wgpu-runtime", "service.shutdown", {}, raise_for_status=False)
        except Exception:  # noqa: BLE001 - host may already be gone
            pass
        if self._forward_active:
            try:
                self._run_adb(["-s", self._device, "forward", "--remove", f"tcp:{ANDROID_HOST_PORT}"], 10.0)
            except Exception:  # noqa: BLE001
                pass
            self._forward_active = False
