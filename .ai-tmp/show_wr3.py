# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# find WindowedRuntime::new body
m = re.search(r'impl WindowedRuntime \{\n\s*pub fn new\(', d)
if not m:
    # try another pattern
    for mm in re.finditer(r'fn new\(epoch: u64\) -> Self', d):
        line = d[:mm.start()].count('\n') + 1
        print('new at line', line)
        print(d[mm.start()-200:mm.start()+600])
        break
