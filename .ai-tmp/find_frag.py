# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# WindowCommand variants + where fragments map is mutated in WindowedRuntime
for m in re.finditer(r'[^\n]*(enum WindowCommand|SubmitFragment|fragments\.insert|fragments\.remove)[^\n]*', d):
    print('  ', d[:m.start()].count('\n') + 1, ':', m.group(0).strip()[:150])
