# -*- coding: utf-8 -*-
p = r'D:\Neon3\crates\neon-ui-schema\src\lib.rs'
d = open(p, 'rb').read().decode('utf-8')
was_crlf = '\r\n' in d
d = d.replace('\r\n', '\n')

old = '''            Self::CodeEditorDeclaration { node_key, declaration } => {
                if node_key.trim().is_empty() || !declaration.validate() {
                    Err(UiSchemaError::InvalidProgramEvent)
                } else {
                    Ok(())
                }
            }
        }
    }
}'''
new = '''            Self::CodeEditorDeclaration { node_key, declaration } => {
                if node_key.trim().is_empty() || !declaration.validate() {
                    Err(UiSchemaError::InvalidProgramEvent)
                } else {
                    Ok(())
                }
            }
            Self::CodeEditorPresentation { presentations } => {
                if presentations.values().any(|snapshot| !snapshot.validate()) {
                    Err(UiSchemaError::InvalidProgramEvent)
                } else {
                    Ok(())
                }
            }
        }
    }
}'''
assert old in d, 'validate anchor missing'
d = d.replace(old, new)
open(p, 'wb').write(d.replace('\n', '\r\n').encode('utf-8') if was_crlf else d.encode('utf-8'))
print('validate branch added')
