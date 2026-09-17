# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
# 1) probe block: LOG_ONCE leftovers at 414
old1 = '''            if !LOG_ONCE.swap(true, std::sync::atomic::Ordering::Relaxed) {
                ;
            }
            if row_height <= 0.0 || visual.bounds.width <= 0.0 || visual.bounds.height <= 0.0 {'''
new1 = '''            if row_height <= 0.0 || visual.bounds.width <= 0.0 || visual.bounds.height <= 0.0 {'''
assert old1 in d, 'a1 missing'
d = d.replace(old1, new1, 1)

# 2) editor_at_pointer leftovers: `;` lines inside skip blocks
old2 = '''            let visual = &self.sampled[index];
            if visual.world_depth.is_some() {
                ;
                continue;
            }
            if self.plan[index].instance_index.is_none() {
                ;
                continue;
            }'''
new2 = '''            let visual = &self.sampled[index];
            if visual.world_depth.is_some() {
                continue;
            }
            if self.plan[index].instance_index.is_none() {
                continue;
            }'''
assert old2 in d, 'a2 missing'
d = d.replace(old2, new2, 1)

# 3) editor_pointer_press leftover `;` after fn
old3 = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        ;
        let Some(path) = self.editor_at_pointer(pointer) else {'''
new3 = '''    pub(crate) fn editor_pointer_press(&mut self, pointer: [f32; 2]) -> bool {
        let Some(path) = self.editor_at_pointer(pointer) else {'''
assert old3 in d, 'a3 missing'
d = d.replace(old3, new3, 1)

open(p, 'w', newline='\n').write(d)
print('semicolons cleaned')
