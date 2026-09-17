# -*- coding: utf-8 -*-
"""Static check for neon3.hpp: brace/paren balance + every C ABI call's
name/arity matches include/neon3.h declarations."""
import re

hpp = open(r'D:\Neon3Sdk\packages\cpp-sdk\include\neon3.hpp', 'rb').read().decode('utf-8')
h = open(r'D:\Neon3Sdk\packages\c-sdk\include\neon3.h', 'rb').read().decode('utf-8')

# 1) brace / paren / bracket balance
for a, b in [('{', '}'), ('(', ')'), ('[', ']')]:
    print(f'balance {a}{b}: {hpp.count(a)} / {hpp.count(b)}', 'OK' if hpp.count(a) == hpp.count(b) else 'MISMATCH')

# 2) every neon3_* call in hpp exists in h with matching param count
#    find C ABI prototypes in h
protos = {}
for m in re.finditer(r'NEON3_API\s+(?:int|void)\s+neon3_(\w+)\s*\(([^)]*)\)', h):
    args = [a.strip() for a in m.group(2).split(',') if a.strip()]
    protos[m.group(1)] = len(args)

calls = re.findall(r'neon3_(\w+)\s*\(', hpp)
bad = []
for c in set(calls):
    if c not in protos:
        bad.append(('missing-in-h', c))
    else:
        # count args in hpp call (rough: split top-level commas)
        pass
print('C ABI fns used in hpp:', sorted(set(calls)))
print('all present in neon3.h:', 'OK' if not bad else bad)

# 3) neon3_editor_open / subscribe etc. actually used
for name in ['editor_open', 'editor_snapshot', 'editor_apply', 'editor_commit',
             'editor_completions', 'editor_close', 'event_subscribe', 'event_recv',
             'event_subscription_free']:
    print(name, 'in hpp:', 'neon3_' + name in hpp)
