# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        let Some(path) = self.editor_at_pointer(pointer) else {
            return false;
        };'''
new = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        eprintln!(
            "[editor-renderer] pointer_press at {pointer:?} editors={} plan={}",
            self.editors.len(),
            self.plan.len()
        );
        let Some(path) = self.editor_at_pointer(pointer) else {
            eprintln!("[editor-renderer] pointer_press: no editor at pointer");
            return false;
        };'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('pointer log added')
