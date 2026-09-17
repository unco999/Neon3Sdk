# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\cli.py', 'rb').read().decode('utf-8')
# 找进程启动清单
i = d.find('neon-eventd.exe')
print('--- spawn block ---')
print(d[max(0, i - 900):i + 1400])
