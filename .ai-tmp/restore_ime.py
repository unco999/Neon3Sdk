import io
head = io.open(r'D:\Neon3Sdk\.ai-tmp\ed_renderer_head.rs', 'rb').read().decode('utf-8', errors='ignore').replace('\r\n', '\n')
p = r'D:\Neon3\crates\neon-wgpu-runtime\src\ui_renderer\editor_renderer.rs'
cur = io.open(p, 'rb').read().decode('utf-8').replace('\r\n', '\n')

# Extract HEAD IME block: from the comment to the closing of the IME if block
i = head.find('// IME preedit text renders at the caret position with a dim')
assert i != -1
# find the end: the IME block ends right before the for-row close (a 12-space '}' on its own)
seg_start = head.find('\n', i) + 1
# the block is: if state.focus && row == state.caret.line && !state.preedit.is_empty() { ... }
# find its closing brace: scan from the if statement
if_i = head.find('if state.focus && row == state.caret.line && !state.preedit.is_empty()', i)
assert if_i != -1
# find matching close: the block is at 16-space indent '                if ... {' and closes at '                }'
# then followed by '            }' (for-row close)
j = head.find('\n                }\n            }', if_i)
assert j != -1
ime_block = head[seg_start:j + len('\n                }')]
ime_block = ime_block.rstrip('\n')

# Insert into current file after the for-ch close (line '                }' before for-row close '            }')
anchor = '''                }
            }
            // Flush transient fx batches'''
# current file: for-ch close + for-row close + Flush
cur_anchor = '                }\n            }\n\n                \n            // Flush transient fx batches'
idx = cur.find(cur_anchor)
if idx == -1:
    # fallback: find '                }' followed by '            }' then blank then Flush
    idx = cur.find('                }\n            }\n')
    assert idx != -1
    tail = cur[idx + len('                }\n            }\n'):]
    replacement = '                }\n' + ime_block + '\n            }\n' + tail
else:
    replacement = cur_anchor.replace('                }\n            }\n\n                \n            // Flush', '                }\n' + ime_block + '\n            }\n\n            // Flush', 1)

cur = cur[:idx] + replacement
io.open(p, 'w', encoding='utf-8', newline='\n').write(cur)
print('IME block restored, len', len(ime_block))
