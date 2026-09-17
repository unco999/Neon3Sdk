# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
if 'neon-editor' in d:
    lines = d.split('\n')
    kept = [l for l in lines if 'neon-editor' not in l]
    d = '\n'.join(kept)
    open(p, 'w', newline='\n').write(d)
    print('neon-editor dep removed from wgpu-runtime')
else:
    print('no neon-editor dep found')
