import io
d = io.open(r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs', 'rb').read().decode('utf-8').replace('\r\n', '\n')
depth = 0
min_depth = 0
line = 1
in_str = False
in_line_comment = False
in_block_comment = False
i = 0
while i < len(d):
    c = d[i]
    n = d[i+1] if i+1 < len(d) else ''
    if c == '\n':
        line += 1
        in_line_comment = False
        i += 1
        continue
    if in_line_comment:
        i += 1
        continue
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
        i += 2
        continue
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
        if depth < min_depth:
            min_depth = depth
            print('NEGATIVE at line', line)
    i += 1
print('final depth', depth, 'min', min_depth)
