import io
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\bin\nui_flow_code_editor_demo.rs'
d = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')
old1 = '''            eprintln!("EDITOR_AUTO_INPUT inject at t={now:.2}");
            let commits = bridge.handle_input(&event, now);'''
new1 = '''            let _commits = bridge.handle_input(&event, now);'''
d = d.replace(old1, new1, 1)
old2 = '''                let commits = bridge.handle_input(&event, now);
                eprintln!("EDITOR_AUTO_INPUT commits={}", commits.len());'''
new2 = '''                let _commits = bridge.handle_input(&event, now);'''
d = d.replace(old2, new2, 1)
io.open(p, 'w', encoding='utf-8', newline='\n').write(d)
print('demo cleaned; EDITOR_AUTO remaining:', d.count('EDITOR_AUTO'))
