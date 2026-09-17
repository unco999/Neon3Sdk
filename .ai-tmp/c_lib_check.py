# -*- coding: utf-8 -*-
import re
l = open(r'D:\Neon3Sdk\packages\c-sdk\src\lib.rs', 'rb').read().decode('utf-8')
i = l.find('EDITOR_SERVICE')
print('--- EDITOR_SERVICE context ---')
print(l[max(0, i - 300):i + 500])
print('--- editor/event fns ---')
for m in re.finditer(r'pub unsafe extern "C" fn (neon3_editor_\w+|neon3_event_\w+)', l):
    print(m.group(1))
