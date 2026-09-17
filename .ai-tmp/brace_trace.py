import io
d = io.open(r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs', 'rb').read().decode('utf-8').replace('\r\n', '\n')
lines = d.split('\n')
depth = 0
in_str = False
in_line_comment = False
in_block_comment = False
for li, line in enumerate(lines):
    i = 0
    while i < len(line):
        c = line[i]
        n = line[i+1] if i+1 < len(line) else ''
        if in_line_comment:
            break
        if in_block_comment:
            if c == '*' and n == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '/' and n == '/':
            in_line_comment = True
            break
        if c == '/' and n == '*':
            in_block_comment = True
            i += 2
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    # report any line where depth changed into values we care about
    if depth == 1 and (li % 20 == 0 or li > 1380):
        pass
# print depth at key markers
for marker in ['fn layout_editors', 'fn reconcile_editors', 'impl super', 'fn from_presentation']:
    for li, line in enumerate(lines):
        if marker in line:
            print(li+1, marker, '-> depth check later')
# recompute with logging every time depth crosses specific values
depth = 0
in_str = False
in_line_comment = False
in_block_comment = False
for li, line in enumerate(lines):
    i = 0
    while i < len(line):
        c = line[i]
        n = line[i+1] if i+1 < len(line) else ''
        if in_line_comment:
            break
        if in_block_comment:
            if c == '*' and n == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '/' and n == '/':
            in_line_comment = True
            break
        if c == '/' and n == '*':
            in_block_comment = True
            i += 2
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        i += 1
    if li % 100 == 99 or li == len(lines)-1:
        print('line', li+1, 'depth', depth)
