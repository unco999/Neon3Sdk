# -*- coding: utf-8 -*-
"""Adapt python-sdk runtime.py to the unified single-exe neon3-runtime.

- asset: download neon3-runtime-windows-x86_64-<version>.exe (no zip)
- availability: check neon3-runtime.exe
- start: one process `neon3-runtime serve [--window] [--eventd ...] [--ui ...] [--wgpu ...] [--editor ...]`
"""
p = r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\runtime.py'
d = open(p, 'rb').read().decode('utf-8')
orig = d

# 1) asset template: exe instead of zip
d = d.replace(
    'NEON3_RUNTIME_ASSET_TEMPLATE = "neon3-runtime-windows-x86_64-{version}.zip"',
    'NEON3_RUNTIME_ASSET_TEMPLATE = "neon3-runtime-windows-x86_64-{version}.exe"',
)

# 2) availability check: single binary
d = d.replace(
    '''def _runtime_available(root: Path) -> bool:
    return all((root / "target" / "release" / name).is_file() for name in (
        "neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"
    ))''',
    '''def _runtime_available(root: Path) -> bool:
    return (root / "target" / "release" / "neon3-runtime.exe").is_file()''',
)

# 3) download: fetch the exe straight into target/release
d = d.replace(
    '''def _download_runtime(root: Path, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    asset = NEON3_RUNTIME_ASSET_TEMPLATE.format(version=version)
    archive = root.parent / f"{asset}.download"
    url = f"https://github.com/{NEON3_RUNTIME_REPOSITORY}/releases/download/{version}/{asset}"
    try:
        with urllib.request.urlopen(url, timeout=180) as response, archive.open("wb") as stream:
            stream.write(response.read())
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root)
    finally:
        archive.unlink(missing_ok=True)''',
    '''def _download_runtime(root: Path, version: str) -> None:
    executable_dir = root / "target" / "release"
    executable_dir.mkdir(parents=True, exist_ok=True)
    asset = NEON3_RUNTIME_ASSET_TEMPLATE.format(version=version)
    url = f"https://github.com/{NEON3_RUNTIME_REPOSITORY}/releases/download/{version}/{asset}"
    destination = executable_dir / "neon3-runtime.exe"
    with urllib.request.urlopen(url, timeout=180) as response, destination.open("wb") as stream:
        stream.write(response.read())''',
)

# 4) start: one neon3-runtime serve process
d = d.replace(
    '''        profiles = (requested_profile,) if requested_profile != "auto" else ("release", "debug")
        runtime_dir = next(
            (
                root / "target" / profile
                for profile in profiles
                if all((root / "target" / profile / name).is_file() for name in ("neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"))
            ),
            None,
        )''',
    '''        profiles = (requested_profile,) if requested_profile != "auto" else ("release", "debug")
        runtime_dir = next(
            (
                root / "target" / profile
                for profile in profiles
                if (root / "target" / profile / "neon3-runtime.exe").is_file()
            ),
            None,
        )''',
)

d = d.replace(
    '''        if can_download:
            _download_runtime(root, selected_runtime_version)
            runtime_dir = root / "target" / "release"
        if runtime_dir is None:
            raise FileNotFoundError(f"Neon3 release/debug binaries not found under {root}")
        specs = [
            ("eventd", runtime_dir / "neon-eventd.exe", ("--server", self.config.endpoints.eventd, "1")),
            ("wgpu-runtime", runtime_dir / "neon-wgpu-runtime.exe", self.config.wgpu_arguments),
            ("ui-runtime", runtime_dir / "neon-ui-runtime.exe", ("--forward-server", self.config.endpoints.ui, self.config.endpoints.wgpu, self.config.domain_endpoint, "--eventd", self.config.endpoints.eventd)),
        ]''',
    '''        if can_download:
            _download_runtime(root, selected_runtime_version)
            runtime_dir = root / "target" / "release"
        if runtime_dir is None:
            raise FileNotFoundError(f"Neon3 release/debug binaries not found under {root}")
        runtime_args = [
            "serve",
            "--eventd", self.config.endpoints.eventd,
            "--ui", self.config.endpoints.ui,
            "--wgpu", self.config.endpoints.wgpu,
            "--editor", self.config.domain_endpoint,
        ]
        if self.config.mode is not RuntimeMode.HEADLESS:
            runtime_args.append("--window")
        specs = [
            ("runtime", runtime_dir / "neon3-runtime.exe", tuple(runtime_args)),
        ]''',
)

open(p, 'wb').write(d.encode('utf-8'))
print('changed:', d != orig)
print('zip refs left:', d.count('zipfile'), d.count('.zip'))
