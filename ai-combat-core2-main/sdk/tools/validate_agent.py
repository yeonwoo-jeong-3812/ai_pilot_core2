"""제출 전 에이전트 검증 — 서버와 동일한 파서로 문법·어휘·doctrine 블록 검사.

사용:
    python tools/validate_agent.py my_agents/my_agent.yaml [추가 파일 ...]

여기서 통과하면 업로드 후 "제출물 오류로 인한 DISQUALIFIED" 판정을 받지 않는다.
(전술이 좋은지는 검사하지 않는다 — run_match 로 직접 싸워볼 것.)
"""
from __future__ import annotations

import os
import sys


def _find_root(start: str) -> str:
    """aircombat 패키지가 보일 때까지 상위로 — SDK(tools/)·저장소(sdk/tools/) 겸용."""
    d = os.path.abspath(start)
    for _ in range(4):
        if os.path.isdir(os.path.join(d, "aircombat")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("aircombat 패키지를 찾을 수 없습니다 — SDK 루트에서 실행하세요.")


sys.path.insert(0, _find_root(os.path.dirname(__file__)))
from aircombat.engine.factory import load_policy  # noqa: E402


def validate(path: str) -> bool:
    try:
        policy, doctrine = load_policy(path)
    except Exception as exc:
        print(f"❌ {path}")
        print(f"   {type(exc).__name__}: {exc}")
        return False
    doc = "doctrine 블록 검증됨" if policy.doctrine_overrides else "doctrine 블록 없음(기본 교리)"
    print(f"✅ {path} — 트리 파싱·어휘 검증 통과, {doc}")
    return True


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    results = [validate(p) for p in args]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
