# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\cli.py', 'rb').read().decode('utf-8')
# 打印启动相关段落
for kw in ['neon-editor-runtime', 'editor', '43100', '39102', 'port', 'wgpu']:
    for m in re.finditer(re.escape(kw), d):
        s = m.start()
        seg = d[max(0, s - 120):s + 220].replace('\n', ' ')
        print(f'[{kw}] ...{seg}...')
        break
