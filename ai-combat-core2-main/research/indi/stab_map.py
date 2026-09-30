"""필터 차단주파수 × 측정 지연 안정 경계 지도 (E1 벤치, 기준 게인 고정 — 필터 효과만 분리).

  python research/indi/stab_map.py            → results/indi/stab_map.json (그림 7: figures.fig7_stability)
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import pmap, ROOT
from bench import evaluate
from aircombat.control.indi import INDIConfig, SensorConfig

FC = [3.0, 4.0, 5.0, 6.0, 8.0, 12.0, 17.0, 25.0, 40.0]
DT = [0, 1, 2, 3, 4, 6, 8, 11]                       # 틱 (1틱 = 8.3 ms)
OUT = os.path.join(ROOT, "results", "indi", "stab_map.json")


def _job(j):
    fc, dt = j
    r = evaluate(INDIConfig(filt_hz=fc), SensorConfig("gyro", 0.1, dt))
    return dict(filt_hz=fc, delay_ticks=dt, delay_ms=dt / 120 * 1000, J=r["J"], by_test=r["by_test"])


if __name__ == "__main__":
    rows = pmap(_job, [(fc, dt) for fc in FC for dt in DT], workers=int(sys.argv[1]) if len(sys.argv) > 1 else 3)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(base=dataclasses.asdict(INDIConfig()), rows=rows), f, indent=1)
    print("saved", OUT)
