# -*- coding: utf-8 -*-
p = r'D:\Neon3\Cargo.toml'
d = open(p, 'rb').read().decode('utf-8')
if '[profile.release]' not in d:
    d += '\n[profile.release]\nlto = "fat"\ncodegen-units = 1\nstrip = true\n'
    open(p, 'wb').write(d.encode('utf-8'))
    print('profile.release added')
else:
    print('already present')
