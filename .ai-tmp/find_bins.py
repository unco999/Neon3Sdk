# -*- coding: utf-8 -*-
import re, glob, os
root = r'D:\Neon3'
# 找所有 [[bin]] / [package] name
for cargo in glob.glob(os.path.join(root, 'crates', '*', 'Cargo.toml')):
    d = open(cargo, 'rb').read().decode('utf-8')
    pkgs = re.findall(r'^\[package\]\s*name\s*=\s*"([^"]+)"', d, re.M)
    bins = re.findall(r'^\[\[bin\]\]\s*name\s*=\s*"([^"]+)"', d, re.M)
    if pkgs:
        print(os.path.basename(os.path.dirname(cargo)), '->', pkgs, 'bins:', bins)
