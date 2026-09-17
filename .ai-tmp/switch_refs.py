# -*- coding: utf-8 -*-
"""Replace neon_editor_core:: with neon_editor:: in the two dependents."""
import glob, re, os

for crate in ['neon-editor-runtime', 'neon-wgpu-runtime']:
    for p in glob.glob(r'D:\Neon3\crates\%s\src\**\*.rs' % crate, recursive=True):
        d = open(p, 'rb').read().decode('utf-8')
        if 'neon_editor_core' not in d:
            continue
        d2 = d.replace('neon_editor_core::', 'neon_editor::')
        d2 = d2.replace('use neon_editor_core;', '')
        open(p, 'wb').write(d2.encode('utf-8'))
        print('rewrote', os.path.relpath(p, r'D:\Neon3'))
