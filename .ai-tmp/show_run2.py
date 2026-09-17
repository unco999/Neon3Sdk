# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
i = d.find('fn run_with_server(')
j = d.find('\n    }\n', i)
print(d[i:j])
