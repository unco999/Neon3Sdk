# -*- coding: utf-8 -*-
import os, re, json
root = r'D:\Neon3Sdk\packages'
for d in sorted(os.listdir(root)):
    p = os.path.join(root, d)
    if not os.path.isdir(p):
        continue
    print('===', d)
    for fname in ['pyproject.toml', 'package.json', 'Cargo.toml', 'CMakeLists.txt']:
        fp = os.path.join(p, fname)
        if not os.path.exists(fp):
            continue
        t = open(fp, 'rb').read().decode('utf-8', 'replace')
        if fname == 'package.json':
            try:
                j = json.loads(t)
                print('  package.json:', j.get('name'), j.get('version'))
            except Exception as e:
                print('  package.json parse err', e)
        else:
            m = re.search(r'version\s*=\s*"([^"]+)"', t)
            if m:
                print(f'  {fname}: {m.group(1)}')
            else:
                m2 = re.search(r'project\(\s*VERSION\s+([\d.]+)', t)
                if m2:
                    print(f'  {fname}: VERSION {m2.group(1)}')
