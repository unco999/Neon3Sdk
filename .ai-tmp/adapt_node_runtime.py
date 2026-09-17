# -*- coding: utf-8 -*-
"""Adapt node-sdk runtime.ts to the unified single-exe neon3-runtime."""
p = r'D:\Neon3Sdk\packages\node-sdk\src\runtime.ts'
d = open(p, 'rb').read().decode('utf-8')
orig = d

# 1) asset: exe
d = d.replace(
    'const NEON3_RUNTIME_ASSET = (version: string) => `neon3-runtime-windows-x86_64-${version}.zip`;',
    'const NEON3_RUNTIME_ASSET = (version: string) => `neon3-runtime-windows-x86_64-${version}.exe`;',
)

# 2) start(): one neon3-runtime serve process
d = d.replace(
    '''    this.executableDir = await this.findExecutableDir();
    const specs: Array<[string, string, string[]]> = [
      ["eventd", join(this.executableDir, "neon-eventd.exe"), ["--server", this.config.eventd, "1"]],
      ["wgpu", join(this.executableDir, "neon-wgpu-runtime.exe"), this.wgpuArgs()],
      ["ui", join(this.executableDir, "neon-ui-runtime.exe"), ["--forward-server", this.config.ui, this.config.wgpu, this.config.domain, "--eventd", this.config.eventd]],
    ];
    try {
      for (const [name, executable, args] of specs) {
        await access(executable);
        this.processes.push(spawn(executable, args, {
          cwd: this.config.neonRoot,
          stdio: "ignore",
          windowsHide: false,
          env: name === "wgpu" ? this.wgpuEnvironment() : process.env,
        }));
      }
      await this.waitReady();
    } catch (error) { await this.stop(); throw error; }
  }
  private wgpuArgs(): string[] { return this.config.mode === "headless" ? ["--headless-server", this.config.wgpu] : ["--window-server", this.config.wgpu, this.config.ui, "--eventd", this.config.eventd]; }''',
    '''    this.executableDir = await this.findExecutableDir();
    const runtimeArgs = [
      "serve",
      "--eventd", this.config.eventd,
      "--ui", this.config.ui,
      "--wgpu", this.config.wgpu,
      "--editor", this.config.domain,
    ];
    if (this.config.mode !== "headless") runtimeArgs.push("--window");
    const specs: Array<[string, string, string[]]> = [
      ["runtime", join(this.executableDir, "neon3-runtime.exe"), runtimeArgs],
    ];
    try {
      for (const [_name, executable, args] of specs) {
        await access(executable);
        this.processes.push(spawn(executable, args, {
          cwd: this.config.neonRoot,
          stdio: "ignore",
          windowsHide: false,
          env: this.runtimeEnvironment(),
        }));
      }
      await this.waitReady();
    } catch (error) { await this.stop(); throw error; }
  }
  private runtimeEnvironment(): NodeJS.ProcessEnv {
    const backdrop = this.config.windowBackdrop;
    if (!backdrop) return process.env;
    if (!Number.isFinite(backdrop.blurAmount ?? 0) || (backdrop.blurAmount ?? 0) < 0 || (backdrop.blurAmount ?? 0) > 64) throw new Error("windowBackdrop.blurAmount must be between 0 and 64");
    if (!Number.isFinite(backdrop.tintOpacity ?? 0) || (backdrop.tintOpacity ?? 0) < 0 || (backdrop.tintOpacity ?? 0) > 1) throw new Error("windowBackdrop.tintOpacity must be between 0 and 1");
    if (backdrop.tint !== undefined && !/^#[0-9a-fA-F]{6}$/.test(backdrop.tint)) throw new Error("windowBackdrop.tint must use #RRGGBB");
    return {
      ...process.env,
      NEON_WINDOW_BACKDROP: backdrop.kind,
      ...(backdrop.blurAmount !== undefined ? { NEON_BLUR_AMOUNT: String(backdrop.blurAmount) } : {}),
      ...(backdrop.tint !== undefined ? { NEON_BACKDROP_TINT: backdrop.tint } : {}),
      ...(backdrop.tintOpacity !== undefined ? { NEON_BACKDROP_TINT_OPACITY: String(backdrop.tintOpacity) } : {}),
    };
  }''',
)

# 3) findExecutableDir: single binary
d = d.replace(
    '''        await Promise.all(["neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"].map((name) => access(join(directory, name))));''',
    '''        await access(join(directory, "neon3-runtime.exe"));''',
)

# 4) ensureDownloadedRuntime: download exe straight into target/release
d = d.replace(
    '''    const cacheRoot = join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Neon3Sdk", "runtime", version);
    const binaries = ["neon-eventd.exe", "neon-wgpu-runtime.exe", "neon-ui-runtime.exe"];
    try { await Promise.all(binaries.map(name => access(join(cacheRoot, "target", "release", name)))); return cacheRoot; } catch { /* download below */ }
    await mkdir(cacheRoot, { recursive: true });
    const asset = NEON3_RUNTIME_ASSET(version);
    const archive = join(cacheRoot, `${asset}.download`);
    const url = `https://github.com/${NEON3_RUNTIME_REPOSITORY}/releases/download/${version}/${asset}`;
    const downloadTimeoutMs = Math.max(this.config.timeoutMs, 180000);
    await download(url, archive, downloadTimeoutMs);
    await new Promise<void>((resolve, reject) => execFile("tar", ["-xf", archive, "-C", cacheRoot], { timeout: downloadTimeoutMs }, error => error ? reject(error) : resolve()));
    await unlink(archive).catch(() => undefined);
    await Promise.all(binaries.map(name => access(join(cacheRoot, "target", "release", name))));
    return cacheRoot;''',
    '''    const cacheRoot = join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "Neon3Sdk", "runtime", version);
    const executablePath = join(cacheRoot, "target", "release", "neon3-runtime.exe");
    try { await access(executablePath); return cacheRoot; } catch { /* download below */ }
    await mkdir(join(cacheRoot, "target", "release"), { recursive: true });
    const asset = NEON3_RUNTIME_ASSET(version);
    const url = `https://github.com/${NEON3_RUNTIME_REPOSITORY}/releases/download/${version}/${asset}`;
    const downloadTimeoutMs = Math.max(this.config.timeoutMs, 180000);
    await download(url, executablePath, downloadTimeoutMs);
    await access(executablePath);
    return cacheRoot;''',
)

# 5) drop now-unused tar/execFile import if nothing else uses it
if d.count('execFile') == 0:
    d = d.replace('import { spawn, ChildProcess, execFile } from "node:child_process";',
                  'import { spawn, ChildProcess } from "node:child_process";')
if d.count('unlink') == 0:
    d = d.replace('import { access, mkdir, unlink, writeFile } from "node:fs/promises";',
                  'import { access, mkdir, writeFile } from "node:fs/promises";')

open(p, 'wb').write(d.encode('utf-8'))
print('changed:', d != orig)
print('neon-eventd refs:', d.count('neon-eventd.exe'))
print('execFile refs:', d.count('execFile'), '| unlink refs:', d.count('unlink'))
