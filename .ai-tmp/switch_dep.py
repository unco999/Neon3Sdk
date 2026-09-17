# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-editor-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
d2 = d.replace('neon-editor-core = { version = "0.2.10", path = "../neon-editor-core" }',
               'neon-editor = { version = "0.1", path = "D:/neon-editor" }')
open(p, 'wb').write(d2.encode('utf-8'))
print('editor-runtime: neon-editor =', 'neon-editor =' in d2, '| core left:', 'neon-editor-core' in d2)

p = r'D:\Neon3\crates\neon-wgpu-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
d2 = d.replace('neon-editor-core = { version = "0.2.0", path = "../neon-editor-core" }',
               'neon-editor = { version = "0.1", path = "D:/neon-editor" }')
open(p, 'wb').write(d2.encode('utf-8'))
print('wgpu: neon-editor =', 'neon-editor =' in d2, '| core left:', 'neon-editor-core' in d2)
