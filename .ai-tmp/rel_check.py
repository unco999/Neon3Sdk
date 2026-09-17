# -*- coding: utf-8 -*-
import json, urllib.request

url = "https://api.github.com/repos/unco999/Neon3-CiJian/releases/tags/v0.2.10"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "probe"})
with urllib.request.urlopen(req, timeout=30) as r:
    rel = json.loads(r.read().decode("utf-8"))
print("tag:", rel.get("tag_name"), "| published:", rel.get("published_at"))
for a in rel.get("assets", []):
    print(f"  asset: {a['name']}  {a['size']} bytes  url={a['browser_download_url']}")
