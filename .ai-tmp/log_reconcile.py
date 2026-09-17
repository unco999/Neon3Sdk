# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''                if let Some(path) = path
                    && let Some((_, existing)) = desired.get_mut(&path)
                {
                    *existing = presentation.clone();
                }
            }
        }'''
new = '''                if let Some(path) = path
                    && let Some((_, existing)) = desired.get_mut(&path)
                {
                    *existing = presentation.clone();
                }
            }
            eprintln!(
                "[editor-renderer] reconcile: desired={} external_presentations={} mirrors={}",
                desired.len(),
                external.len(),
                self.editors.len()
            );
        }'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('log added')
