# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
k = d.find('fn ui_flow_submit')
seg = d[k:k+5000]
# find the accept call with fragment
m = re.search(r'(self\.fragments[^\n]*|self\.accept[^\n]*fragment[^\n]*|fragment)', seg)
for mm in re.finditer(r'[^\n]*(self\.accept\(|self\.fragments)[^\n]*', seg):
    print('  ', mm.group(0).strip()[:160])
