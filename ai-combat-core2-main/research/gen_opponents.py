"""T2/T4 상대 생성기 — 검증 신선도 공급(자가발전 사이클의 재료).

기존 로스터 아키타입(순정 DSL yaml)에 **시드 선언 변이**를 가해 새 상대를 만든다.
변이는 두 급:
  · 수치 섭동(T2): 조건 문턱값 ±20% — 가족 내 보간(약한 신규성)
  · 구조 변이(T4-lite): 추격 조준점 교체(lead↔lag↔pure), 수직 편향 주입
    (aim_above_ft ±2000~8000 — 기존 로스터에 없는 수직 기동 방향), commit 시간 변형
생성물은 즉시 신뢰하지 않는다 — **역량 필터**(official_default 상대로 1판: 60s 이상
생존 & 데미지>10 or 승리)를 통과한 것만 로스터 후보가 된다(자명한 상대 배제).

usage:
  python -m research.gen_opponents make --seed 100 --count 12   # 생성만
  python -m research.gen_opponents filter --seed 100            # 역량 필터(경기 실행)
산출: roster/gen/g<seed>_<k>_<원본>.yaml + roster/gen_s<seed>.txt(양 진영 슬롯)
"""
from __future__ import annotations

import argparse
import copy
import os
import random
import subprocess
import sys

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
GEN = os.path.join(ROOT, "roster", "gen")

# 변이 대상 수치 키(조건 문턱·액션 파라미터)
NUM_KEYS = {"range_ft", "closure_fps", "aspect_deg", "ata_deg", "min_ft", "kcas",
            "floor_ft", "hca_deg", "min_fps", "aim_above_ft", "lead_time_s",
            "lag_dist_ft", "cz_range_ft", "duration_s", "cooldown_s", "wait_s"}
PURSUITS = ["pure", "lead", "lag"]


def _mutate(node, rng: random.Random, log: list):
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if k in NUM_KEYS and isinstance(v, (int, float)):
                f = rng.uniform(0.8, 1.2)
                node[k] = round(v * f, 2)
            elif k == "pursuit" and rng.random() < 0.25:
                new = rng.choice([p for p in PURSUITS if p != v])
                log.append(f"pursuit {v}→{new}")
                node[k] = new
            else:
                _mutate(v, rng, log)
        # 수직 편향 주입(신규 기동 방향): action 에 aim_above 가 없으면 확률 부여
        if "pursuit" in node and "aim_above_ft" not in node and rng.random() < 0.3:
            off = rng.choice([-8000, -4000, -2000, 2000, 4000, 8000])
            node["aim_above_ft"] = off
            log.append(f"수직편향 {off:+d}")
    elif isinstance(node, list):
        for it in node:
            _mutate(it, rng, log)


def make(seed: int, count: int) -> None:
    os.makedirs(GEN, exist_ok=True)
    rng = random.Random(seed)
    bases = sorted(f[:-5] for f in os.listdir(os.path.join(ROOT, "roster"))
                   if f.endswith(".yaml") and not f.startswith("gen"))
    slots = []
    for k in range(count):
        base = rng.choice(bases)
        tree = yaml.safe_load(open(os.path.join(ROOT, "roster", base + ".yaml"),
                                   encoding="utf-8"))
        mut = copy.deepcopy(tree)
        log: list = []
        _mutate(mut, rng, log)
        name = f"g{seed}_{k:02d}_{base}"
        mut["agent_name"] = name
        with open(os.path.join(GEN, name + ".yaml"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(f"# 생성 상대(gen_opponents) — 원본 {base}, 시드 {seed}#{k}\n"
                    f"# 변이: {'; '.join(log) if log else '수치 섭동만'}\n")
            yaml.safe_dump(mut, f, allow_unicode=True, sort_keys=False)
        slots += [f"roster/gen/{name}/blue", f"roster/gen/{name}/red"]
        print(f"{name}: {'; '.join(log) if log else '수치 섭동'}")
    lst = os.path.join(ROOT, "roster", f"gen_s{seed}.txt")
    open(lst, "w", encoding="utf-8", newline="\n").write("\n".join(slots) + "\n")
    print(f"{count}상대 {len(slots)}판 → {lst}  (역량 필터 전 — 후보)")


def filt(seed: int) -> None:
    """역량 필터: 각 생성 상대를 official_default 와 1판 — 자명한 상대 탈락."""
    import re
    lst = os.path.join(ROOT, "roster", f"gen_s{seed}.txt")
    stems = sorted({s.rsplit("/", 1)[0] for s in open(lst, encoding="utf-8")
                    .read().split() if s.strip()})
    keep = []
    for st_ in stems:
        r = subprocess.run([sys.executable, os.path.join("scripts", "run_match.py"),
                            "--blue", st_ + ".yaml",
                            "--red", os.path.join("roster", "official_default.yaml"),
                            "--no-acmi" if False else "--acmi",
                            os.path.join("replays", "genfilter.acmi")],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        m = re.search(r"time\s+:\s+([\d.]+)s", r.stdout or "")
        w = re.search(r"winner\s+:\s+(\w+)", r.stdout or "")
        hp = re.search(r"HP\s+:\s+blue=([\d.]+)\s+red=([\d.]+)", r.stdout or "")
        t = float(m.group(1)) if m else 0.0
        dealt = 100.0 - float(hp.group(2)) if hp else 0.0
        ok = (w and w.group(1) == "blue") or t >= 60.0 and dealt > 10.0
        print(f"{st_}: {'채택' if ok else '탈락'} (t={t:.0f}s dealt={dealt:.0f} "
              f"winner={w.group(1) if w else '?'})")
        if ok:
            keep.append(st_)
    out = os.path.join(ROOT, "roster", f"gen_s{seed}_ok.txt")
    open(out, "w", encoding="utf-8", newline="\n").write(
        "\n".join(f"{s}/{side}" for s in keep for side in ("blue", "red")) + "\n")
    print(f"역량 통과 {len(keep)}/{len(stems)} → {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--count", type=int, default=12)
    p = sub.add_parser("filter")
    p.add_argument("--seed", type=int, required=True)
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.seed, a.count)
    else:
        filt(a.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
