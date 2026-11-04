"""다른 커밋·PC 로 돌린 shard 파일 표본 재현 점검. 파일에서 무작위 N경기 (seed 고정) 를 이 PC 에서 다시 돌려 비교한다. 읽기 전용.

  python bt/verify_shard.py bt/out/bt-main/games_main_lhs64_shard2of3.csv            # 20경기, seed 20261108
  python bt/verify_shard.py <파일> --n 20 --seed 20261108 --procs 4

비교 열 = run_bt.FIELDS 에서 실행 환경 열 (wall_s, host, code_commit, python_version) 을 뺀 전부 (engine_sha 포함).
값은 CSV 에 적힌 문자열 그대로 비교한다 (run_bt 가 쓰는 형식과 같다). 모두 같으면 종료 코드 0, 하나라도 다르면 1.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from multiprocessing import Pool

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402

ENV = ("wall_s", "host", "code_commit", "python_version")
COMPARED = [k for k in run_bt.FIELDS if k not in ENV]


def job_from_row(row: dict, engine_sha: str) -> dict:
    """CSV 한 줄 → run_bt.play 가 받는 경기. θ·트리·시드는 줄에 적힌 값으로 다시 만든다."""
    r0 = row["stage"] == "r0"
    th = mt.normalize({k: row[k] for k in mt.NAMES + ["dummy"]}, r0)
    if mt.theta_id(th, r0) != row["theta_id"]:
        raise ValueError(f"theta_id 불일치: 줄 {row['theta_id']} ≠ 다시 계산 {mt.theta_id(th, r0)}")
    return dict(stage=row["stage"], theta_id=row["theta_id"], theta=th, tree=mt.make_tree(th, r0),
                scenario=row["scenario"], opponent=row["opponent"], opponent_set=row["opponent_set"],
                seed_salt=row["seed_salt"], seed=int(row["seed"]), engine_sha=engine_sha, code_commit="verify_shard")


def verify(path: str, n: int = 20, seed: int = 20261108, procs: int = 4) -> list[dict]:
    """[{key, same, diff: {열: (파일 값, 다시 돌린 값)}}]."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    pick = random.Random(seed).sample(rows, min(n, len(rows)))
    sha = run_bt.engine_sha()
    jobs = [job_from_row(r, sha) for r in pick]
    with Pool(procs) as pool:
        new = pool.map(run_bt.play, jobs)
    out = []
    for old, nw in zip(pick, new):
        diff = {k: (old[k], str(nw[k])) for k in COMPARED if old[k] != str(nw[k])}
        out.append(dict(key="/".join(old[k] for k in ("theta_id", "scenario", "opponent", "seed_salt")),
                        commit=old["code_commit"], same=not diff, diff=diff))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261108)
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    res = verify(a.path, a.n, a.seed, a.procs)
    print(f"# verify_shard: {a.path}")
    print(f"표본 {len(res)}경기 (seed {a.seed}), 이 PC code_commit {run_bt.code_commit()}, engine_sha {run_bt.engine_sha()}")
    print(f"비교 열 {len(COMPARED)}개 (실행 환경 열 {', '.join(ENV)} 제외)\n")
    print("| 경기 (theta_id/기하/상대/시드) | 파일 code_commit | 같음 | 다른 열 |")
    print("|---|---|---|---|")
    for r in res:
        print(f"| {r['key']} | {r['commit']} | {'O' if r['same'] else 'X'} | "
              + (", ".join(f"{k}: {a} → {b}" for k, (a, b) in r["diff"].items()) or "—") + " |")
    bad = sum(not r["same"] for r in res)
    print(f"\n**{'모두 같음' if not bad else f'{bad}경기 다름'}** ({len(res) - bad}/{len(res)})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
