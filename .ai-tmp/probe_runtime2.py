# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\runtime.py', 'rb').read().decode('utf-8')
for kw in ['neon-editor-runtime', 'editor-runtime', 'editor', '43100', '3910']:
    n = d.count(kw)
    print(kw, n)
    if n:
        i = d.find(kw)
        print('   ', d[max(0, i - 150):i + 200].replace('\n', ' '))
