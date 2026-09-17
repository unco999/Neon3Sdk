# -*- coding: utf-8 -*-
"""Verify the unified host via the C ABI: wgpu health on 39103, editor open on 39104."""
import ctypes, json, sys

dll = r'D:\Neon3Sdk\packages\c-sdk\target\debug\neon3_c.dll'
lib = ctypes.CDLL(dll)

lib.neon3_client_new.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_uint64,
                                 ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_char_p)]
lib.neon3_client_new.restype = ctypes.c_int
lib.neon3_client_free.argtypes = [ctypes.c_void_p]
lib.neon3_client_health.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int),
                                    ctypes.POINTER(ctypes.c_char_p)]
lib.neon3_client_health.restype = ctypes.c_int
lib.neon3_editor_open.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                  ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_char_p),
                                  ctypes.POINTER(ctypes.c_char_p)]
lib.neon3_editor_open.restype = ctypes.c_int
lib.neon3_free_string.argtypes = [ctypes.c_char_p]

def err_str(p):
    if not p:
        return ''
    s = ctypes.string_at(p).decode('utf-8', 'replace')
    lib.neon3_free_string(p)
    return s

def new_client(endpoint):
    client = ctypes.c_void_p()
    e = ctypes.c_char_p()
    rc = lib.neon3_client_new(endpoint.encode(), 1, 10000, ctypes.byref(client), ctypes.byref(e))
    if rc != 0:
        raise RuntimeError(f'connect {endpoint}: {err_str(e)}')
    return client

def health(client, target):
    h = ctypes.c_int(0)
    e = ctypes.c_char_p()
    rc = lib.neon3_client_health(client, target.encode(), ctypes.byref(h), ctypes.byref(e))
    return rc, h.value, err_str(e)

def editor_open(client, doc, sess, source, language):
    r = ctypes.c_char_p()
    e = ctypes.c_char_p()
    rc = lib.neon3_editor_open(client, doc.encode(), sess.encode(), source.encode(),
                               language.encode(), ctypes.byref(r), ctypes.byref(e))
    return rc, err_str(r), err_str(e)

# 1) wgpu health through 39103
c1 = new_client('127.0.0.1:39103')
rc, h, msg = health(c1, 'wgpu-runtime')
print('wgpu health rc=%d healthy=%d msg=%r' % (rc, h, msg))
lib.neon3_client_free(c1)

# 2) editor open through 39104
c2 = new_client('127.0.0.1:39104')
rc, result, msg = editor_open(c2, 'doc-1', 'sess-1', 'version 1\nsurface root w 100 h 100\n  text t value "hi"\n', 'nui_flow')
print('editor open rc=%d result=%s msg=%r' % (rc, result[:120], msg))
lib.neon3_client_free(c2)

print('DONE')
