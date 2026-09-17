import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
anchor = """            let commits = bridge.handle_input(&event, now);
            eprintln!("EDITOR_AUTO_INPUT commits={}", commits.len());"""
assert anchor in d, 'anchor missing'
probe = """            let commits = bridge.handle_input(&event, now);
            eprintln!("EDITOR_AUTO_INPUT commits={}", commits.len());
            {
                let presentations = bridge.presentations.lock().unwrap();
                for p in presentations.iter() {
                    eprintln!(
                        "EDITOR_AUTO_PRES node_key={} fx={} rev={} caret=({},{})",
                        p.node_key, p.edit_fx.len(), p.revision, p.caret_line, p.caret_column
                    );
                }
            }"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('patched pres probe')
