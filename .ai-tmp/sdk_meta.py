# -*- coding: utf-8 -*-
import json, os, re

print('### node-sdk package.json')
d = json.loads(open(r'D:\Neon3Sdk\packages\node-sdk\package.json', 'rb').read().decode('utf-8'))
for k in ['name', 'version', 'description', 'main', 'types', 'files', 'license', 'repository', 'publishConfig']:
    v = d.get(k)
    print(' ', k, ':', json.dumps(v, ensure_ascii=False)[:220] if v is not None else '(missing)')

print()
print('### python-sdk pyproject.toml')
t = open(r'D:\Neon3Sdk\packages\python-sdk\pyproject.toml', 'rb').read().decode('utf-8')
print(t[:1600])

print()
print('### rust-sdk Cargo.toml (name/desc/license)')
t = open(r'D:\Neon3Sdk\packages\rust-sdk\Cargo.toml', 'rb').read().decode('utf-8')
for line in t.splitlines()[:25]:
    print(' ', line)

print()
print('### c-sdk Cargo.toml head')
t = open(r'D:\Neon3Sdk\packages\c-sdk\Cargo.toml', 'rb').read().decode('utf-8')
for line in t.splitlines()[:25]:
    print(' ', line)

print()
print('### cpp-sdk contents')
root = r'D:\Neon3Sdk\packages\cpp-sdk'
for f in sorted(os.listdir(root)):
    print(' ', f)
