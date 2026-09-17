import io, re
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# Each probe block starts with a "{ use std::sync::atomic..." and ends with the eprintln + "}" 
# We remove the full block including its opening brace. Strategy: find each eprintln containing EDITOR_FX,
# then walk back to the matching "{ use std::sync::atomic" opener, and forward to the closing "}" of the block.
# Simpler: remove exact probe blocks by scanning for 'use std::sync::atomic::{AtomicU32, Ordering};' occurrences
# that are part of probe blocks (they are followed by EDITOR_FX eprintln). We'll delete from the block opener
# (the line starting with '{' before 'use std::sync::atomic') through the eprintln statement + closing '}'.
# We do multiple passes by index since offsets shift.

probes = []
for m in re.finditer(r'EDITOR_FX', d):
    probes.append(m.start())

# Collect removal ranges by finding each probe's enclosing block
ranges = []
for idx in probes:
    # eprintln line start
    line_start = d.rfind('\n', 0, idx) + 1
    # find the block opener '{' before 'use std::sync::atomic'
    u = d.rfind('use std::sync::atomic::{AtomicU32, Ordering};', 0, idx)
    if u == -1:
        continue
    opener = d.rfind('{', 0, u)
    # find end: the '}' that closes the block after eprintln
    # block ends at the '}' on its own line following the eprintln(...); statement
    stmt_end = d.find(');', idx) + 2
    close = d.find('}', stmt_end)
    # ensure close is within a few lines
    if close == -1 or close - stmt_end > 400:
        continue
    ranges.append((opener, close + 1))

# merge overlapping ranges
ranges.sort()
merged = []
for a, b in ranges:
    if merged and a < merged[-1][1]:
        merged[-1] = (merged[-1][0], max(merged[-1][1], b))
    else:
        merged.append((a, b))

# remove from end to start
for a, b in reversed(merged):
    d = d[:a] + d[b:]

io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('removed', len(merged), 'probe blocks; remaining EDITOR_FX:', d.count('EDITOR_FX'))
