# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
i = d.find('fn run_with_server')
seg = d[i:i+60000]
for m in re.finditer(r'[^\n]*(serve_until|BlockingRpcServer|\.handle\(|RpcServer)[^\n]*', seg):
    print('  ', m.group(0).strip()[:150])
