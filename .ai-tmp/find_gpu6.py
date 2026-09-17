# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
for kw in ['window_gpu', 'WindowGpu::']:
    idx = 0
    while True:
        i = d.find(kw, idx)
        if i < 0:
            break
        print(d[:i].count('\n') + 1, ':', d[max(0,i-100):i+80].replace('\n', ' ')[:170])
        idx = i + 1
