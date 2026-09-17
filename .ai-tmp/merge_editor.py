# -*- coding: utf-8 -*-
import io

# 1) workspace members
p = r'D:\Neon3\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''    "crates/neon-editor-runtime",
    "crates/neon-wgpu-runtime",'''
new = '''    "crates/neon-editor-runtime",
    "crates/neon-editor",
    "crates/neon-wgpu-runtime",'''
assert old in d, 'workspace anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('workspace member added')

# 2) neon-ui-runtime dep
p = r'D:\Neon3\crates\neon-ui-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = 'neon-editor = { version = "0.1", path = "D:/neon-editor" }'
new = 'neon-editor = { version = "0.1", path = "../neon-editor" }'
assert old in d, 'ui-runtime dep anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('ui-runtime dep updated')

# 3) neon-editor-runtime dep
p = r'D:\Neon3\crates\neon-editor-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = 'neon-editor = { version = "0.1", path = "D:/neon-editor" }'
new = 'neon-editor = { version = "0.1", path = "../neon-editor" }'
assert old in d, 'editor-runtime dep anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('editor-runtime dep updated')
