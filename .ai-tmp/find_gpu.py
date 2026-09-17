# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# where does WindowedRuntime create its gpu (UiWgpuRenderer)?
for m in re.finditer(r'[^\n]*(new_gpu|create_renderer|Renderer::|UiWgpuRenderer|gpu:)[^\n]*', d):
    line = d[:m.start()].count('\n') + 1
    print(f'  {line}: {m.group(0).strip()[:150]}')
