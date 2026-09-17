# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''                eprintln!(
                    "[editor-renderer] layout probe: viewport={:?} scale={} raster_px={} row_height={} bounds={:?} lines={}",
                    self.viewport_logical_size,
                    self.scale_factor,
                    raster_px,
                    row_height,
                    visual.bounds,
                    state.lines.len()
                );'''
new = '''                eprintln!(
                    "[editor-renderer] layout probe: viewport={:?} raster_px={} row_height={} bounds={:?} lines={}",
                    self.viewport_logical_size,
                    raster_px,
                    row_height,
                    visual.bounds,
                    state.lines.len()
                );'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('probe fixed')
