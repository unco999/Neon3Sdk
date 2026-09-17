# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
lines = d.split('\n')
# find where gpu: Some(window_gpu(...)) is set inside run_with_server (after 4000)
for i in range(6250, 6340):
    l = lines[i]
    if 'gpu' in l or 'window_gpu' in l or 'init' in l:
        print(f'{i+1}: {l[:150]}')
