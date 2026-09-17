import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
i0 = d.find('const TEXT_TYPE_IN_SOURCE')
i1 = d.find('const TEXT_DELETE_FRAGMENT_SOURCE')
orig = d[i0:i1]
io.open(r'D:\Neon3Sdk\.ai-tmp\typein_orig.txt', 'w', encoding='utf-8').write(orig)
new_shader = (
    'const TEXT_TYPE_IN_SOURCE: &str = r#"\n'
    'fn text_material(input: TextMaterialInput) -> vec4<f32> {\n'
    '    let alpha = smoothstep(0.05, 0.6, input.coverage);\n'
    '    return vec4<f32>(0.0, 1.0, 1.0, alpha);\n'
    '}\n'
    '"#;\n\n'
)
d = d[:i0] + new_shader + d[i1:]
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('type-in shader -> pure cyan, backup saved')
