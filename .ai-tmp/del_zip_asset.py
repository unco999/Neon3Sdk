# -*- coding: utf-8 -*-
"""Remove the zip asset from the v0.2.10 release (keep exe only)."""
import json, urllib.request, base64

TOKEN = None
import subprocess
r = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
TOKEN = r.stdout.strip() if r.returncode == 0 else None
print('gh token available:', bool(TOKEN))

def api(url, method='GET', data=None):
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'probe')
    if TOKEN:
        req.add_header('Authorization', f'Bearer {TOKEN}')
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
        return json.loads(body.decode('utf-8')) if body else None

rel = api('https://api.github.com/repos/unco999/Neon3-CiJian/releases/tags/v0.2.10')
print('assets before:', [(a['name'], a['id']) for a in rel.get('assets', [])])
for a in rel.get('assets', []):
    if a['name'].endswith('.zip'):
        api(f"https://api.github.com/repos/unco999/Neon3-CiJian/releases/assets/{a['id']}", method='DELETE')
        print('deleted zip asset:', a['name'])
rel = api('https://api.github.com/repos/unco999/Neon3-CiJian/releases/tags/v0.2.10')
print('assets after:', [(a['name'], a['size']) for a in rel.get('assets', [])])
