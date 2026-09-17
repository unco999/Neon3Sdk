# -*- coding: utf-8 -*-
import re
h = open(r'D:\Neon3Sdk\packages\c-sdk\include\neon3.h', 'rb').read().decode('utf-8')
for m in re.finditer(r'#define\s+(NEON3_(?:METHOD|SEMANTIC|EVENT|SERVICE)_\w+)\s+"([^"]+)"', h):
    print(m.group(1), '=', m.group(2))
