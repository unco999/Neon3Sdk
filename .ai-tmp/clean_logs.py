# -*- coding: utf-8 -*-
import re
paths = [
    r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs',
    r'D:\Neon3\crates\neon-ui-runtime\src\editor_component.rs',
]
patterns = [
    'eprintln!(\n        "[editor-renderer] reconcile:',
    'eprintln!(\n        "[editor-renderer] input event',
    'eprintln!(\n            "[editor-renderer] pointer_press at',
    'eprintln!("[editor-renderer] pointer_press: no editor at pointer");',
    'eprintln!(\n                "[editor-renderer] hit-check',
    'eprintln!("[editor-renderer] hit-skip world_depth");',
    'eprintln!("[editor-renderer] hit-skip no instance");',
    'eprintln!(\n                "[editor-renderer] hit-skip bounds panel={} content={:?}",',
    'eprintln!(\n                    "[editor-renderer] layout probe:',
    'eprintln!(\n        "[editor-bridge] sync_fragments:',
]
for p in paths:
    d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
    removed = []
    for pat in patterns:
        # find the full eprintln!(...) statement containing pat
        idx = 0
        while True:
            i = d.find(pat, idx)
            if i < 0:
                break
            # locate start of statement: search backwards for 'eprintln!('
            start = d.rfind('eprintln!(', 0, i)
            if start < 0:
                idx = i + 1
                continue
            # locate end: matching close paren
            depth = 0
            j = d.find('(', start)
            end = j
            while end < len(d):
                if d[end] == '(':
                    depth += 1
                elif d[end] == ')':
                    depth -= 1
                    if depth == 0:
                        break
                end += 1
            stmt = d[start:end+1]
            # also eat trailing newline
            tail = end + 1
            while tail < len(d) and d[tail] in '\r\n ':
                tail += 1
            removed.append(stmt.split('\n')[0][:80])
            d = d[:start] + d[tail:]
            idx = start
    open(p, 'w', newline='\n').write(d)
    print(p, 'removed', len(removed))
    for r in removed:
        print('  -', r)
