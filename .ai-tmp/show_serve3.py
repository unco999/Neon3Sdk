# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# run_with_server: full function boundaries
i = d.find('fn run_with_server(')
j = d.find('\n    }\n', i)
body = d[i:j]
print('run_with_server body lines:', body.count('\n'))
# look for RPC / event loop entry
for kw in ['RpcServer', 'serve_until', 'BlockingRpcServer', 'run_app', 'with_user_event', 'request', 'handle(']:
    k = body.find(kw)
    if k >= 0:
        print(kw, '->', body[:k].count('\n') + 1, ':', body[max(0,k-100):k+150].replace('\n', ' ')[:200])
