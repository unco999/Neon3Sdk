import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = """        Self {
            declaration,
            lines,"""
assert anchor in d, 'from_pres anchor missing'
probe = """        {
            use std::sync::atomic::{AtomicU32, Ordering};
            static FP: AtomicU32 = AtomicU32::new(0);
            let f = FP.fetch_add(1, Ordering::Relaxed);
            if f < 60 {
                eprintln!(
                    "EDITOR_FX from_pres f={f} fx_in={} rev={}",
                    presentation.edit_fx.len(),
                    presentation.revision
                );
            }
        }
        Self {
            declaration,
            lines,"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('from_pres probe installed')
