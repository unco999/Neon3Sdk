# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
lines = d.split('\n')
for i in range(4005, 4025):
    print(f'{i+1}: {lines[i][:160]}')
