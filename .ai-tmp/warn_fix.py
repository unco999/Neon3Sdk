# -*- coding: utf-8 -*-
"""Cleanup warnings: c-sdk crate-level allow(non_camel_case_types);
rust-sdk session.rs unused import; event.rs writer field (split stream,
keep for symmetry with `#[allow(dead_code)]`). Preserve CRLF."""
import io

def patch(path, fn, crlf_keep=True):
    raw = open(path, 'rb').read()
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    body = raw[3:] if has_bom else raw
    crlf = body.count(b'\r\n') > body.count(b'\n') / 2
    d = body.decode('utf-8')
    if crlf:
        d = d.replace('\r\n', '\n')
    out = fn(d)
    if crlf:
        out = out.replace('\n', '\r\n')
    open(path, 'wb').write((b'\xef\xbb\xbf' if has_bom else b'') + out.encode('utf-8'))
    print('patched', path)

# 1) c-sdk crate-level allow
def c1(d):
    old = '//! C ABI for the Neon3 control-plane protocol.'
    assert d.count(old) == 1
    return d.replace(old, '#![allow(non_camel_case_types)]\n\n' + old, 1)

# 2) rust-sdk session.rs unused import
def r1(d):
    old = 'use crate::wire::{RpcFailure, RpcResponse};'
    assert d.count(old) == 1
    return d.replace(old, 'use crate::wire::RpcFailure;', 1)

# 3) rust-sdk event.rs writer field
def r2(d):
    old = '''pub struct EventSubscription {
    reader: BufReader<TcpStream>,
    writer: BufWriter<TcpStream>,
}'''
    assert d.count(old) == 1
    return d.replace(old, '''pub struct EventSubscription {
    reader: BufReader<TcpStream>,
    // The writer half keeps the stream open and owns the socket; the recv
    // path only reads. Split for future request/response use on the same
    // subscription connection.
    #[allow(dead_code)]
    writer: BufWriter<TcpStream>,
}''', 1)

patch(r'D:\Neon3Sdk\packages\c-sdk\src\lib.rs', c1)
patch(r'D:\Neon3Sdk\packages\rust-sdk\src\session.rs', r1)
patch(r'D:\Neon3Sdk\packages\rust-sdk\src\event.rs', r2)
