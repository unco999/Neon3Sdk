# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# WindowCommand enum variants
i = d.find('enum WindowCommand')
print(d[i:i+600])
