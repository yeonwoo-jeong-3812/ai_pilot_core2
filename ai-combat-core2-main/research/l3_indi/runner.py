"""병렬 실행 + 출처 기록. 커밋 안 된 코드로는 본실행을 거부한다(PREREGISTRATION §2.4, 계획 G6).

사용 예 (실험 스크립트에서):
    from l3_indi.runner import run_experiment
    run_experiment("rq1_pilot", jobs, job_fn, out_root)

`jobs` 는 JSON 직렬화 가능한 dict 목록, `job_fn(job) -> dict` 는 한 런의 요약 행을 돌려준다.
"""
from __future__ import annotations

import csv
import json
import multiprocessing as mp
import os
import platform
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 결과에 영향을 주는 코드·데이터 경로. 여기에 커밋 안 된 변경이 있으면 거부한다.
GUARDED_PATHS = ("research/l3_indi", "aircombat", "jsbsim_data", "examples", "roster", "agents")


class DirtyTreeError(RuntimeError):
    pass


def _git(*args) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True,
                                   encoding="utf-8", errors="replace").strip()


def git_state(paths=GUARDED_PATHS) -> dict:
    status = _git("status", "--porcelain", "--untracked-files=all", "--", *paths)
    dirty = [ln for ln in status.splitlines()
             if ln.strip() and "__pycache__" not in ln and not ln.endswith(".pyc")]
    return {"commit": _git("rev-parse", "HEAD"), "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty_files": dirty, "clean": not dirty}


def require_clean(paths=GUARDED_PATHS) -> dict:
    st = git_state(paths)
    if not st["clean"]:
        raise DirtyTreeError("커밋 안 된 변경이 있어 실행을 거부함:\n  " + "\n  ".join(st["dirty_files"]))
    return st


def _init_worker():
    # 워커가 JSBSim 배너를 대량 출력하지 않도록
    sys.stdout = open(os.devnull, "w")


def run_experiment(name: str, jobs: list, job_fn, out_root: str,
                   processes: int = 8, allow_dirty: bool = False) -> str:
    st = git_state()
    if not st["clean"] and not allow_dirty:
        raise DirtyTreeError("커밋 안 된 변경이 있어 실행을 거부함:\n  " + "\n  ".join(st["dirty_files"]))
    out_dir = os.path.join(out_root, name, st["commit"][:10])
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    with mp.get_context("spawn").Pool(processes, initializer=_init_worker) as pool:
        rows = pool.map(job_fn, jobs, chunksize=1)
    wall = time.time() - t0
    keys = sorted({k for r in rows for k in r})
    with open(os.path.join(out_dir, "runs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    manifest = {"experiment": name, "git": st, "allow_dirty": allow_dirty,
                "n_jobs": len(jobs), "wall_s": round(wall, 1), "processes": processes,
                "python": sys.version, "platform": platform.platform(),
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "preregistration": "docs/PREREGISTRATION.md"}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False)
    return out_dir
