# neon3-sdk

Python SDK for the Neon3 `neon3.rpc` control plane.

```bash
cd packages/python-sdk
pip install -e .
python -m neon3_sdk calculator --neon-root <path-to-neon3-runtime>
```

Tests and deterministic scenario:

```bash
python -m unittest discover -s tests -v
python -m neon3_sdk calculator --neon-root <path-to-neon3-runtime> --once
```