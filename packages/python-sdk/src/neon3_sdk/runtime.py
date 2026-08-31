"""Runtime mode and process configuration types for library users."""

from __future__ import annotations

import enum
import os
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from .client import NeonClient

NEON3_RUNTIME_VERSION = "v0.2.1"
NEON3_RUNTIME_REPOSITORY = "unco999/Neon3-CiJian"
NEON3_RUNTIME_ASSET = f"neon3-runtime-windows-x86_64-{NEON3_RUNTIME_VERSION}.zip"


def default_neon_root() -> Path:
    """Return an explicit root, local SDK bundle, or per-user runtime cache."""
    override = os.environ.get("NEON_ROOT")
    if override:
        return Path(override)
    sdk_root = Path(__file__).resolve().parents[4]
    local_release = sdk_root / "release"
    if _runtime_available(local_release):
        return local_release
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "Neon3Sdk" / "runtime" / NEON3_RUNTIME_VERSION


def _runtime_available(root: Path) -> bool:
    return all((root / "target" / "release" / name).is_file() for name in (
        "neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"
    ))


def _download_runtime(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    archive = root.parent / f"{NEON3_RUNTIME_ASSET}.download"
    url = f"https://github.com/{NEON3_RUNTIME_REPOSITORY}/releases/download/{NEON3_RUNTIME_VERSION}/{NEON3_RUNTIME_ASSET}"
    try:
        with urllib.request.urlopen(url, timeout=180) as response, archive.open("wb") as stream:
            stream.write(response.read())
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root)
    finally:
        archive.unlink(missing_ok=True)


class RuntimeMode(str, enum.Enum):
    WINDOWED = "windowed"
    HEADLESS = "headless"
    EXTERNAL_SURFACE = "external_surface"


@dataclass(frozen=True)
class RuntimeEndpoints:
    eventd: str = "127.0.0.1:39101"
    ui: str = "127.0.0.1:39102"
    wgpu: str = "127.0.0.1:39103"


@dataclass(frozen=True)
class RuntimeConfig:
    neon_root: str = field(default_factory=lambda: str(default_neon_root()))
    mode: RuntimeMode = RuntimeMode.WINDOWED
    endpoints: RuntimeEndpoints = RuntimeEndpoints()
    domain_endpoint: str = "127.0.0.1:39104"
    timeout_seconds: float = 15.0
    profile: str = field(default_factory=lambda: os.environ.get("NEON_PROFILE", "auto"))

    @property
    def wgpu_arguments(self) -> tuple[str, ...]:
        if self.mode is RuntimeMode.WINDOWED:
            return ("--window-server", self.endpoints.wgpu, self.endpoints.ui, "--eventd", self.endpoints.eventd)
        if self.mode is RuntimeMode.EXTERNAL_SURFACE:
            return ("--window-server", self.endpoints.wgpu, self.endpoints.ui, "--eventd", self.endpoints.eventd)
        return ("--headless-server", self.endpoints.wgpu)


class RuntimeSession:
    """Owns only processes started by the SDK and exposes deterministic lifecycle."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.processes: list[tuple[str, subprocess.Popen[str]]] = []

    def start(self) -> None:
        root = Path(self.config.neon_root)
        requested_profile = self.config.profile.lower()
        if requested_profile not in {"auto", "release", "debug"}:
            raise ValueError("profile must be auto, release, or debug")
        profiles = (requested_profile,) if requested_profile != "auto" else ("release", "debug")
        runtime_dir = next(
            (
                root / "target" / profile
                for profile in profiles
                if all((root / "target" / profile / name).is_file() for name in ("neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"))
            ),
            None,
        )
        can_download = (
            runtime_dir is None
            and self.config.profile.lower() in {"auto", "release"}
            and not os.environ.get("NEON_ROOT")
            and Path(self.config.neon_root) == default_neon_root()
        )
        if can_download:
            _download_runtime(root)
            runtime_dir = root / "target" / "release"
        if runtime_dir is None:
            raise FileNotFoundError(f"Neon3 release/debug binaries not found under {root}")
        specs = [
            ("eventd", runtime_dir / "neon-eventd.exe", ("--server", self.config.endpoints.eventd, "1")),
            ("wgpu-runtime", runtime_dir / "neon-wgpu-runtime.exe", self.config.wgpu_arguments),
            ("ui-runtime", runtime_dir / "neon-ui-runtime.exe", ("--forward-server", self.config.endpoints.ui, self.config.endpoints.wgpu, self.config.domain_endpoint, "--eventd", self.config.endpoints.eventd)),
        ]
        try:
            for name, executable, arguments in specs:
                if not executable.is_file():
                    raise FileNotFoundError(f"Neon3 executable not found: {executable}")
                process = subprocess.Popen([str(executable), *arguments], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
                self.processes.append((name, process))
            self.wait_ready()
        except Exception:
            self.stop()
            raise

    def wait_ready(self) -> None:
        deadline = time.monotonic() + self.config.timeout_seconds
        for target, endpoint in (("eventd", self.config.endpoints.eventd), ("wgpu-runtime", self.config.endpoints.wgpu), ("ui-runtime", self.config.endpoints.ui)):
            while time.monotonic() < deadline:
                try:
                    health = NeonClient.connect(endpoint, origin="neon3-sdk-runtime", timeout_seconds=0.5).health(target)
                    if health.status == "healthy":
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            else:
                raise TimeoutError(f"timed out waiting for {target} at {endpoint}")

    def stop(self) -> None:
        for _name, process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        self.processes.clear()

    def __enter__(self) -> "RuntimeSession":
        self.start()
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.stop()
