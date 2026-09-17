import io, os
p = r'D:\Neon3\crates\neon-ui-runtime\src\editor_component.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
d2 = d.replace('const FX_TYPE_IN_PACKAGE: &str = "code-editor-demo-register-type-in-v1";',
               'const FX_TYPE_IN_PACKAGE: &str = "text-type-in";')
d2 = d2.replace('const FX_DELETE_PACKAGE: &str = "code-editor-demo-register-delete-fragment-v1";',
                'const FX_DELETE_PACKAGE: &str = "text-delete-fragment";')
io.open(p, 'w', encoding='utf-8', newline='\n').write(d2)
i = d2.find('const FX_TYPE_IN_PACKAGE')
print(d2[i:i+180])
