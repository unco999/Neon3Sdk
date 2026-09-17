# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# WindowedRuntime struct + whether it has its own handle()
i = d.find('pub struct WindowedRuntime')
print(d[i:i+700])
print('==== handle methods ====')
for m in __import__('re').finditer(r'fn handle\(&mut self, request', d):
    print('  ', d[:m.start()].count('\n') + 1)
