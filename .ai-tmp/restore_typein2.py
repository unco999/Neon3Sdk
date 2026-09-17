import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
i0 = d.find('const TEXT_TYPE_IN_SOURCE')
i1 = d.find('const TEXT_DELETE_FRAGMENT_SOURCE')
assert i0 != -1 and i1 != -1
orig = io.open(r'D:\Neon3Sdk\.ai-tmp\typein_orig2.txt', 'rb').read().decode('utf-8')
d = d[:i0] + orig + d[i1:]
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('type-in restored to HEAD original')
