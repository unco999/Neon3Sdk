# -*- coding: utf-8 -*-
p = r'D:\Neon3Sdk\packages\c-sdk\Cargo.toml'
t = open(p, 'rb').read().decode('utf-8')
old = 'neon3-sdk = { path = "../rust-sdk" }'
new = 'neon3-sdk = "0.1.7"'
if old in t:
    t = t.replace(old, new)
    open(p, 'wb').write(t.encode('utf-8'))
    print('c-sdk dependency -> neon3-sdk = "0.1.7"')
else:
    print('pattern missing:', 'neon3-sdk' in t, repr([l for l in t.splitlines() if 'neon3-sdk' in l][:3]))
