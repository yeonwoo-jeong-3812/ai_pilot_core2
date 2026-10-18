"""Aircraft selection shared by the plant, guidance and live-session metadata."""
from __future__ import annotations

import os

DEFAULT_AIRCRAFT_MODEL = "f16"
ENGINE_BY_MODEL = {"f16": "F100-PW-220", "f16_220": "F100-PW-220-research", "f16_229": "F100-PW-229"}


def resolve_aircraft_model(model: str | None = None) -> str:
    """Resolve once per instance, never at module import time."""
    selected = model if model is not None else os.environ.get(
        "AIRCOMBAT_F16_MODEL", DEFAULT_AIRCRAFT_MODEL)
    if selected not in ENGINE_BY_MODEL:
        raise ValueError(f"Unknown aircraft model {selected!r}; choose f16, f16_220 or f16_229")
    return selected
