# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
k = d.find('fn ui_flow_submit')
seg = d[k:k+5000]
# show everything around the fragment insert & accept
i = seg.find('self.fragments')
print(seg[max(0,i-700):i+300])
