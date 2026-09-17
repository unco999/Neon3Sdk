# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''                    let action = match &event.intent {
                        UiIntent::Invoke { action, .. } => action.as_str(),
                        _ => "",
                    };'''
new = '''                    let action = match &event.intent {
                        UiIntent::Invoke { action, .. } => action.as_str(),
                    };'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('unreachable pattern fixed')
