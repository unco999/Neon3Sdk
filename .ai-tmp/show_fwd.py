# -*- coding: utf-8 -*-
d = open(r'D:\Neon3\crates\neon-ui-runtime\src\lib.rs', 'rb').read().decode('utf-8')
i = d.find('pub fn serve_forwarder')
print(d[i-300:i+3000])
