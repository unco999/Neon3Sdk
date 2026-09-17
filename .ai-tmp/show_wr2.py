# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# WindowedRuntime struct full + new()
i = d.find('pub struct WindowedRuntime')
j = d.find('\n}\n', i)
print(d[i:j+3])
k = d.find('impl WindowedRuntime')
l = d.find('pub fn new(', k)
print('==== new ====')
print(d[l-60:l+500])
