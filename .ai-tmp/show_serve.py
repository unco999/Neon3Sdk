# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# in run_with_server: the RPC serve_until block
i = d.find('fn run_with_server')
seg = d[i:i+60000]
j = seg.find('serve_until')
print(seg[j-400:j+1600])
