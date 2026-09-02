"""Frozen cross-language wire contract helpers for the Neon3 SDKs.

Canonical JSON and fixture loading live here so that the Python and Node
test suites validate byte-identical wire output for the fixtures in
``docs/fixtures/wire``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

FIXTURE_DIR_ENV = "NEON3_WIRE_FIXTURES"
CORE_ERROR_CODES = (
    "stale_revision",
    "unknown_target",
    "unsupported_intent",
    "capability_unavailable",
    "duplicate_event",
    "invalid_publication",
)


def canonical_json(value: Any) -> str:
    """Serialize a parsed wire value with sorted keys and no insignificant space.

    Numbers in canonical fixtures must be integers or values whose shortest
    decimal form matches across JSON implementations; keep non-integer floats
    out of contract fixtures.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fixture_root() -> Path:
    override = os.environ.get(FIXTURE_DIR_ENV)
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "fixtures" / "wire"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"{FIXTURE_DIR_ENV} is not set and docs/fixtures/wire was not found above {here}")


def fixture_path(name: str) -> Path:
    return fixture_root() / name


def load_fixture(name: str) -> Any:
    return json.loads(fixture_path(name).read_text(encoding="utf-8"))


def require_fields(value: Any, required: tuple[str, ...], optional: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected an object")
    keys = set(value)
    missing = set(required) - keys
    extra = keys - set(required) - set(optional)
    if missing or extra:
        raise ValueError(f"{label}: missing={sorted(missing)} unexpected={sorted(extra)}")
    return value
