# -*- coding: utf-8 -*-
"""E2E: SDK downloads the v0.2.10 exe from GitHub and starts one neon3-runtime process."""
import os, shutil, sys, time
from pathlib import Path

CACHE = Path(os.environ["LOCALAPPDATA"]) / "Neon3Sdk" / "runtime" / "v0.2.10"
if CACHE.exists():
    shutil.rmtree(CACHE, ignore_errors=True)
    print("cache cleared:", CACHE)

sys.path.insert(0, r"D:\Neon3Sdk\packages\python-sdk\src")
os.environ["NEON3_RUNTIME_VERSION"] = "v0.2.10"
os.environ["NEON_PROFILE"] = "release"

from neon3_sdk.runtime import RuntimeSession, RuntimeConfig, RuntimeMode
from neon3_sdk.client import NeonClient

with RuntimeSession(RuntimeConfig(mode=RuntimeMode.HEADLESS)) as session:
    print("runtime started, profile:", session.active_profile if hasattr(session, "active_profile") else "n/a")
    print("processes:", [(n, p.poll() is None) for n, p in session.processes])
    # health
    for target, ep in (("eventd", "127.0.0.1:39101"), ("wgpu-runtime", "127.0.0.1:39103"), ("ui-runtime", "127.0.0.1:39102")):
        h = NeonClient.connect(ep, origin="e2e", timeout_seconds=5).health(target)
        print(f"health {target}: {h.status}")
    # editor open through the domain endpoint
    c = NeonClient.connect("127.0.0.1:39104", origin="e2e", timeout_seconds=5)
    r = c.editor.document_open("e2e-doc", "e2e-sess", "surface root w 100 h 100\n  text t value \"hi\"\n", "nui_flow")
    print("editor open:", r.snapshot.document_id if hasattr(r, "snapshot") else r)
print("session stopped OK")
