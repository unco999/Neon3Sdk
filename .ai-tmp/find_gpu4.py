# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
lines = d.split('\n')
# run_with_server body: search for window_gpu( call
for i in range(4700, 5600):
    l = lines[i]
    if 'window_gpu(' in l or 'gpu = ' in l and 'Some' in l:
        print(f'{i+1}: {l[:160]}')
