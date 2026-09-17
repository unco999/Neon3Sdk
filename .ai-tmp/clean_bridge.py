# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-ui-runtime\src\editor_component.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''        let presentations = registry.to_presentations(0.0);
        eprintln!(
            "[editor-bridge] sync_fragments: fragments={} declarations={} presentations={}",
            fragments.len(),
            desired.len(),
            presentations.len()
        );
        *self.presentations.lock().expect("editor bridge presentations lock") = presentations;'''
new = '''        *self.presentations.lock().expect("editor bridge presentations lock") =
            registry.to_presentations(0.0);'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('sync_fragments log removed')
