# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')

# 1. EditorBridgeHandle definition after top uses (anchor: pub mod ... / first fn)
anchor = 'use serde_json::{Value, json};'
assert anchor in d, 'anchor1 missing'
bridge_def = '''
/// Host bridge wiring for the code editor component. The host creates the
/// shared ui-runtime `EditorBridge`, then hands these handles to the
/// windowed runtime: the input sink routes renderer input into the editor
/// component, the presentations slot is republished every frame, and the
/// fragment observer keeps the component registry in sync with submitted
/// fragments. See `neon3-runtime` main.rs.
pub struct EditorBridgeHandle {
    pub input_sink:
        Option<Box<dyn FnMut(neon_ui_schema::UiEditorInputEvent, f32) -> Vec<ui_renderer::editor_renderer::EditorCommit> + Send>>,
    pub external_presentations: Option<Arc<Mutex<Vec<neon_ui_schema::UiCodeEditorPresentation>>>>,
    pub fragment_observer: Option<Box<dyn FnMut(&HashMap<UiFragmentId, UiFragment>) + Send>>,
}

'''
d = d.replace(anchor, anchor + bridge_def, 1)

# 2. WindowedRuntime struct field
old = '''    component_states: ComponentStateStore,
}'''
new = '''    component_states: ComponentStateStore,
    /// Host-injected editor bridge handles (input sink, presentations slot,
    /// fragment observer). `None` in standalone renderer mode.
    editor_bridge: Option<EditorBridgeHandle>,
}'''
assert old in d, 'struct anchor missing'
d = d.replace(old, new, 1)

# 3. WindowedRuntime::new init
old = '''            component_states: ComponentStateStore::default(),
        }
    }'''
new = '''            component_states: ComponentStateStore::default(),
            editor_bridge: None,
        }
    }'''
assert old in d, 'new anchor missing'
d = d.replace(old, new, 1)

open(p, 'w', newline='\n').write(d)
print('part1 done')
