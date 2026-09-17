import io

# --- Patch 1: editor_renderer.rs - fx_source external-slot merge ---
p1 = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p1, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''                    // Transient edit fx: inserted glyphs in the fx column
                    // range ride the type-in package; a delete fx snapshots
                    // its ghost at the pre-delete estimate position.
                    for fx in &state.edit_fx {'''
new = '''                    // Transient edit fx: inserted glyphs in the fx column
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

                    for fx in fx_source {'''
assert d.count(old) == 1, d.count(old)
d = d.replace(old, new, 1)
io.open(p1, 'w', encoding='utf-8', newline='\n').write(d)
print('patch1 fx_source applied')

# --- Patch 2: demo - NEON_DEMO_AUTO_INPUT auto input block ---
p2 = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d2 = io.open(p2, 'rb').read().decode('utf-8').replace('\r\n', '\n')
anchor = '''    let editor_bridge =
        std::sync::Arc::new(neon_ui_runtime::editor_component::EditorBridge::new());
'''
assert d2.count(anchor) == 1
add = anchor + '''
    // Optional headless self-check: `NEON_DEMO_AUTO_INPUT=1` injects one
    // character 8s after boot straight into the shared EditorBridge, so the
    // whole insert -> edit-fx -> presentation -> renderer material pass chain
    // can be verified without OS keyboard focus. Kept env-gated: normal runs
    // never auto-type.
    if std::env::var("NEON_DEMO_AUTO_INPUT").is_ok_and(|v| v == "1" || v == "true") {
        let bridge = editor_bridge.clone();
        let boot = std::time::Instant::now();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(8));
            let now = boot.elapsed().as_secs_f32();
            let event = neon_ui_schema::UiEditorInputEvent::Key {
                path: "code-editor-demo/source-view".to_string(),
                kind: neon_ui_schema::UiEditorKeyKind::Character("x".to_string()),
                text: Some("x".to_string()),
                shift: false,
                ctrl: false,
                viewport_height: 0.0,
                viewport_width: 0.0,
                row_height: 0.0,
                gutter_width: 0.0,
            };
            let _commits = bridge.handle_input(&event, now);
        });
    }
'''
d2 = d2.replace(anchor, add, 1)
io.open(p2, 'w', encoding='utf-8', newline='\n').write(d2)
print('patch2 auto-input applied')
