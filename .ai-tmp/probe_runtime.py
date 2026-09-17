# -*- coding: utf-8 -*-
import re, glob, os

# 1) runtime source bins
d = open(r'D:\Neon3Sdk\.cache\neon3\source\Cargo.toml', 'rb').read().decode('utf-8')
print('=== source Cargo.toml names ===')
for m in re.finditer(r'name = "([^"]+)"', d):
    print(' ', m.group(1))

# 2) python sdk runtime spawn hints
print('=== python spawn hints ===')
for f in glob.glob(r'D:\Neon3Sdk\packages\python-sdk\src\neon3_sdk\*.py'):
    d = open(f, 'rb').read().decode('utf-8')
    hits = re.findall(r'([\w./\\-]+\.exe|43100|39101|--[a-z_]+ \d+)', d)
    if hits:
        print(' ', os.path.basename(f), sorted(set(hits)))
