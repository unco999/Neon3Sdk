# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# 1) LOG_ONCE leftover
old1 = '''            let row_height = editor_row_height(font, declaration, state.font_scale);
            static LOG_ONCE: std::sync::atomic::AtomicBool =
                std::sync::atomic::AtomicBool::new(false);
            if row_height <= 0.0'''
new1 = '''            let row_height = editor_row_height(font, declaration, state.font_scale);
            if row_height <= 0.0'''
assert old1 in d, 'a1 missing'
d = d.replace(old1, new1, 1)

# 2) stray `;` after external presentations overwrite
old2 = '''                    *existing = presentation.clone();
                }
            }
            ;
        }'''
new2 = '''                    *existing = presentation.clone();
                }
            }
        }'''
assert old2 in d, 'a2 missing'
d = d.replace(old2, new2, 1)

# 3) stray `;` in editor_at_pointer after editors check
old3 = '''            if !self.editors.contains_key(path) {
                continue;
            }
            ;
            let visual = &self.sampled[index];'''
new3 = '''            if !self.editors.contains_key(path) {
                continue;
            }
            let visual = &self.sampled[index];'''
assert old3 in d, 'a3 missing'
d = d.replace(old3, new3, 1)

# 4) stray `;` before closing editor_at_pointer loop
old4 = '''            if in_panel || in_content {
                return Some(path.clone());
            }
            ;
        }
        None
    }'''
new4 = '''            if in_panel || in_content {
                return Some(path.clone());
            }
        }
        None
    }'''
assert old4 in d, 'a4 missing'
d = d.replace(old4, new4, 1)

# 5) leftover pointer_press log
old5 = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        let Some(path) = self.editor_at_pointer(pointer) else {
            eprintln!("[editor-renderer] pointer_press: no editor at pointer");
            return false;
        };'''
new5 = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        let Some(path) = self.editor_at_pointer(pointer) else {
            return false;
        };'''
assert old5 in d, 'a5 missing'
d = d.replace(old5, new5, 1)

open(p, 'w', newline='\n').write(d)
print('leftovers cleaned')
