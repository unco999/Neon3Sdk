import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
anchor = """        // Destroy mirrors whose presentations disappeared.
        self.editors.retain(|path, _| desired.contains_key(path));"""
assert anchor in d, 'anchor missing'
probe = """        for (path, state) in &self.editors {
            if !state.edit_fx.is_empty() {
                eprintln!(
                    "EDITOR_FX mirror {path} fx={} pkg0={}",
                    state.edit_fx.len(),
                    state.edit_fx[0].package_id
                );
            }
        }
        // Destroy mirrors whose presentations disappeared.
        self.editors.retain(|path, _| desired.contains_key(path));"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('patched mirror probe')
