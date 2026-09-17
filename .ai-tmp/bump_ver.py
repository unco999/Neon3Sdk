import io
p = r'D:\Neon3\Cargo.toml'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = 'version = "0.2.10"'
new = 'version = "0.2.11"'
i = d.find(old)
assert i != -1, '0.2.10 not found'
d = d[:i] + new + d[i + len(old):]
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('workspace version -> 0.2.11')
