# -*- coding: utf-8 -*-
import re, subprocess, json

print('=== git tags ===')
r = subprocess.run(['git', '-C', r'D:\Neon3', 'tag'], capture_output=True, text=True)
tags = [t for t in r.stdout.splitlines() if t.strip()]
print(tags[-8:] if tags else '(no tags)')

print('=== gh ===')
r = subprocess.run(['gh', '--version'], capture_output=True, text=True)
print(r.stdout.splitlines()[0] if r.stdout else 'gh not found')
r = subprocess.run(['gh', 'auth', 'status'], capture_output=True, text=True)
print((r.stdout + r.stderr).strip().splitlines()[:3])

print('=== workspace version ===')
d = open(r'D:\Neon3\Cargo.toml', 'rb').read().decode('utf-8')
m = re.search(r'version = "([^"]+)"', d)
print(m.group(1) if m else '?')
