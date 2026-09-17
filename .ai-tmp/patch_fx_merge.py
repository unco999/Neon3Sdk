import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# Insert fx source merge right before the glyph loop that consumes state.edit_fx.
anchor = """                    // Transient edit fx: inserted glyphs in the fx column
                    // range ride the type-in package; a delete fx snapshots
                    // its ghost at the pre-delete estimate position.
                    for fx in &state.edit_fx {"""
assert anchor in d, 'fx loop anchor missing'

merge = """                    // Transient edit fx: inserted glyphs in the fx column
                    // range ride the type-in package; a delete fx snapshots
                    // its ghost at the pre-delete estimate position.
                    // The mirror can be rebuilt by a co-drawn render pass
                    // (behind-ui / world-lab) between presentations, which
                    // would drop a just-published fx; re-read the external
                    // presentations slot directly so transient effects never
                    // vanish from the layout pass.
                    let fx_owned;
                    let fx_source = if !state.edit_fx.is_empty() {
                        &state.edit_fx
                    } else if let Some(slot) = &self.editor_external_presentations
                        && let Ok(external) = slot.lock()
                    {
                        fx_owned = external
                            .iter()
                            .filter(|p| p.node_key == state.declaration.node_key)
                            .flat_map(|p| p.edit_fx.iter().cloned())
                            .collect::<Vec<_>>();
                        &fx_owned
                    } else {
                        &state.edit_fx
                    };
                    for fx in fx_source {"""
d = d.replace(anchor, merge, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('fx slot merge installed')
