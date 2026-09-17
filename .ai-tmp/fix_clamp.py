# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-ui-runtime\src\editor_component.rs'
d = open(p, 'rb').read().decode('utf-8')
old = '''        self.clamp_scroll_approx();
        self.revision += 1;
    }

    /// Approximate scroll clamping without font access (viewport in "rows"
    /// via the metric row height; horizontal uses the mono advance factor).
    pub fn clamp_scroll_approx(&mut self) {
        let row_height = self
            .declaration
            .font_size
            .max(1.0)
            * self.font_scale
            * 1.4;
        let content_height = self.core.buffer().line_count() as f32 * row_height;
        let _ = content_height;
    }

    fn scroll_caret_into_view('''
new = '''        self.revision += 1;
    }

    fn scroll_caret_into_view('''
assert old in d, 'clamp block not found'
d = d.replace(old, new)
open(p, 'w', newline='\n').write(d)
print('clamp removed')
