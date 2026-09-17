# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
lines = d.split('\n')
i = 12185
for j in range(i-1, i+60):
    print(f'{j+1}: {lines[j][:160]}')
