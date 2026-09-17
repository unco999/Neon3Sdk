# -*- coding: utf-8 -*-
"""Update all forward_editor_input call sites to pass now."""
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8')
repls = [
    ('self.forward_editor_input(UiEditorInputEvent::PointerPress { path, line, column })',
     'self.forward_editor_input(\n            UiEditorInputEvent::PointerPress { path, line, column },\n            self.animation_clock_seconds,\n        )'),
    ('self.forward_editor_input(UiEditorInputEvent::PointerDrag { path, line, column });',
     'self.forward_editor_input(\n            UiEditorInputEvent::PointerDrag { path, line, column },\n            self.animation_clock_seconds,\n        );'),
    ('self.forward_editor_input(UiEditorInputEvent::PointerRelease);',
     'self.forward_editor_input(\n            UiEditorInputEvent::PointerRelease,\n            self.animation_clock_seconds,\n        );'),
    ('self.forward_editor_input(UiEditorInputEvent::Scroll { path, delta })',
     'self.forward_editor_input(\n            UiEditorInputEvent::Scroll { path, delta },\n            self.animation_clock_seconds,\n        )'),
    ('self.forward_editor_input(UiEditorInputEvent::Zoom {\n            path,\n            factor,\n            viewport_height,\n            viewport_width,\n            row_height,\n            gutter_width,\n        })',
     'self.forward_editor_input(\n            UiEditorInputEvent::Zoom {\n                path,\n                factor,\n                viewport_height,\n                viewport_width,\n                row_height,\n                gutter_width,\n            },\n            self.animation_clock_seconds,\n        )'),
    ('self.forward_editor_input(UiEditorInputEvent::Key {\n            path,\n            kind,\n            text: text.map(str::to_string),\n            shift,\n            ctrl,\n            viewport_height,\n            viewport_width,\n            row_height,\n            gutter_width,\n        })',
     'self.forward_editor_input(\n            UiEditorInputEvent::Key {\n                path,\n                kind,\n                text: text.map(str::to_string),\n                shift,\n                ctrl,\n                viewport_height,\n                viewport_width,\n                row_height,\n                gutter_width,\n            },\n            self.animation_clock_seconds,\n        )'),
    ('self.forward_editor_input(UiEditorInputEvent::ImePreedit {\n            path,\n            value: value.to_string(),\n        });',
     'self.forward_editor_input(\n            UiEditorInputEvent::ImePreedit {\n                path,\n                value: value.to_string(),\n            },\n            self.animation_clock_seconds,\n        );'),
    ('self.forward_editor_input(UiEditorInputEvent::ImeCommit {\n            path,\n            value: value.to_string(),\n            viewport_height,\n            viewport_width,\n            row_height,\n            gutter_width,\n        })',
     'self.forward_editor_input(\n            UiEditorInputEvent::ImeCommit {\n                path,\n                value: value.to_string(),\n                viewport_height,\n                viewport_width,\n                row_height,\n                gutter_width,\n            },\n            self.animation_clock_seconds,\n        )'),
    ('''        self.forward_editor_input(UiEditorInputEvent::Key {
            path,
            kind: UiEditorKeyKind::Named("Escape".to_string()),
            text: None,
            shift: false,
            ctrl: false,
            viewport_height,
            viewport_width,
            row_height,
            gutter_width,
        });''',
     '''        self.forward_editor_input(
            UiEditorInputEvent::Key {
                path,
                kind: UiEditorKeyKind::Named("Escape".to_string()),
                text: None,
                shift: false,
                ctrl: false,
                viewport_height,
                viewport_width,
                row_height,
                gutter_width,
            },
            self.animation_clock_seconds,
        );'''),
]
for old, new in repls:
    if old in d:
        d = d.replace(old, new)
    else:
        print('NOT FOUND:', old[:70].replace('\n', '\\n'))
open(p, 'w', newline='\n').write(d)
print('sink call sites updated')
