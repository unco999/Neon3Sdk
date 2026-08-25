# neon3-sdk

Python SDK for the Neon3 `neon3.rpc` control plane.

```bash
cd packages/python-sdk
pip install -e .
python -m neon3_sdk calculator
```

Tests and deterministic scenario:

```bash
python -m unittest discover -s tests -v
python -m neon3_sdk calculator --once
```

When `--neon-root` is omitted, the command uses the SDK-local `release`
directory. Set `NEON_ROOT` or pass `--neon-root <path>` only to override it.
