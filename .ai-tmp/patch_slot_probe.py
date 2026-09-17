import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = """        if let Some(slot) = &self.editor_external_presentations
            && let Ok(external) = slot.lock()
        {
            for presentation in external.iter() {"""
assert anchor in d, 'slot anchor missing'
probe = """        if let Some(slot) = &self.editor_external_presentations
            && let Ok(external) = slot.lock()
        {
            for presentation in external.iter() {
                {
                    use std::sync::atomic::{AtomicU32, Ordering};
                    static SLOT_FRAMES: AtomicU32 = AtomicU32::new(0);
                    let f = SLOT_FRAMES.fetch_add(1, Ordering::Relaxed);
                    if f < 40 {
                        eprintln!(
                            "EDITOR_FX slot node={} fx={} rev={}",
                            presentation.node_key,
                            presentation.edit_fx.len(),
                            presentation.revision
                        );
                    }
                }"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('slot probe installed')
