# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''    pub(crate) fn editor_at_pointer(&self, pointer: [f32; 2]) -> Option<String> {
        for index in (0..self.plan.len()).rev() {
            let path = &self.plan[index].id;
            if !self.editors.contains_key(path) {
                continue;
            }
            let visual = &self.sampled[index];
            if visual.world_depth.is_some() {
                continue;
            }
            if self.plan[index].instance_index.is_none() {
                continue;
            }
            if contains(visual.bounds, pointer) {
                return Some(path.clone());
            }
        }
        None
    }'''
new = '''    pub(crate) fn editor_at_pointer(&self, pointer: [f32; 2]) -> Option<String> {
        for index in (0..self.plan.len()).rev() {
            let path = &self.plan[index].id;
            if !self.editors.contains_key(path) {
                continue;
            }
            eprintln!(
                "[editor-renderer] hit-check idx={index} path={path} pointer={pointer:?} instance={:?} bounds={:?}",
                self.plan[index].instance_index, self.sampled[index].bounds
            );
            let visual = &self.sampled[index];
            if visual.world_depth.is_some() {
                eprintln!("[editor-renderer] hit-skip world_depth");
                continue;
            }
            if self.plan[index].instance_index.is_none() {
                eprintln!("[editor-renderer] hit-skip no instance");
                continue;
            }
            if contains(visual.bounds, pointer) {
                return Some(path.clone());
            }
            eprintln!("[editor-renderer] hit-skip bounds");
        }
        None
    }'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('hit log added')
