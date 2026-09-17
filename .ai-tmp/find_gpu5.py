# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# find all 'window_gpu(' occurrences with line numbers
idx = 0
while True:
    i = d.find('window_gpu(', idx)
    if i < 0:
        break
    print(d[:i].count('\n') + 1, ':', d[max(0,i-80):i+60].replace('\n', ' ')[:150])
    idx = i + 1
