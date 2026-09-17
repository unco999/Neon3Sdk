import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

anchor = """                    for fx in fx_source {"""
assert anchor in d, 'fx_source loop anchor missing'
probe = """                    {
                        use std::sync::atomic::{AtomicU32, Ordering};
                        static LF: AtomicU32 = AtomicU32::new(0);
                        let lf = LF.fetch_add(1, Ordering::Relaxed);
                        if lf < 80 {
                            eprintln!(
                                "EDITOR_FX layout f={lf} fx_source={} fx_alive={} t={:.2}",
                                fx_source.len(),
                                fx_source
                                    .iter()
                                    .filter(|fx| time_seconds - fx.started_seconds < fx.duration_ms as f32 / 1000.0)
                                    .count(),
                                time_seconds
                            );
                        }
                    }
                    for fx in fx_source {"""
d = d.replace(anchor, probe, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('layout probe installed')
