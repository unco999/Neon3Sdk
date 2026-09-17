# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''pub(crate) mod editor_renderer;
pub(crate) mod editor_theme;
pub use editor_theme::{EditorTheme, UI_COLOR_KEYS, editor_theme_from};
'''
new = '''pub(crate) mod editor_renderer;
pub(crate) mod editor_theme;
'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('unused import removed')
