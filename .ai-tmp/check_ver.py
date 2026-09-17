import io, re
d = io.open(r'D:\Neon3\Cargo.toml', 'rb').read().decode('utf-8', errors='ignore')
m = re.search(r'^version\s*=\s*"([^"]+)"', d, re.M)
print('workspace version:', m.group(1) if m else '?')
d2 = io.open(r'D:\Neon3\crates\neon-editor\Cargo.toml', 'rb').read().decode('utf-8', errors='ignore')
print('neon-editor:', re.search(r'^version[^\n]*', d2, re.M).group(0))
