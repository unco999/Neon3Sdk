import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# replace conditional mirror probe with unconditional frame probe (bounded)
old = """        for (path, state) in &self.editors {
            if !state.edit_fx.is_empty() {
                eprintln!(
                    "EDITOR_FX mirror {path} fx={} pkg0={}",
                    state.edit_fx.len(),
                    state.edit_fx[0].package_id
                );
            }
        }
    }

    /// Attaches the ui-runtime input sink (host bridge)."""
new = """        {
            use std::sync::atomic::{AtomicU32, Ordering};
            static FRAMES: AtomicU32 = AtomicU32::new(0);
            let f = FRAMES.fetch_add(1, Ordering::Relaxed);
            if f < 120 {
                for (path, state) in &self.editors {
                    eprintln!(
                        "EDITOR_FX reconcile f={f} path={path} fx={} rev={} lines={} src_head={}",
                        state.edit_fx.len(),
                        state.presentation_revision,
                        state.lines.len(),
                        state.lines.first().map(|l| l.chars().take(12).collect::<String>()).unwrap_or_default()
                    );
                }
            }
        }
    }

    /// Attaches the ui-runtime input sink (host bridge)."""
assert old in d, 'conditional probe missing'
d = d.replace(old, new, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('unconditional probe installed')
