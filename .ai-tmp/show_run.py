# -*- coding: utf-8 -*-
import re
d = open(r'D:\Neon3\crates\neon-wgpu-runtime\src\lib.rs', 'rb').read().decode('utf-8')
i = d.find('pub fn run_server_with_eventd')
print(d[i:i+2600])
