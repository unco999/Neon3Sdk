import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = """        // Create / update mirrors.
        for (path, (declaration, presentation)) in desired {
            if let Some(state) = self.editors.get_mut(&path) {
                if state.presentation_revision != presentation.revision {"""
assert anchor in d, 'update anchor missing'
probe = """        // Create / update mirrors.
        for (path, (declaration, presentation)) in desired {
            {
                use std::sync::atomic::{AtomicU32, Ordering};
                static UP_FRAMES: AtomicU32 = AtomicU32::new(0);
                let f = UP_FRAMES.fetch_add(1, Ordering::Relaxed);
                if f < 60 {
                    eprintln!(
                        "EDITOR_FX desired path={path} fx={} rev={} existing={}",
                        presentation.edit_fx.len(),
                        presentation.revision,
                        self.editors.contains_key(&path)
                    );
                }
            }
            if let Some(state) = self.editors.get_mut(&path) {
                if state.presentation_revision != presentation.revision {"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('desired probe installed')
