import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old = '''    return vec4<f32>(0.0, 1.0, 1.0, 1.0);
}
TEXT_DELETE_FRAGMENT_SOURCE'''
new = '''    return vec4<f32>(0.0, 1.0, 1.0, 1.0);
}
"#;

const TEXT_DELETE_FRAGMENT_SOURCE'''
assert old in d, 'anchor missing'
d = d.replace(old, new, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('fixed')
