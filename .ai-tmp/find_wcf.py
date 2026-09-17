# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
for m in re.finditer(r'WindowCommand::Fragments', d):
    line = d[:m.start()].count('\n') + 1
    print(line, ':', d[max(0, m.start()-60):m.start()+60].replace('\n', ' ')[:140])
