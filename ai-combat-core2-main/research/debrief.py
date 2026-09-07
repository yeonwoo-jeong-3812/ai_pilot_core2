"""[shim] 디브리프 도구는 정본 `aircombat.debrief.replay_debrief` 로 승격됨.

기존 호출부(`python -m research.debrief …`) 호환 유지 — 로직은 정본 모듈에 있고
여기선 재노출만 한다. Match.run() 이 교전마다 auto_debrief 를 무조건 호출한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aircombat.debrief.replay_debrief import (   # noqa: F401
    parse_acmi, debrief_summary, plot_debrief, auto_debrief, main,
)

if __name__ == "__main__":
    raise SystemExit(main())
