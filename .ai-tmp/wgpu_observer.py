# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')
old = 'self.fragments\n            .insert(fragment.fragment_id.clone(), fragment);\n        self.graph_revision = Revision(self.graph_revision.0 + 1);'
new = 'self.fragments\n            .insert(fragment.fragment_id.clone(), fragment);\n        if let Some(observer) = self.editor_fragment_observer.as_mut() {\n            observer(&self.fragments);\n        }\n        self.graph_revision = Revision(self.graph_revision.0 + 1);'
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('observer hook added')
