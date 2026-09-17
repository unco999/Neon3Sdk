# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''    fn forward_editor_input(&mut self, event: UiEditorInputEvent, now: f32) -> bool {
        let Some(sink) = self.editor_input_sink.as_mut() else {
            return false;
        };
        let commits = sink(event, now);
        self.editor_pending_commits.extend(commits);
        true
    }'''
new = '''    fn forward_editor_input(&mut self, event: UiEditorInputEvent, now: f32) -> bool {
        let tag = match &event {
            UiEditorInputEvent::Key { .. } => "Key",
            UiEditorInputEvent::PointerPress { .. } => "PointerPress",
            UiEditorInputEvent::PointerDrag { .. } => "PointerDrag",
            UiEditorInputEvent::PointerRelease => "PointerRelease",
            UiEditorInputEvent::Scroll { .. } => "Scroll",
            UiEditorInputEvent::Zoom { .. } => "Zoom",
            UiEditorInputEvent::ImePreedit { .. } => "ImePreedit",
            UiEditorInputEvent::ImeCommit { .. } => "ImeCommit",
        };
        eprintln!("[editor-renderer] input event: {tag}");
        let Some(sink) = self.editor_input_sink.as_mut() else {
            eprintln!("[editor-renderer] input dropped: no sink");
            return false;
        };
        let commits = sink(event, now);
        self.editor_pending_commits.extend(commits);
        true
    }'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('input log added')
