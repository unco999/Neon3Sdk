# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-ui-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
old = 'neon-world-bridge = { version = "0.2.0", path = "../neon-world-bridge" }'
new = old + '\nneon-editor = { version = "0.1", path = "D:/neon-editor" }'
assert old in d
d = d.replace(old, new)
open(p, 'w', newline='\n').write(d)
print('dep added')

p2 = r'D:\Neon3\crates\neon-ui-runtime\src\lib.rs'
d2 = open(p2, 'rb').read().decode('utf-8')
assert 'pub use nui_state_machine' in d2
d2 = d2.replace('pub use nui_state_machine', 'pub mod editor_component;\npub use nui_state_machine', 1)
open(p2, 'w', newline='\n').write(d2)
print('mod added')
