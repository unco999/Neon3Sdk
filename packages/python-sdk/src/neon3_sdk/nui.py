"""Bridges for canonical NUI Flow programs shipped by Neon3."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .models import AssetRef


@dataclass(frozen=True)
class GallerySubmission:
    endpoint: str
    executable: Path
    return_code: int
    stdout: str
    stderr: str


class ComponentGallery:
    """Submit Neon3's complete ``imgui-component-gallery.nui`` via its canonical compiler."""

    def __init__(self, neon_root: str | Path, executable: str | Path | None = None) -> None:
        self.neon_root = Path(neon_root)
        self.executable = Path(executable) if executable else self.neon_root / "target" / "debug" / "nui_flow_demo.exe"

    @property
    def source_path(self) -> Path:
        return self.neon_root / "tests" / "fixtures" / "ui" / "imgui-component-gallery.nui"

    def submit(self, endpoint: str, image_asset: AssetRef, *, timeout_seconds: float = 15.0) -> GallerySubmission:
        if not self.source_path.is_file():
            raise FileNotFoundError(f"component gallery source was not found: {self.source_path}")
        if not self.executable.is_file():
            raise FileNotFoundError(
                f"canonical NUI compiler/demo was not found: {self.executable}. Build Neon3 with cargo build -p neon-ui-runtime --bin nui_flow_demo."
            )
        completed = subprocess.run(
            [str(self.executable), "component-gallery", endpoint, json.dumps(image_asset.to_wire(), separators=(",", ":"))],
            cwd=self.neon_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=False,
        )
        submission = GallerySubmission(endpoint, self.executable, completed.returncode, completed.stdout, completed.stderr)
        if completed.returncode != 0:
            raise RuntimeError(f"component gallery submission failed ({completed.returncode}): {completed.stderr.strip()}")
        return submission
