"""설치 자가 점검 — 의존성 → 예제 검증 → 스모크 교전 → 결정론 → ACMI 생성.

사용: python tools/selfcheck.py
PASS 가 나오면 로컬 환경이 서버와 같은 방식으로 매치를 실행할 수 있다는 뜻이다.
"""
from __future__ import annotations

import os
import platform
import sys


def _find_root(start: str) -> str:
    d = os.path.abspath(start)
    for _ in range(4):
        if os.path.isdir(os.path.join(d, "aircombat")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("aircombat 패키지를 찾을 수 없습니다 — SDK 루트에서 실행하세요.")


ROOT = _find_root(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

# 2NM 헤드온 → 20여 초 안에 머지·교전 발생 (환경 정상 여부가 HP 변화로 보임)
SMOKE_DURATION_S = 25.0
SMOKE_RANGE_NM = 2.0


def main() -> int:
    print(f"[1/4] 환경: Python {platform.python_version()} ({sys.executable})")
    # 엔진은 cp314-win_amd64 단일 타깃 — 버전/플랫폼이 다르면 아래 import 가 생 트레이스백을
    # 낸다. PASS/FAIL 도구가 가장 흔한 실패를 명확한 메시지로 먼저 잡는다.
    if sys.version_info[:2] != (3, 14):
        print(f"FAIL — Python 3.14 필요 (현재 {platform.python_version()}). "
              f"py -3.14 -m venv .venv 로 3.14 가상환경을 만드세요.")
        return 1
    if sys.platform != "win32":
        print(f"FAIL — 이 SDK 는 Windows(cp314-win_amd64) 전용입니다 (현재 {sys.platform}).")
        return 1
    try:
        import numpy, yaml, jsbsim  # noqa: F401
        print(f"      numpy {numpy.__version__} / jsbsim {jsbsim.__version__} "
              f"/ pyyaml {yaml.__version__}")
    except ImportError as exc:
        print(f"FAIL — 의존성 누락: {exc} (pip install -r requirements.txt)")
        return 1

    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions

    blue_yaml = os.path.join(ROOT, "examples", "textbook.yaml")
    red_yaml = os.path.join(ROOT, "examples", "starter.yaml")
    print("[2/4] 예제 에이전트 검증:", end=" ")
    sides = [load_policy(blue_yaml), load_policy(red_yaml)]
    print("OK")

    def _run(acmi: str | None):
        ic = initial_conditions("headon", range_nm=SMOKE_RANGE_NM)
        # 파일럿별 트리 별도 build (Commit/Cooldown 상태 공유 금지)
        b = make_pilot("Blue", ic["blue"], *load_policy(blue_yaml))
        r = make_pilot("Red", ic["red"], *load_policy(red_yaml))
        m = Match(b, r, duration_s=SMOKE_DURATION_S, acmi_path=acmi,
                  log_hz=30.0 if acmi else 0.0)
        res = m.run()
        return (res.winner, res.condition, round(res.time_s, 3),
                round(res.hp_blue, 6), round(res.hp_red, 6))

    os.makedirs(os.path.join(ROOT, "replays"), exist_ok=True)
    acmi_path = os.path.join(ROOT, "replays", "selfcheck.acmi")
    print(f"[3/4] 스모크 교전 ({SMOKE_DURATION_S:.0f}s, {SMOKE_RANGE_NM:.0f}NM 헤드온):")
    r1 = _run(acmi_path)
    print(f"      winner={r1[0]} cond={r1[1]} HP={r1[3]:.1f}/{r1[4]:.1f}")

    print("[4/4] 결정론(같은 시드 재실행):", end=" ")
    r2 = _run(None)
    if r1 != r2:
        print(f"FAIL — 재실행 불일치: {r1} != {r2}")
        return 1
    print("일치")

    if not (os.path.isfile(acmi_path) and os.path.getsize(acmi_path) > 0):
        print(f"FAIL — 리플레이 미생성: {acmi_path}")
        return 1
    print(f"리플레이: {os.path.relpath(acmi_path, ROOT)} "
          f"({os.path.getsize(acmi_path):,} bytes — Tacview 로 열어보세요)")
    print("PASS — 환경 준비 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
