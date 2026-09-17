# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# find UiWgpuRenderer construction inside run_with_server
i = d.find('fn run_with_server')
seg = d[i:i+40000]
for m in re.finditer(r'[^\n]*(UiWgpuRenderer|renderer:|ui =|self\.ui)[^\n]*', seg):
    print('  ', m.group(0).strip()[:140])
