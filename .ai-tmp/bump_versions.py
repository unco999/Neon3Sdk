# -*- coding: utf-8 -*-
"""Bump all SDK package versions 0.1.6 -> 0.1.7."""
import json, os, re

targets = [
    (r'D:\Neon3Sdk\packages\python-sdk\pyproject.toml', r'version = "0.1.6"', r'version = "0.1.7"'),
    (r'D:\Neon3Sdk\packages\rust-sdk\Cargo.toml', r'version = "0.1.6"', r'version = "0.1.7"'),
    (r'D:\Neon3Sdk\packages\c-sdk\Cargo.toml', r'version = "0.1.6"', r'version = "0.1.7"'),
]

# node: package.json + package-lock.json
pkg = r'D:\Neon3Sdk\packages\node-sdk\package.json'
j = json.loads(open(pkg, 'rb').read().decode('utf-8'))
j['version'] = '0.1.7'
open(pkg, 'wb').write(json.dumps(j, indent=2, ensure_ascii=False).encode('utf-8') + b'\n')
print('node package.json -> 0.1.7')
lock = r'D:\Neon3Sdk\packages\node-sdk\package-lock.json'
if os.path.exists(lock):
    jl = json.loads(open(lock, 'rb').read().decode('utf-8'))
    jl['version'] = '0.1.7'
    for k, v in jl.get('packages', {}).items():
        if v.get('version') == '0.1.6':
            v['version'] = '0.1.7'
    open(lock, 'wb').write(json.dumps(jl, indent=2, ensure_ascii=False).encode('utf-8') + b'\n')
    print('node package-lock.json -> 0.1.7')

for path, old, new in targets:
    t = open(path, 'rb').read().decode('utf-8')
    if old in t:
        t = t.replace(old, new)
        open(path, 'wb').write(t.encode('utf-8'))
        print(os.path.basename(path), '-> 0.1.7')
    else:
        print(os.path.basename(path), 'PATTERN MISSING')

# rust lock if any
for f in ['D:\\Neon3Sdk\\packages\\rust-sdk\\Cargo.lock', 'D:\\Neon3Sdk\\packages\\c-sdk\\Cargo.lock']:
    if os.path.exists(f):
        t = open(f, 'rb').read().decode('utf-8')
        t2 = re.sub(r'name = "neon3-sdk"\nversion = "0\.1\.6"', 'name = "neon3-sdk"\nversion = "0.1.7"', t)
        if t2 != t:
            open(f, 'wb').write(t2.encode('utf-8'))
            print(os.path.basename(f), 'lock bumped')
