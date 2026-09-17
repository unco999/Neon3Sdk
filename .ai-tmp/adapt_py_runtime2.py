# -*- coding: utf-8 -*-
"""Full CRLF-safe rewrite of the python-sdk RuntimeSession consumption of the
unified single-exe neon3-runtime (asset .exe, one `serve` process)."""
p = r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\runtime.py'
d = open(p, 'rb').read().decode('utf-8')
d = d.replace('\r\n', '\n')

# 1) availability
old = '''def _runtime_available(root: Path) -> bool:
    return all((root / "target" / "release" / name).is_file() for name in (
        "neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"
    ))'''
new = '''def _runtime_available(root: Path) -> bool:
    return (root / "target" / "release" / "neon3-runtime.exe").is_file()'''
if old in d:
    d = d.replace(old, new); print('availability: replaced')
else:
    print('availability: pattern missing')

# 2) download
old = '''def _download_runtime(root: Path, version: str) -> None:
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
        archive.unlink(missing_ok=True)'''
new = '''def _download_runtime(root: Path, version: str) -> None:
    executable_dir = root / "target" / "release"
    executable_dir.mkdir(parents=True, exist_ok=True)
    asset = NEON3_RUNTIME_ASSET_TEMPLATE.format(version=version)
    url = f"https://github.com/{NEON3_RUNTIME_REPOSITORY}/releases/download/{version}/{asset}"
    destination = executable_dir / "neon3-runtime.exe"
    with urllib.request.urlopen(url, timeout=180) as response, destination.open("wb") as stream:
        stream.write(response.read())'''
if old in d:
    d = d.replace(old, new); print('download: replaced')
else:
    print('download: pattern missing')

# 3) runtime_dir discovery
old = '''        runtime_dir = next(
            (
                root / "target" / profile
                for profile in profiles
                if all((root / "target" / profile / name).is_file() for name in ("neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"))
            ),
            None,
        )'''
new = '''        runtime_dir = next(
            (
                root / "target" / profile
                for profile in profiles
                if (root / "target" / profile / "neon3-runtime.exe").is_file()
            ),
            None,
        )'''
if old in d:
    d = d.replace(old, new); print('runtime_dir: replaced')
else:
    print('runtime_dir: pattern missing')

# 4) specs -> single serve process
old = '''        specs = [
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
            raise'''
new = '''        runtime_args = [
            "serve",
            "--eventd", self.config.endpoints.eventd,
            "--ui", self.config.endpoints.ui,
            "--wgpu", self.config.endpoints.wgpu,
            "--editor", self.config.domain_endpoint,
        ]
        if self.config.mode is not RuntimeMode.HEADLESS:
            runtime_args.append("--window")
        executable = runtime_dir / "neon3-runtime.exe"
        try:
            if not executable.is_file():
                raise FileNotFoundError(f"Neon3 executable not found: {executable}")
            process = subprocess.Popen([str(executable), *runtime_args], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            self.processes.append(("runtime", process))
            self.wait_ready()
        except Exception:
            self.stop()
            raise'''
if old in d:
    d = d.replace(old, new); print('specs: replaced')
else:
    print('specs: pattern missing')

# 5) drop zipfile import
if d.count('zipfile') == 0 and 'import zipfile' in d:
    d = d.replace('import zipfile\n', ''); print('zipfile import: removed')

open(p, 'wb').write(d.replace('\n', '\r\n').encode('utf-8'))
print('FINAL: neon-eventd refs:', d.count('neon-eventd.exe'), '| neon3-runtime refs:', d.count('neon3-runtime.exe'), '| zip refs:', d.count('zip'))
