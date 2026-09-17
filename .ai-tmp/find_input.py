# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
pats = ['ui.input', 'input.key', 'InputEvent', 'handle_injected', 'injected_key', 'editor_handle_key', 'inject_keyboard']
for pat in pats:
    for m in re.finditer(re.escape(pat), d):
        line = d[:m.start()].count('\n') + 1
        ctx = d[max(0, m.start()-40):m.start()+60].replace('\n', ' ')
        print(f'  {line}: ...{ctx}...')
        if line > 20000:
            break
