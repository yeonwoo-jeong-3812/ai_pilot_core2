"""액션 파라미터 → 물리 거동 실측 표 생성.

단일 액션 트리의 Pilot 을 우전방(방위 45°) 스크립트 직진 표적에 붙여 6초 실행,
초기→최종 상태 차로 평균 응답(선회·상승/강하·접근·속도)을 측정한다.
"명령이 결과로 이어짐"을 표로 보증하는 참가자 교육 자료 (NME analyze_transfer
방법론 이식 — 코드 미복사).

사용: python scripts/measure_behavior.py           # → sdk/docs/MEASURED_BEHAVIOR.md
엔진(제어 스택·교리) 변경 시 재실행해서 갱신할 것 — 문서에 엔진 커밋이 찍힌다.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from aircombat.engine.factory import make_pilot          # noqa: E402
from aircombat.engine.match import Match                 # noqa: E402
from aircombat.engine.opponents.scripted import ScriptedOpponent  # noqa: E402
from aircombat.guidance.doctrine import Doctrine         # noqa: E402
from aircombat.tactics.dsl import build_node             # noqa: E402
from aircombat.tactics.policy import TacticPolicy        # noqa: E402

DURATION_S = 6.0
BLUE_IC = dict(pos=(0.0, 0.0, -15000.0), psi=0.0, kcas=350.0, alt=15000.0)
RED_POS = (6000.0, 6000.0, -15000.0)     # 우전방 45°, 8,485 ft

CASES = [
    ("pure (기준)",              {"pursuit": "pure", "name": "m"}),
    ("lead",                     {"pursuit": "lead", "name": "m"}),
    ("lag",                      {"pursuit": "lag", "name": "m"}),
    ("pure + g_burst 1.0",       {"pursuit": "pure", "g_burst": 1.0, "name": "m"}),
    ("pure + g_burst 0.5",       {"pursuit": "pure", "g_burst": 0.5, "name": "m"}),
    ("pure + g_full_ata 25",     {"pursuit": "pure", "g_full_ata_deg": 25.0, "name": "m"}),
    ("pure + aim_above +1000ft", {"pursuit": "pure", "aim_above_ft": 1000, "name": "m"}),
    ("pure + aim_above −800ft",  {"pursuit": "pure", "aim_above_ft": -800, "name": "m"}),
]


def _measure(action: dict) -> dict:
    policy = TacticPolicy(root=build_node({"action": action}))
    blue = make_pilot("Blue", BLUE_IC, policy, Doctrine())
    red = ScriptedOpponent(init_pos_ned=RED_POS, speed_kts=350.0, heading_deg=0.0,
                           maneuver="straight")
    range0 = float(np.linalg.norm(np.array(RED_POS) - np.array(BLUE_IC["pos"])))
    Match(blue, red, duration_s=DURATION_S, log_hz=0).run()
    bs, rs = blue.state(), red.state()
    rng = float(np.linalg.norm(rs.pos_ned - bs.pos_ned))
    hdg = (math.degrees(bs.psi) + 180.0) % 360.0 - 180.0
    return dict(dpsi=hdg / DURATION_S,
                climb=(bs.alt_ft - BLUE_IC["alt"]) / DURATION_S,
                closure=(range0 - rng) / DURATION_S,
                kcas=bs.kcas)


def main() -> int:
    commit = "unknown"
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        pass

    rows = []
    for label, action in CASES:
        m = _measure(action)
        rows.append(f"| {label} | {m['dpsi']:+.1f} | {m['climb']:+.0f} "
                    f"| {m['closure']:+.0f} | {m['kcas']:.0f} |")
        print(f"  {label:<26} 선회 {m['dpsi']:+5.1f}°/s  상승 {m['climb']:+5.0f}ft/s  "
              f"접근 {m['closure']:+5.0f}ft/s")

    doc = f"""<!-- 실측 문서 — scripts/measure_behavior.py 가 생성. 엔진 변경 시 재실행. -->

# 액션 → 거동 실측 표

**측정 조건**: 15,000 ft·350 KCAS 북향에서, 우전방 45°·8,485 ft 의 직진 표적(350 kt)에
단일 액션 트리로 {DURATION_S:.0f}초. 값은 {DURATION_S:.0f}초 평균 응답. 엔진 커밋 `{commit}`.

**요점**: 명령은 결정론적으로 거동이 된다 — 트리 설계 시 아래 응답을 신뢰하고
조건 임계값을 잡으면 된다. (같은 조건 재실행 = 같은 수치)

| 액션 | 선회율 [°/s, +우] | 상승률 [ft/s] | 접근율 [ft/s] | 종료 KCAS |
|---|---|---|---|---|
{chr(10).join(rows)}

읽는 법 (수치가 말하는 것):
- **pure/lead/lag** 는 조준점 기하 차이 — lag 는 표적 **뒤**를 지향하므로 더 크게
  돌아 들어가고(선회율 최대), lead 는 미래점을 지향해 가장 완만하다. 접근율
  차이는 이 기하·6초 창에서는 작다 — 추격 유형의 이득은 더 긴 시간·다른
  국면(요격/과접근 방지)에서 나타난다.
- **g_burst 는 선회를 사고 에너지를 낸다**: burst 를 올리면 6초 선회율이 오르고
  종료 KCAS 가 떨어진다(표에서 기준 대비 확인). 구 max_g 처럼 조절을 우회해 리미터에
  붙는 것이 아니라 **천장만** 올리므로 단기 선회가 무너지지는 않지만, 에너지 소모는
  누적된다 — 교범 4.4.7.2 *"DO NOT stay on the limiter"*. 태워야 할 국면(방어 브레이크·
  하드덱 회복·사격창)에만 올리고, 평시 당김은 교리 계층에 맡겨라.
- **g_full_ata_deg** 를 줄이면 같은 조준 오차에서 더 세게 당긴다(선회율 최대) —
  대가는 역시 에너지. burst 와 조합해 국면별 공격성을 설계하는 재료다.
- **aim_above_ft** 는 수직 오프셋이 그대로 상승/강하로 나타난다 — 요요의 재료.
  교리 계층이 G·파워를 함께 조절하므로 기하 명령만으로 안전하다.

재측정: `python scripts/measure_behavior.py` (SDK 에는 스크립트가 포함되지 않는다 —
수치가 궁금하면 같은 조건으로 run_match 를 돌려 Tacview 로 확인해도 된다).
"""
    out = os.path.join(ROOT, "sdk", "docs", "MEASURED_BEHAVIOR.md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    print(f"생성: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
