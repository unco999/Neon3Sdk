# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# 1) struct field
old1 = '''    /// Revision of the presentation this mirror was built from (the
    /// ui-runtime bumps it on every semantic change).
    pub presentation_revision: u64,
}'''
new1 = '''    /// Revision of the presentation this mirror was built from (the
    /// ui-runtime bumps it on every semantic change).
    pub presentation_revision: u64,
    /// Full rows region laid out by the renderer (x/y/width/height in the
    /// same logical space as the node bounds). The lowered panel bounds may
    /// not grow with content, so pointer hit-testing falls back to this.
    pub content_rect: UiBounds,
}'''
assert old1 in d, 'a1 missing'
d = d.replace(old1, new1, 1)

# 2) from_presentation init
old2 = '''            layout_dirty: true,
            presentation_revision: presentation.revision,
        }
    }
}'''
new2 = '''            layout_dirty: true,
            presentation_revision: presentation.revision,
            content_rect: UiBounds {
                x: 0.0,
                y: 0.0,
                width: 0.0,
                height: 0.0,
            },
        }
    }
}'''
assert old2 in d, 'a2 missing'
d = d.replace(old2, new2, 1)

# 3) layout_editors: compute content_rect before the visible-row loop
old3 = '''            let line_count = state.lines.len() as u32;
            let gutter_width = editor_gutter_width(declaration, line_count, state.font_scale);'''
new3 = '''            let line_count = state.lines.len() as u32;
            let gutter_width = editor_gutter_width(declaration, line_count, state.font_scale);
            state.content_rect = UiBounds {
                x: visual.bounds.x,
                y: visual.bounds.y - state.scroll_y,
                width: visual.bounds.width,
                height: (line_count as f32 * row_height).max(visual.bounds.height),
            };'''
assert old3 in d, 'a3 missing'
d = d.replace(old3, new3, 1)

# 4) editor_at_pointer: fall back to content_rect
old4 = '''            let visual = &self.sampled[index];
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
            eprintln!("[editor-renderer] hit-skip bounds");'''
new4 = '''            let visual = &self.sampled[index];
            if visual.world_depth.is_some() {
                eprintln!("[editor-renderer] hit-skip world_depth");
                continue;
            }
            if self.plan[index].instance_index.is_none() {
                eprintln!("[editor-renderer] hit-skip no instance");
                continue;
            }
            let in_panel = contains(visual.bounds, pointer);
            let in_content = self
                .editors
                .get(path)
                .is_some_and(|st| contains(st.content_rect, pointer));
            if in_panel || in_content {
                return Some(path.clone());
            }
            eprintln!(
                "[editor-renderer] hit-skip bounds panel={} content={:?}",
                in_panel, self.editors.get(path).map(|st| st.content_rect)
            );'''
assert old4 in d, 'a4 missing'
d = d.replace(old4, new4, 1)

open(p, 'w', newline='\n').write(d)
print('content_rect patch applied')
