# -*- coding: utf-8 -*-
"""Update sink type + add external presentations slot to UiWgpuRenderer."""
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer.rs'
d = open(p, 'rb').read().decode('utf-8')

old_sink = '''    editor_input_sink:
        Option<Box<dyn FnMut(neon_ui_schema::UiEditorInputEvent) -> Vec<editor_renderer::EditorCommit> + Send>>,'''
new_sink = '''    editor_input_sink: Option<
        Box<
            dyn FnMut(neon_ui_schema::UiEditorInputEvent, f32)
                -> Vec<editor_renderer::EditorCommit>
                + Send,
        >,
    >,
    /// Shared slot where the host's ui-runtime editor component publishes
    /// fresh presentations (after handling input). The renderer merges these
    /// into `reconcile_editors` ahead of the fragment's own effect.
    editor_external_presentations: Option<
        std::sync::Arc<std::sync::Mutex<Vec<neon_ui_schema::UiCodeEditorPresentation>>>,
    >,'''
assert old_sink in d, 'sink type anchor missing'
d = d.replace(old_sink, new_sink)

old_init = '''            editor_input_sink: None,
        }
    }'''
new_init = '''            editor_input_sink: None,
            editor_external_presentations: None,
        }
    }'''
assert old_init in d, 'init anchor missing'
d = d.replace(old_init, new_init, 1)
open(p, 'w', newline='\n').write(d)
print('sink type + slot added')
