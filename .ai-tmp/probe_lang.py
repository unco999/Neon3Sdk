import io, re

d = io.open(r'D:\Neon3\crates\neon-editor\src\languages.rs', 'rb').read().decode('utf-8', errors='ignore')
print('=== languages.rs ===')
seen = set()
for m in re.finditer(r'(pub fn \w+|pub enum \w+|pub struct \w+|impl \w+|LanguageKind|tree_sitter|"typescript"|"rust"|"cpp"|"nui_flow")', d):
    s = m.group(0)
    if s not in seen:
        seen.add(s)
        print(' ', s)

d2 = io.open(r'D:\Neon3\crates\neon-editor\src\lsp.rs', 'rb').read().decode('utf-8', errors='ignore')
print('\n=== lsp.rs ===')
seen = set()
for m in re.finditer(r'(pub fn \w+|pub struct \w+|pub enum \w+|impl \w+)', d2):
    s = m.group(0)
    if s not in seen:
        seen.add(s)
        print(' ', s)
