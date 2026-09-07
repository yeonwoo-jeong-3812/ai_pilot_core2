"""doctrine 개방 전 지배 설정 스윕 (운영자 도구 — 개방 게이트).

각 교리 필드를 one-at-a-time 극단으로 밀었을 때 baseline 대비 성적(Δpts)을
측정한다. "모두가 수렴할 단일 최적"이 있는 필드는 개방하지 않고 점잠금한다
(DOCTRINE_BOUNDS 를 (기본값, 기본값) 으로 축소).

격자: 극단 18 config + baseline 1 = 19 / base 트리.
  · 밴드 10키(*_lo/*_hi 5쌍): 반대쪽 극단 1개씩 (lo↔hi 동치라 유효)
  · 중앙 기본 3키(entry_kcas·lv_above_ft·initial_pull_g): 양극단 2개씩
  · 편측 2키(g_fraction→0.8, g_min→1.5): 1개씩
base 트리 3종 = 조절형 2종(examples) + max_g 상시형 1종(인라인 — 2026-08 예선
1위 FNG 08-15 제출물 재현. 실존 메타의 두 집단을 모두 측정한다. max_g 분기는
G 계열 교리 키를 우회하므로 조절형만으로는 측정이 어긋난다).
대항군 3종 고정 = 변별력 실측 상위 배터리(2026-08-02, 신뢰도 0.81).

총 3 base × 19 config × (red 3 × 시나리오 4 × 시드 2 = 24경기) = 1,368경기.
지배 판정(분석 시): Δpts ≥ +6 ∧ base 3종 중 2종 동일 방향 ∧ red 2종 이상 일관.

사용:
    python scripts/sweep_doctrine.py --json tmp/sweep_doctrine.json   # 전체 (수 시간)
    python scripts/sweep_doctrine.py --only entry_kcas                # 스모크
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.guidance.doctrine import Doctrine, DOCTRINE_BOUNDS

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SWEEP_REDS = ("red_attacker", "red_textbook", "red_two_circle")
DEFAULT_BASES = {
    "energy_fighter": os.path.join(ROOT, "examples", "energy_fighter.yaml"),
    "textbook_headon": os.path.join(ROOT, "examples", "textbook_headon.yaml"),
    "fng_burst": None,   # 인라인 (아래 FNG_BURST_TREE)
}

# 예선 1위 FNG 08-15 19:23 제출물의 g_burst 전환판 — 고burst 집단 대표.
# (구 max_g 상시형과 거동이 같지는 않다 — 2026-08-24 조절 법칙 변경)
FNG_BURST_TREE = """\
agent_name: FngBurst
selector:
  - sequence:
      - condition: {name: low_altitude, floor_ft: 5000}
      - action: {pursuit: pure, g_burst: 0.8, aim_above_ft: 4000, name: recover_altitude}
  - sequence:
      - inverter:
          condition: {name: nose_far, ata_deg: 12}
      - action: {pursuit: lead, lead_time_s: 0.2, g_burst: 0.8, name: weak_lead_track}
  - action: {pursuit: lead, g_burst: 0.8, name: lead_chase}
"""


def build_grid() -> dict[str, dict]:
    """{config 이름: doctrine 오버라이드} — baseline 포함."""
    d = Doctrine().to_yaml_dict()
    grid: dict[str, dict] = {"baseline": {}}
    for field, (lo, hi) in DOCTRINE_BOUNDS.items():
        default = d[field]
        if default == lo and default == hi:
            continue                                    # 점잠금 필드 — 스윕 불가
        extremes = [v for v in (lo, hi) if v != default]
        for v in extremes:
            grid[f"{field}={v:g}"] = {field: v}
    return grid


def _run_config(job) -> tuple:
    """워커 (프로세스 병렬) — base 하나 × config 하나 = 건틀릿 24경기."""
    base_name, base_yaml_text, cfg_name, overrides, reds = job
    # 개방 전 스윕이므로 인프로세스 토글 (tests/test_doctrine _TuningOn 선례)
    from aircombat.guidance import doctrine as doctrine_mod
    doctrine_mod.TUNING_ENABLED = True
    from aircombat.engine.tournament import run_gauntlet

    text = base_yaml_text
    if overrides:
        block = "doctrine:\n" + "".join(f"  {k}: {v}\n" for k, v in overrides.items())
        text = block + text
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix=f"sweep_{base_name}_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        games = run_gauntlet(base_name, path, dict(reds))
    finally:
        os.unlink(path)

    s = collections.Counter()
    per_red = collections.defaultdict(collections.Counter)
    for g in games:
        won = g.winner == base_name and g.condition != "no_contact"
        pts = 0 if g.condition == "no_contact" else (3 if won else (1 if g.winner == "draw" else 0))
        s["pts"] += pts
        s["wins"] += int(won)
        s["kill_wins"] += int(won and g.condition == "health_zero")
        s["hp_diff"] += round(g.hp_blue - g.hp_red, 6)
        s[g.condition] += 1
        per_red[g.red]["pts"] += pts
    return base_name, cfg_name, dict(s), {r: dict(c) for r, c in per_red.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", nargs="+", default=None,
                    help="base 트리 YAML 경로들 (기본: 조절형 2종 + 인라인 fng_burst)")
    ap.add_argument("--only", default=None, help="특정 교리 필드만 (스모크)")
    ap.add_argument("--json", default="tmp/sweep_doctrine.json")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    grid = build_grid()
    if args.only:
        grid = {n: o for n, o in grid.items()
                if n == "baseline" or n.startswith(args.only + "=")}

    bases: dict[str, str] = {}
    if args.base:
        for p in args.base:
            bases[os.path.splitext(os.path.basename(p))[0]] = open(p, encoding="utf-8").read()
    else:
        for name, path in DEFAULT_BASES.items():
            bases[name] = FNG_BURST_TREE if path is None else open(path, encoding="utf-8").read()

    reds = tuple((r, os.path.join(ROOT, "redteams", f"{r}.yaml")) for r in SWEEP_REDS)
    jobs = [(bn, bt, cn, ov, reds) for bn, bt in bases.items()
            for cn, ov in grid.items()]
    total_games = len(jobs) * len(reds) * 8
    print(f"스윕: base {len(bases)} × config {len(grid)} = {len(jobs)} 건틀릿 "
          f"({total_games}경기), workers={args.workers}", flush=True)

    results: dict[str, dict] = collections.defaultdict(dict)
    done = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_run_config, j): j for j in jobs}
        for fut in concurrent.futures.as_completed(futs):
            base_name, cfg_name, summary, per_red = fut.result()
            results[base_name][cfg_name] = {"summary": summary, "per_red": per_red}
            done += 1
            print(f"[{done:>3}/{len(jobs)}] {base_name:<16} {cfg_name:<24} "
                  f"pts={summary.get('pts', 0):>2} wins={summary.get('wins', 0):>2} "
                  f"nc={summary.get('no_contact', 0)}", flush=True)

    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\nJSON: {args.json}\n", flush=True)

    # Δpts 표 (baseline 대비) — 지배 판정의 1차 자료
    for base_name, cfgs in results.items():
        bl = cfgs.get("baseline", {}).get("summary", {}).get("pts", 0)
        print(f"== {base_name}  baseline pts={bl}")
        rows = sorted(((c["summary"].get("pts", 0) - bl, n)
                       for n, c in cfgs.items() if n != "baseline"), reverse=True)
        for dp, n in rows:
            print(f"   {dp:+3d}  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
