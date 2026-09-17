# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-editor\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = 'repository = "https://github.com/unco999/neon-editor"'
new = 'repository = "https://github.com/unco999/Neon3-CiJian"'
assert old in d, 'repo anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('repository updated')
