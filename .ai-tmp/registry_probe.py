# -*- coding: utf-8 -*-
import json, urllib.request, subprocess

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'probe'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        return f'ERR: {e}'

print('### pypi neon3-sdk')
import re
r = get('https://pypi.org/pypi/neon3-sdk/json')
if r.startswith('{'):
    j = json.loads(r)
    print(' latest:', j['info']['version'], '| versions:', list(j['releases'].keys()))
else:
    print(r[:120])

print('### npm @neon3/sdk')
r = get('https://registry.npmjs.org/@neon3%2Fsdk')
if r.startswith('{'):
    j = json.loads(r)
    print(' dist-tags:', j.get('dist-tags'))
    print(' versions:', list(j.get('versions', {}).keys()))
else:
    print(r[:120])

print('### crates.io neon3-sdk')
r = get('https://crates.io/api/v1/crates/neon3-sdk')
if r.startswith('{'):
    j = json.loads(r)
    print(' max_version:', j['crate'].get('max_version'), '| versions:', [v['num'] for v in j.get('versions', [])][:8])
else:
    print(r[:120])

print('### crates.io neon3-c')
r = get('https://crates.io/api/v1/crates/neon3-c')
if r.startswith('{'):
    j = json.loads(r)
    print(' max_version:', j['crate'].get('max_version'), '| versions:', [v['num'] for v in j.get('versions', [])][:8])
else:
    print(r[:120])
