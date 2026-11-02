"""θ 목록 × 48셀(교전 기하 3 × 상대 4 × 시드 4) 실행기. 규칙은 bt/CONTRACT.md.

  python bt/run_bt.py bt/thetas/baseline.csv                 # 기본 접두어 bt-smoke
  python bt/run_bt.py thetas.json --prefix bt-pilot --procs 6
  python bt/run_bt.py thetas.csv --dry                       # 경기 수만 센다
  python bt/run_bt.py thetas.csv --limit 10                  # 남은 경기 중 앞 10개만
  python bt/run_bt.py thetas.csv --prefix bt-main --unlock-confirm
  python bt/run_bt.py bt/thetas/r0.csv --prefix bt-cal --r0  # R0 검증: 범위 밖 θ 허용, stage=r0, 결과 bt/out/r0/
  python bt/run_bt.py thetas.csv --opponents original        # kit 원본 상대 (기본은 patched)
  python bt/run_bt.py thetas.csv --prefix bt-main --unlock-confirm --shard 2/3   # 3대 중 2번째 PC 몫 (bt/RUNBOOK.md)

실행 전 점검 (bt/RUNBOOK.md): bt/ 에 커밋 안 된 수정이 없고, Python 버전·crosscheck 전체 해시가 CONTRACT.md §8 과 같아야 돈다.
진단용으로만 --force-dev 로 건너뛴다. --dry 는 점검하지 않는다.

결과: bt/out/<접두어>/games.csv, 1경기 1줄. 이미 기록된 경기는 건너뛴다(끊기면 같은 명령으로 재개).
run.py 를 import 하지 않는다 (run.py 는 import 시 Pilot.setup 을 감싼다). 경기 조립은 bridge.CompetitionMatch.run 과
같은 순서로 하고, Match 를 직접 만들어 wez_time·ata_mean 과 관측기 값을 받는다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time

BT = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(BT)
sys.path.insert(0, KIT)
sys.path.insert(0, BT)

from aircombat.bridge import _ranked_healths, derive_seed  # noqa: E402
from aircombat.engine.factory import load_policy, make_pilot  # noqa: E402
from aircombat.engine.match import Match  # noqa: E402
from aircombat.engine.scenarios import initial_conditions  # noqa: E402
import make_tree as mt  # noqa: E402
import monitor  # noqa: E402

SCENARIOS = ("perch_offense", "perch_defense", "neutral")
OPPONENTS = {   # 이름 -> kit 기준 경로. 상대를 바꿀 때는 여기만 고친다
    "A2_GunTracker_00": "agents/main/A2_GunTracker_00.yaml",
    "B2_Extender_00": "agents/main/B2_Extender_00.yaml",
    "C1_TwoCircleRate_00": "agents/main/C1_TwoCircleRate_00.yaml",
    "D1_Reactive_00": "agents/main/D1_Reactive_00.yaml",
}
# 상대 묶음 (--opponents). 이름은 같고 파일만 다르다. CSV 의 opponent_set 열로 구분한다.
#   original    kit/agents/main 원본 (고치지 않는다)
#   patched     bt/opponents_patched: 최우선 low_altitude → climb 노드만 청 recover 와 같게 (bt/analysis/opponent_patch_rules.md)
#   diag-f4000  bt/diag_opponents: floor_ft 만 1200 → 4000 (하드덱 진단 전용, bt-diag 에서만)
OPPONENT_SETS = {
    "original": OPPONENTS,
    "patched": {k: "bt/opponents_patched/" + os.path.basename(v) for k, v in OPPONENTS.items()},
    "diag-f4000": {k: "bt/diag_opponents/" + os.path.basename(v) for k, v in OPPONENTS.items()},
}
DEFAULT_SET = "patched"
# 옛 CSV (opponent_set 열 없음) 재실행용: 원본 이름 = original, "<이름>_f4000" = diag-f4000
OPP_PATHS = {**OPPONENTS, **{f"{k}_f4000": v for k, v in OPPONENT_SETS["diag-f4000"].items()}}
SEEDS = 4
PREFIXES = ("bt-smoke", "bt-pilot", "bt-cal", "bt-cal-a", "bt-cal-b", "bt-diag", "bt-main", "bt-confirm")
LOCKED = ("bt-main", "bt-confirm")
ENGINE_PARTS = ("aircombat", "jsbsim_data", "config")

FIELDS = (["stage", "theta_id"] + mt.NAMES +
          ["dummy", "scenario", "opponent", "opponent_set", "seed_salt", "seed",
           "winner", "end_reason", "win_mode", "hp_blue", "hp_red", "hp_blue_raw", "hp_red_raw", "wez_blue", "wez_red",
           "ata_mean_blue", "ata_mean_red", "off_frac", "def_frac", "e_adv_ft", "t_first_wez", "node_frac", "node_frac_red",
           "sim_time_s", "wall_s", "engine_sha", "tree_sha", "code_commit", "host", "python_version"])
KEY = ("stage", "theta_id", "scenario", "opponent", "opponent_set", "seed_salt")


def engine_sha() -> str:
    """aircombat/ jsbsim_data/ config/ 의 .py·데이터 파일 내용 해시. 줄끝(CRLF/LF)과 __pycache__ 는 무시한다."""
    h = hashlib.sha256()
    for part in ENGINE_PARTS:
        for root, dirs, files in os.walk(os.path.join(KIT, part)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                if name.endswith((".pyc", ".pyo")):
                    continue
                p = os.path.join(root, name)
                h.update(os.path.relpath(p, KIT).replace("\\", "/").encode() + b"\0")
                with open(p, "rb") as f:
                    h.update(f.read().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:12]


def code_commit() -> str:
    """실행 시점 git 커밋 해시 (짧은 형식). git 저장소가 아니면 "unknown"."""
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=BT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def shard(jobs: list[dict], spec: str | None) -> list[dict]:
    """--shard i/n: build_jobs 순서의 k 번째 경기를 (k mod n) + 1 번 몫으로. 같은 θ 목록·n 이면 겹치지 않고 빠짐없이 나뉜다."""
    if not spec:
        return jobs
    m = re.fullmatch(r"(\d+)/(\d+)", spec)
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        raise ValueError(f"--shard 는 i/n (1 ≤ i ≤ n) 형식: {spec!r}")
    i, n = int(m.group(1)), int(m.group(2))
    return [j for k, j in enumerate(jobs) if k % n == i - 1]


def preflight() -> list[str]:
    """실행 전 점검. 문제 목록 (빈 목록 = 통과). CONTRACT.md §8 의 Python 버전·crosscheck 전체 해시와 비교한다."""
    problems = []
    try:
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=BT, capture_output=True,
                               text=True, check=True).stdout.strip()
        if dirty:
            problems.append("bt/ 에 커밋 안 된 수정이 있다:\n" + dirty)
    except (OSError, subprocess.CalledProcessError) as e:
        problems.append(f"git 상태를 읽을 수 없다: {e}")
    with open(os.path.join(BT, "CONTRACT.md"), encoding="utf-8") as f:
        contract = f.read()
    want_py = re.search(r"\| python_version \| ([\d.]+) \|", contract).group(1)
    want_hash = re.search(r"\| \*\*전체 해시\*\* \| \*\*`([0-9a-f]+)`\*\* \|", contract).group(1)
    if platform.python_version() != want_py:
        problems.append(f"Python {platform.python_version()} ≠ CONTRACT {want_py}")
    import crosscheck
    got = crosscheck.compute()["overall"]
    if got != want_hash:
        problems.append(f"crosscheck 전체 해시 {got} ≠ CONTRACT {want_hash}")
    return problems


def win_mode(winner: str, end_reason: str) -> str:
    """청 승리 방식. 청이 이기지 않았으면 빈칸."""
    if winner != "blue":
        return ""
    return {"health_zero": "shootdown", "hard_deck": "opp_hard_deck", "stall": "opp_stall",
            "timeout": "judge", "overtime": "judge"}.get(end_reason, "other")


def read_thetas(path: str, r0: bool = False) -> list[dict]:
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    return [mt.normalize(r, r0) for r in rows]


def read_rows(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, "rb+") as f:                       # 쓰다 꺼져 잘린 마지막 줄 정리 (run_extra.py 와 같다)
        data = f.read()
        if data and not data.endswith(b"\n"):
            f.seek(data.rfind(b"\n") + 1); f.truncate()
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_jobs(thetas: list[dict], prefix: str, r0: bool = False, opponent_set: str = DEFAULT_SET) -> list[dict]:
    """시드는 prefix 로 정한다. r0 면 stage 만 "r0" 로 기록한다 (시드는 prefix 그대로)."""
    jobs, seen = [], set()
    for th in thetas:
        tid, tree = mt.theta_id(th, r0), mt.make_tree(th, r0)
        if tid in seen:          # 같은 θ 가 목록에 두 번 있으면 한 번만
            continue
        seen.add(tid)
        for i in range(SEEDS):
            salt = f"{prefix}-{i}"
            for scen in SCENARIOS:
                for opp in OPPONENT_SETS[opponent_set]:
                    jobs.append(dict(stage="r0" if r0 else prefix, theta_id=tid, theta=th, tree=tree,
                                     scenario=scen, opponent=opp, opponent_set=opponent_set, seed_salt=salt,
                                     seed=derive_seed(scen, salt)))   # run.py 와 같은 시드 규칙
    return jobs


def _r(v, nd):
    return "" if v is None else round(float(v), nd)


def play(job: dict) -> dict:
    """1경기. 청 = θ 트리, 적 = 상대. bridge.CompetitionMatch.run 과 같은 조립·판정 규약."""
    t0 = time.time()
    me, foe = load_policy(job["tree"]), load_policy(os.path.join(KIT, OPPONENT_SETS[job["opponent_set"]][job["opponent"]]))
    ic = initial_conditions(job["scenario"], seed=job["seed"])
    blue = make_pilot("Blue", ic["blue"], *me, name="EnergyFighterBT")
    red = make_pilot("Red", ic["red"], *foe, name=job["opponent"])
    mon = monitor.attach(blue, red)
    m = Match(blue, red, duration_s=300.0, acmi_path=None, log_hz=0.0,
              acmi_comments=f"scenario={job['scenario']};seed={job['seed']}", overtime_s=0.0)
    r = m.run()
    hp_b, hp_r = _ranked_healths({"blue": "tree1", "red": "tree2", "draw": "draw"}[r.winner],
                                 r.condition, r.hp_blue, r.hp_red)   # 판정패 HP 0 (run.py 결과와 같은 규약)
    s = mon.summary()
    th = job["theta"]
    return {"stage": job["stage"], "theta_id": job["theta_id"],
            **{k: th[k] for k in mt.NAMES}, "dummy": "" if th["dummy"] is None else th["dummy"],
            "scenario": job["scenario"], "opponent": job["opponent"], "opponent_set": job["opponent_set"],
            "seed_salt": job["seed_salt"], "seed": job["seed"],
            "winner": r.winner, "end_reason": r.condition, "win_mode": win_mode(r.winner, r.condition),
            "hp_blue": _r(hp_b, 2), "hp_red": _r(hp_r, 2),
            "hp_blue_raw": _r(r.hp_blue, 2), "hp_red_raw": _r(r.hp_red, 2),
            "wez_blue": _r(r.wez_time["blue"], 4), "wez_red": _r(r.wez_time["red"], 4),
            "ata_mean_blue": _r(r.ata_mean["blue"], 3), "ata_mean_red": _r(r.ata_mean["red"], 3),
            "off_frac": _r(s["off_frac"], 4), "def_frac": _r(s["def_frac"], 4),
            "e_adv_ft": _r(s["e_adv_ft"], 1), "t_first_wez": _r(s["t_first_wez"], 2),
            "node_frac": s["node_frac"] or "", "node_frac_red": s["node_frac_red"] or "",
            "sim_time_s": _r(r.time_s, 4), "wall_s": _r(time.time() - t0, 1),
            "engine_sha": job["engine_sha"], "tree_sha": mt.tree_sha(job["tree"]), "code_commit": job["code_commit"],
            "host": socket.gethostname(), "python_version": platform.python_version()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("thetas", help="θ 목록 CSV 또는 JSON")
    ap.add_argument("--prefix", default="bt-smoke", choices=PREFIXES)
    ap.add_argument("--unlock-confirm", action="store_true", help="bt-main·bt-confirm 실행 허용 (확증용)")
    ap.add_argument("--procs", type=int, default=6, help="병렬 프로세스 수 (코어 수보다 작게)")
    ap.add_argument("--r0", action="store_true", help="R0 검증: params.yaml 범위 밖 θ 허용, stage=r0, 결과 bt/out/r0/")
    ap.add_argument("--opponents", default=DEFAULT_SET, choices=list(OPPONENT_SETS),
                    help=f"상대 묶음 (기본 {DEFAULT_SET}). original = kit 원본, diag-f4000 = bt-diag 전용")
    ap.add_argument("--shard", help="i/n: n 대 중 i 번째 몫만 (결과 파일 games_shard<i>of<n>.csv)")
    ap.add_argument("--force-dev", action="store_true", help="진단용: 실행 전 점검 (커밋·Python·crosscheck) 을 건너뛴다")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, help="남은 경기 중 앞 N개만")
    args = ap.parse_args()
    if args.prefix in LOCKED and not args.unlock_confirm:
        ap.error(f"{args.prefix} 는 확증 시드다. 정말 돌릴 때만 --unlock-confirm 을 붙인다")
    if args.opponents == "diag-f4000" and args.prefix != "bt-diag":
        ap.error("--opponents diag-f4000 은 --prefix bt-diag 에서만 쓴다")
    try:
        jobs = shard(build_jobs(read_thetas(args.thetas, args.r0), args.prefix, args.r0, args.opponents), args.shard)
    except ValueError as e:
        ap.error(str(e))
    out_dir = os.path.join(BT, "out", "r0" if args.r0 else args.prefix)
    name = "games.csv" if not args.shard else "games_shard{}of{}.csv".format(*args.shard.split("/"))
    path = os.path.join(out_dir, name)
    rows = read_rows(path)
    if rows and list(rows[0]) != FIELDS:
        sys.exit(f"{path} 의 열이 지금 계약(FIELDS)과 다르다. 옛 형식 파일은 다른 이름으로 옮기고 다시 돌린다")
    done = {tuple(r[k] for k in KEY) for r in rows}
    todo = [j for j in jobs if tuple(str(j[k]) for k in KEY) not in done]
    print(f"{args.prefix}: 전체 {len(jobs)}경기, 기록됨 {len(jobs) - len(todo)}, 남음 {len(todo)}")
    todo = todo[:args.limit]
    if args.dry or not todo:
        return
    if args.force_dev:
        print("⚠ --force-dev: 실행 전 점검을 건너뛴다 (진단용. 본실험 결과에 쓰지 않는다)")
    else:
        print("실행 전 점검 (커밋 상태, Python, crosscheck 10경기) ...", flush=True)
        problems = preflight()
        if problems:
            sys.exit("실행 거부:\n- " + "\n- ".join(problems) + "\n(진단용으로만 --force-dev)")
        print("  통과", flush=True)
    sha, commit = engine_sha(), code_commit()
    for j in todo:
        j["engine_sha"], j["code_commit"] = sha, commit
    os.makedirs(out_dir, exist_ok=True)
    import multiprocessing as mp
    new = not os.path.isfile(path)
    t0, n_wall = time.time(), 0
    with mp.Pool(args.procs) as pool, open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            n_wall += row["end_reason"] == "wall_clock"
            if i % 12 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s", flush=True)
    print(f"기록: {path}  (wall_clock {n_wall}경기)")


if __name__ == "__main__":
    main()
