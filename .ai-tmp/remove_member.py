# -*- coding: utf-8 -*-
"""Remove neon-editor-core from the workspace members list (CRLF-aware)."""
p = r'D:\Neon3\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
d2 = d.replace('    "crates/neon-editor-core",\n', '')
open(p, 'wb').write(d2.encode('utf-8'))
print('member removed:', 'neon-editor-core' not in d2)
