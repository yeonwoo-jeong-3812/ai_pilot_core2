"""서버 파이프라인 계약 통합 검증 — 패치된 _run_single_match 를 실제 core2 로 구동.

형제 체크아웃 ai-combat-server 의 pipeline/match.py 를 그대로 import 해서
가짜 match/teams dict 로 1경기 실행한다 — Supabase 없이, 서버가 실제로 소비하는
계약(함수 시그니처·결과 dict 키·replay 파일)을 end-to-end 로 검증.
(NME bridge/verify_swap.py 의 패턴 차용 — 코드 미복사. 배포 제외 대상.)

사용: python scripts/verify_bridge.py [--duration 초]   # 기본 300s(룰북) 풀매치
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = os.path.abspath(os.path.join(ROOT, "..", "ai-combat-server"))
sys.path.insert(0, ROOT)

REQUIRED_KEYS = {"winner", "total_steps", "duration_seconds",
                 "tree1_hp", "tree2_hp", "replay_filename"}


def _load_server_match_module():
    path = os.path.join(SERVER, "pipeline", "match.py")
    if not os.path.isfile(path):
        raise SystemExit(f"ai-combat-server 체크아웃 없음: {path}")
    spec = importlib.util.spec_from_file_location("server_pipeline_match", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=None,
                    help="테스트용 짧은 매치 (기본: 서버 설정 그대로 = 300s)")
    args = ap.parse_args()

    mod = _load_server_match_module()

    teams = {
        "A": {"name": "verify-blue", "slug": "vblue", "agent_name": "attacker",
              "submission_path": "examples/starter.yaml"},
        "B": {"name": "verify-red", "slug": "vred", "agent_name": "energy",
              "submission_path": "examples/energy_fighter.yaml"},
    }
    match = {"id": "bridge-verify-0001", "team1_id": "A", "team2_id": "B"}

    if args.duration is not None:
        # 짧은 검증: 서버 모듈 내 CompetitionMatch 호출을 그대로 쓰되 duration 만 축소
        from aircombat import bridge
        orig = bridge.CompetitionMatch

        def _short(*a, **kw):
            kw["duration_s"] = args.duration
            kw.pop("max_steps", None)
            return orig(*a, **kw)
        bridge.CompetitionMatch = _short

    res = mod._run_single_match(Path(ROOT), match, teams)

    print(json.dumps(res, ensure_ascii=False, indent=2))
    assert res is not None, "서버 함수가 None(오류 경로) 반환"
    missing = REQUIRED_KEYS - set(res)
    assert not missing, f"결과 dict 키 누락: {missing}"
    assert res["winner"] in ("tree1", "tree2", "draw"), res["winner"]
    if res["replay_filename"]:
        rp = Path(ROOT) / "replays" / res["replay_filename"]
        assert rp.exists(), f"replay 미생성: {rp}"
        print(f"replay OK: {rp.name} ({rp.stat().st_size:,} bytes)")
    print("VERDICT: PASS — 서버 소비 계약(_run_single_match) 충족")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
