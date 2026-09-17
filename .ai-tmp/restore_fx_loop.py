import io
head = io.open(r'D:\Neon3Sdk\.ai-tmp\ed_renderer_head.rs', 'rb').read().decode('utf-8', errors='ignore').replace('\r\n', '\n')
cur_p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
cur = io.open(cur_p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

i = head.find('for fx in &state.edit_fx')
j = head.find('// IME preedit text renders at the caret position', i)
seg = head[i:j]
seg = seg.replace('for fx in &state.edit_fx {', 'for fx in fx_source {', 1)

anchor = '''                        &state.edit_fx
                    };
                    
            // Flush transient fx batches, then the token-class batches and'''
assert anchor in cur, 'anchor missing'
replacement = '''                        &state.edit_fx
                    };

                    ''' + seg + '''
            // Flush transient fx batches, then the token-class batches and'''
cur = cur.replace(anchor, replacement, 1)
io.open(cur_p, 'w', encoding='utf-8', newline='\n').write(cur)
print('fx loop restored, len', len(seg))
