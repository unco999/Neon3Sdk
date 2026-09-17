# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-ui-schema\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')
old = '''    pub focus: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub completion: Option<UiEditorCompletionSnapshot>,'''
new = '''    pub focus: bool,
    /// IME preedit text rendered at the caret (dim, distinct color).
    #[serde(default)]
    pub preedit: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub completion: Option<UiEditorCompletionSnapshot>,'''
assert old in d, 'preedit anchor missing'
d = d.replace(old, new, 1)
open(p, 'w', newline='\n').write(d)
print('preedit field added')
