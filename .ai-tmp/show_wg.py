# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
# find WgpuRuntime struct + its fragment submit handler insert
i = d.find('pub struct WgpuRuntime')
j = d.find('\n}\n', i)
print(d[i:j+3])
# ui_flow_submit body - where fragments inserted
k = d.find('fn ui_flow_submit')
print('==== ui_flow_submit ====')
print(d[k:k+2200])
