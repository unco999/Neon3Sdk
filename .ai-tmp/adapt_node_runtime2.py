# -*- coding: utf-8 -*-
p = r'D:\Neon3Sdk\packages\node-sdk\src\runtime.ts'
d = open(p, 'rb').read().decode('utf-8')

old = '''    this.executableDir = await this.findExecutableDir();
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
  private wgpuArgs(): string[] { return this.config.mode === "headless" ? ["--headless-server", this.config.wgpu] : ["--window-server", this.config.wgpu, this.config.ui, "--eventd", this.config.eventd]; }
  private wgpuEnvironment(): NodeJS.ProcessEnv {'''

new = '''    this.executableDir = await this.findExecutableDir();
    const runtimeArgs = [
      "serve",
      "--eventd", this.config.eventd,
      "--ui", this.config.ui,
      "--wgpu", this.config.wgpu,
      "--editor", this.config.domain,
    ];
    if (this.config.mode !== "headless") runtimeArgs.push("--window");
    const executable = join(this.executableDir, "neon3-runtime.exe");
    try {
      await access(executable);
      this.processes.push(spawn(executable, runtimeArgs, {
        cwd: this.config.neonRoot,
        stdio: "ignore",
        windowsHide: false,
        env: this.runtimeEnvironment(),
      }));
      await this.waitReady();
    } catch (error) { await this.stop(); throw error; }
  }
  private runtimeEnvironment(): NodeJS.ProcessEnv {'''

if old in d:
    d = d.replace(old, new)
    print('start() replaced')
else:
    print('PATTERN NOT FOUND - dumping around specs')
    i = d.find('const specs')
    print(d[i-200:i+700])

# remove stale import bindings if now unused
if d.count('execFile') == 0:
    d = d.replace('import { spawn, ChildProcess, execFile } from "node:child_process";',
                  'import { spawn, ChildProcess } from "node:child_process";')
if d.count('unlink') == 0:
    d = d.replace('import { access, mkdir, unlink, writeFile } from "node:fs/promises";',
                  'import { access, mkdir, writeFile } from "node:fs/promises";')

open(p, 'wb').write(d.encode('utf-8'))
print('neon-eventd refs:', d.count('neon-eventd.exe'), '| wgpuArgs refs:', d.count('wgpuArgs'))
