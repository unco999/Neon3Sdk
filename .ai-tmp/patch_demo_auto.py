import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = "    let editor_bridge =\n        std::sync::Arc::new(neon_ui_runtime::editor_component::EditorBridge::new());\n"
assert anchor in d, 'anchor not found'

auto_block = anchor + """
    // Optional headless self-check: `NEON_DEMO_AUTO_INPUT=1` injects one
    // character 3s after boot straight into the shared EditorBridge, so the
    // whole insert -> edit-fx -> presentation -> renderer material pass chain
    // can be verified without OS keyboard focus. Kept env-gated: normal runs
    // never auto-type.
    if std::env::var("NEON_DEMO_AUTO_INPUT").is_ok_and(|v| v == "1" || v == "true") {
        let bridge = editor_bridge.clone();
        let boot = std::time::Instant::now();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(3));
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
            eprintln!("EDITOR_AUTO_INPUT inject at t={now:.2}");
            let commits = bridge.handle_input(&event, now);
            eprintln!("EDITOR_AUTO_INPUT commits={}", commits.len());
        });
    }
"""
d = d.replace(anchor, auto_block, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('patched ok')
