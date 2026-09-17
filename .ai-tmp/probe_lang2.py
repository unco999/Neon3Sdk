import io, re

for path, label in [
    (r'D:\Neon3\crates\neon-editor\src\languages\mod.rs', 'languages/mod.rs'),
    (r'D:\Neon3\crates\neon-editor\src\languages\tree_sitter.rs', 'languages/tree_sitter.rs'),
    (r'D:\Neon3\crates\neon-editor\src\lsp.rs', 'lsp.rs'),
]:
    d = io.open(path, 'rb').read().decode('utf-8', errors='ignore')
    print(f'=== {label} ===')
    seen = set()
    for m in re.finditer(r'(pub fn \w+|pub enum \w+|pub struct \w+|impl \w+|tree_sitter|"typescript"|"rust"|"cpp"|"nui_flow"|LanguageKind|LspEndpoint|LspClient)', d):
        s = m.group(0)
        if s not in seen:
            seen.add(s)
            print(' ', s)
    print()
