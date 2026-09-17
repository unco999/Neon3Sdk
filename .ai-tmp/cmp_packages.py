# -*- coding: utf-8 -*-
import re

d = open(r'D:\Neon3\crates\neon-ui-runtime\src\editor_component.rs', 'rb').read().decode('utf-8').replace('\r\n', '\n')
for kw in ['FX_TYPE_IN_PACKAGE', 'FX_DELETE_PACKAGE']:
    i = d.find(kw)
    print(kw, ':', d[i:i+130].split('\n')[0])

print('=== demo registered packages ===')
dd = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs', 'rb').read().decode('utf-8').replace('\r\n', '\n')
for m in re.finditer(r'register[^\n"]*"([^"]+)"', dd):
    print(m.group(1))
