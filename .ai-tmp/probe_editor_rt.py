# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-editor-runtime\src\lib.rs', 'rb').read().decode('utf-8')
print('size', len(d))
for m in re.finditer(r'.{60}(port|PORT|bind|listen|3910\d|127\.0\.0\.1).{80}', d, re.S):
    print('...', m.group(0).replace('\n', ' '))
