"""롤 맛보기 (탐색 분석, 판정 아님). 2026-10-19.

E2·E3 의 43개 조건(BASE 포함)을 시드 main-0, 시나리오 neutral 하나로 다시 돌리면서 롤 추종 오차도 기록한다.
키트 파일은 고치지 않는다. run.py 의 주입·기록은 그대로 쓰고, 그 바깥에 롤 기록만 한 겹 더 씌운다.
같은 PC 에서는 결정론이므로 승패·종료 사유·피치 추종 오차는 기존 games.csv 와 같아야 한다 (분석에서 확인).

미리 정한 비교 (결과를 보기 전, 2026-10-19):
  지표  E3 22개 조건의 D 예측 오차 RMS (조건 단위). 피치만 쓴 등록 곡선은 0.041
  모형  P  D = a + b·피치오차            (등록 곡선과 같은 모양)
        PR D = a + b·피치오차 + c·롤오차  (E2 로 적합)
        S  D = a + b·(피치오차 + 롤오차)
  판단  롤을 넣은 모형의 RMS 가 P 보다 20 % 이상 줄면 "의미 있게 나아짐", 5 % 미만이면 "나아지지 않음", 그 사이 "약간"
  함께 κ·k_q 조건(피치에만 주입)의 롤 추종 오차가 BASE 와 같은지

  python roll_pilot.py        # 실행 (끊기면 다시 치면 이어서)
"""
import csv
import ctypes
import os
import sys
import time

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "roll_pilot_games.csv")
LOG = os.path.join(HERE, "roll_pilot.log")
sys.path.insert(0, KIT)
os.chdir(KIT)
import run  # noqa: E402  (Pilot.setup 패치와 피치 기록 포함)
from experiments import AGENTS_MAIN, FIT_CONDS, TEST_CONDS  # noqa: E402

ROLL: dict = {}
_orig_apply = run.apply_knobs


def apply_knobs_roll(pilot, knobs, seed):
    """run.apply_knobs 를 그대로 건 뒤, 그 바깥에서 롤 명령과 실제 롤 각속도(잡음·지연 전)를 누적한다."""
    _orig_apply(pilot, knobs, seed)
    inner = pilot.indi.update
    st = ROLL[pilot.color] = dict(n=0, ae=0.0, sx=0.0, sy=0.0, sxx=0.0, syy=0.0, sxy=0.0, acmd=0.0)

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        x, y = np.degrees(omega_sp[0]), np.degrees(np.asarray(omega, float)[0])
        st["n"] += 1; st["sx"] += x; st["sy"] += y; st["sxx"] += x * x; st["syy"] += y * y
        st["sxy"] += x * y; st["ae"] += abs(x - y); st["acmd"] += abs(x)
        return inner(omega, omega_sp, qbar, ang_accel=ang_accel, **kw)

    pilot.indi.update = update


run.apply_knobs = apply_knobs_roll       # run._patched_setup 이 호출 시점에 이 이름을 찾는다
FIELDS = run.FIELDS + ["blue_mae_p_dps", "red_mae_p_dps", "blue_corr_p", "red_corr_p",
                       "blue_cmd_p_dps", "red_cmd_p_dps"]


def play(job):
    ROLL.clear()
    r = run.play(job)
    for c, k in (("Blue", "blue"), ("Red", "red")):
        s = ROLL[c]
        r[f"{k}_mae_p_dps"] = round(s["ae"] / s["n"], 4)
        r[f"{k}_corr_p"] = round(run._corr(s), 4)
        r[f"{k}_cmd_p_dps"] = round(s["acmd"] / s["n"], 3)
    return r


def jobs():
    exp = dict(agents=AGENTS_MAIN, scenarios=("neutral",), salt="main", conds=["BASE"] + FIT_CONDS + TEST_CONDS)
    return run.build_jobs(exp, 1)


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def main():
    import multiprocessing as mp
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # 실행 중 절전 막기
    js = jobs()
    done = set()
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as f:
            done = {run._key(r) for r in csv.DictReader(f)}
    todo = [j for j in js if run._key(j) not in done]
    log(f"시작: 전체 {len(js)}판, 기록됨 {len(js) - len(todo)}, 남음 {len(todo)}")
    new = not os.path.isfile(OUT)
    t0 = time.time()
    with mp.Pool(14) as pool, open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"{i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")
    log("끝")


if __name__ == "__main__":
    main()
