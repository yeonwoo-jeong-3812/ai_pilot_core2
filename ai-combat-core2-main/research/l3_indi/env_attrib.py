"""봉투 초과의 원인 분해 — 기체 모델인가, G 봉투인가.

A36 2단계는 모델(f16 → f16fix)과 봉투(platform → manual)를 **동시에** 바꿨다.
기준 설정의 봉투 초과가 7.5 % → 0.0 % 로 사라졌는데, 둘 중 무엇 때문인지 가르지 못한다.
2 × 2 중 빠진 두 칸을 채운다. 기준 설정만, 확증 실행과 같은 솔트 8 개.

  A  f16    + platform   = A35 확증 실행 (이미 있음, 7.5 %)
  B  f16fix + manual     = A36 재실행 (이미 있음, 0.0 %)
  C  f16fix + platform   ← 이 스크립트
  D  f16    + manual     ← 이 스크립트

C 가 0 % 에 가까우면 원인은 **기체 모델**, D 가 0 % 에 가까우면 원인은 **봉투**다.

사용: python research/l3_indi/env_attrib.py [--processes 8]   (320 경기, 약 18 분)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi import dogfight as D                          # noqa: E402
from l3_indi.harness import REPO                           # noqa: E402

CELLS = (("C_f16fix_platform", "f16fix", "platform"),
         ("D_f16_manual", "f16", "manual"))
OUT = os.path.join(REPO, "results", "paper", "env_attrib")

# 경기별 봉투 초과 정의는 A31 §5·A33 과 같다 (청군 기준).
exceed = lambda r: float(r["nz_max"] > 9.0 or r["nz_min"] < -3.0 or r["alpha_max_deg"] > 30.0)


def build():
    grid = D.load_grid(os.path.join(HERE, "dogfight_grid_a36.json"))
    jobs = []
    for cname, model, env in CELLS:
        for j in D.build_jobs(grid, ["BASE"], n_salts=8, salt_offset=8):
            j = json.loads(json.dumps(j))
            j["setting"] = dict(j["setting"], model=model, envelope=env)
            D.Setting.from_dict(j["setting"])              # 검증
            j["setting_name"] = cname
            j["match_id"] = f"{cname}__{j['match_id'].split('__', 1)[1]}"
            jobs.append(j)
    return jobs


def main(processes: int = 8) -> int:
    import multiprocessing as mp
    jobs = build()
    print(f"[env] 셀 {len(CELLS)} × 경기 {len(jobs)//len(CELLS)} = {len(jobs)} 경기")
    with mp.get_context("spawn").Pool(processes) as pool:
        rows = pool.map(D.play, jobs, chunksize=1)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "runs.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, default=float)

    print()
    print("| 칸 | 기체 | 봉투 | 경기 | 봉투 초과 [%] | 최대 Nz [G] | 최소 Nz | α 최대 [°] |")
    print("|---|---|---|---|---|---|---|---|")
    print("| A | f16 | platform | 160 | **7.5** | 9.59 | −3.48 | 16.6 | (A35 확증)")
    for cname, model, env in CELLS:
        G = [r for r in rows if r["setting_name"] == cname]
        print(f"| {cname[0]} | {model} | {env} | {len(G)} | **{100*np.mean([exceed(r) for r in G]):.1f}** | "
              f"{max(r['nz_max'] for r in G):.2f} | {min(r['nz_min'] for r in G):.2f} | "
              f"{max(r['alpha_max_deg'] for r in G):.1f} |")
    print("| B | f16fix | manual | 160 | **0.0** | 7.62 | −1.21 | 14.2 | (A36 재실행)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processes", type=int, default=8)
    raise SystemExit(main(ap.parse_args().processes))
