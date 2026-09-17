# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
d = open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

old = '''            for (node_key, presentation) in pres_map {
                // Only accept presentations whose lowered node is still a
                // Panel in this fragment (the renderer needs a draw target).
                if kinds.get(&node_key) != Some(&UiNodeKind::Panel) {
                    continue;
                }
                let path = format!("{}/{}", fragment.fragment_id.0, node_key);
                let Some(declaration) = declarations.get(&node_key).cloned() else {
                    continue;
                };
                desired.insert(path, (declaration, presentation));
            }
        }'''
new = '''            // The desired set comes from declarations (a lowered code_editor
            // always carries the declaration; the presentation may ride the
            // fragment or arrive via the external slot, filled below).
            for (node_key, declaration) in declarations {
                // Only accept declarations whose lowered node is still a
                // Panel in this fragment (the renderer needs a draw target).
                if kinds.get(&node_key) != Some(&UiNodeKind::Panel) {
                    continue;
                }
                let path = format!("{}/{}", fragment.fragment_id.0, node_key);
                let presentation = pres_map.remove(&node_key).unwrap_or_default();
                desired.insert(path, (declaration, presentation));
            }
        }'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('reconcile desired fixed')
