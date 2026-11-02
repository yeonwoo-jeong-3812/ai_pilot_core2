"""PC 간 재현 점검. 고정 10경기(기준 θ, bt-smoke 시드)를 돌려 결과 열의 해시를 찍는다. 읽기 전용, 파일을 쓰지 않는다.

  python bt/crosscheck.py            # cadet_research/kit/ 에서. 약 1–2분

찍힌 "전체 해시"가 CONTRACT.md 의 기준 해시와 같으면 이 PC 는 기준 PC 와 같은 결과를 낸다.
다르면 경기별 해시로 어느 경기가 다른지 보고, engine_sha·Python 버전부터 맞춘다.
해시에 넣는 열 = run_bt.FIELDS 에서 실행 환경 열(wall_s, host, python_version, engine_sha)을 뺀 전부.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from multiprocessing import Pool

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402

CELLS = [   # (기하, 상대, 시드 번호) — 기하 3종 × 상대 4 를 섞은 고정 10경기
    ("perch_offense", "A2_GunTracker_00", 0), ("perch_offense", "C1_TwoCircleRate_00", 1),
    ("perch_offense", "D1_Reactive_00", 2), ("perch_defense", "B2_Extender_00", 0),
    ("perch_defense", "D1_Reactive_00", 1), ("perch_defense", "A2_GunTracker_00", 3),
    ("neutral", "A2_GunTracker_00", 0), ("neutral", "B2_Extender_00", 2),
    ("neutral", "C1_TwoCircleRate_00", 3), ("neutral", "D1_Reactive_00", 1),
]
ENV = ("wall_s", "host", "python_version", "engine_sha")
HASHED = [k for k in run_bt.FIELDS if k not in ENV]


def row_hash(row: dict) -> str:
    return hashlib.sha256(json.dumps([str(row[k]) for k in HASHED]).encode()).hexdigest()[:12]


def main():
    sha = run_bt.engine_sha()
    jobs = {(j["scenario"], j["opponent"], int(j["seed_salt"].rsplit("-", 1)[1])): j
            for j in run_bt.build_jobs([mt.normalize({**mt.BASE, "dummy": mt.DUMMY["base"]})], "bt-smoke")}
    todo = [dict(jobs[c], engine_sha=sha) for c in CELLS]
    with Pool(min(5, os.cpu_count() or 1)) as pool:
        rows = pool.map(run_bt.play, todo)
    hashes = [row_hash(r) for r in rows]
    for c, r, h in zip(CELLS, rows, hashes):
        print(f"  {c[0]:<14} {c[1]:<20} bt-smoke-{c[2]}  {r['winner']:<5} {r['end_reason']:<12} {h}")
    print(f"python_version {platform.python_version()}")
    print(f"engine_sha     {sha}")
    print(f"전체 해시      {hashlib.sha256(''.join(hashes).encode()).hexdigest()[:16]}")
    if any(r["end_reason"] == "wall_clock" for r in rows):
        print("주의: wall_clock 경기가 있다 (PC 가 바쁨). 다른 프로그램을 닫고 다시 돌린다")


if __name__ == "__main__":
    main()
