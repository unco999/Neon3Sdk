# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs', 'rb').read().decode('utf-8').replace('\r\n', '\n')
for m in re.finditer(r'"(code-editor-demo-register-[^"]+)"', d):
    print(m.group(1))
