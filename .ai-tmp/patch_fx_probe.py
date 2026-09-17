import io

# 1) editor_renderer.rs: log fx_batches contents at flush
p1 = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d1 = io.open(p1, 'rb').read().decode('utf-8').replace('\r\n', '\n')
anchor1 = """            // Flush transient fx batches, then the token-class batches and
            // the whole-node material (line numbers are intentionally
            // excluded above; only token-colored code glyphs route to
            // shaders).
            output
                .editor_text_materials
                .extend(fx_batches.into_iter());"""
assert anchor1 in d1, 'anchor1 missing'
probe1 = """            if !fx_batches.is_empty() {
                eprintln!(
                    "EDITOR_FX layout batches={}",
                    fx_batches
                        .iter()
                        .map(|(p, v)| format!("{p}={}", v.len()))
                        .collect::<Vec<_>>()
                        .join(",")
                );
            }
            // Flush transient fx batches, then the token-class batches and
            // the whole-node material (line numbers are intentionally
            // excluded above; only token-colored code glyphs route to
            // shaders).
            output
                .editor_text_materials
                .extend(fx_batches.into_iter());"""
d1 = d1.replace(anchor1, probe1, 1)
io.open(p1, 'w', encoding='utf-8', newline='\n').write(d1)
print('patched editor_renderer.rs')

# 2) ui_renderer.rs: log pipeline miss in the text material pass
p2 = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer.rs'
d2 = io.open(p2, 'rb').read().decode('utf-8').replace('\r\n', '\n')
anchor2 = """                    let Some(pipeline) = self.text_material_pipelines.get(package_id) else {
                        continue;
                    };"""
assert anchor2 in d2, 'anchor2 missing'
probe2 = """                    let Some(pipeline) = self.text_material_pipelines.get(package_id) else {
                        eprintln!("EDITOR_FX MISSING pipeline for package {package_id}");
                        continue;
                    };"""
d2 = d2.replace(anchor2, probe2, 1)
io.open(p2, 'w', encoding='utf-8', newline='\n').write(d2)
print('patched ui_renderer.rs')
