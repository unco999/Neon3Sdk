# -*- coding: utf-8 -*-
p = r'D:\Neon3\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
if 'crates/neon3-runtime' not in d:
    d = d.replace('    "crates/neon-cli",', '    "crates/neon-cli",\n    "crates/neon3-runtime",')
    open(p, 'wb').write(d.encode('utf-8'))
    print('added member')
else:
    print('already present')
