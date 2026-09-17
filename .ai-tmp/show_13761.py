# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
lines = d.split('\n')
# 13761 / 13970 context (windowed fragment insert)
for start in (13755, 13964):
    print('==== line', start+1)
    for i in range(start-6, start+8):
        print(f'{i+1}: {lines[i][:150]}')
