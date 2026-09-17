# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# Where WindowGpu is constructed (ui: UiWgpuRenderer::new)
for m in re.finditer(r'UiWgpuRenderer::new|WindowGpu \{|WindowGpu::init|fn init_window_gpu|window_gpu', d):
    line = d[:m.start()].count('\n') + 1
    print(f'  {line}: {m.group(0)[:80]}')
