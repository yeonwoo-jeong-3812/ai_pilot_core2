"""P2-a: ASYM U자의 메커니즘을 보기 위한 기록 재생 (사전 등록 ../../PREREG_P2.md).

  python asym_replay.py          # 252경기, 14프로세스로 약 8분 → asym_replay_games.csv, asym_replay_output.md

대상 GunTracker × {BASE, 필터 25 Hz·지연 2틱, 6틱} × 시드 main-0·1. 엔진을 고치지 않는다.
run.play 를 그대로 쓰고 바깥에서 두 군데를 감싼다.
  ① match._wez_damage : 틱마다 사수·표적의 조준각, 거리, 피해
  ② INDI update       : 제어 틱마다 n_z, 받음각, 고도, 피치 명령·응답
먼저 재생 결과가 기록(out/asym, out/main)과 같은지 확인한다.
"""
import collections
import csv
import multiprocessing as mp
import os
import sys

import numpy as np

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # kit/supplementary → kit
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
os.chdir(KIT)
import run  # noqa: E402
from aircombat.engine import match as match_mod  # noqa: E402
from experiments import AGENTS_MAIN, EXPERIMENTS  # noqa: E402

TARGET = "GunTracker"
CONDS = ["F25_D2", "F25_D6"]
SEEDS = ["main-0", "main-1"]
KEY = ("cond", "target", "blue", "red", "scenario", "salt")
WEZ = (500.0, 3000.0)                      # ft
TIERS = (2.0, 10.0, 20.0, 30.0)

LOG = {"wez": [], "ctl": collections.defaultdict(list)}
_orig_wez = match_mod._wez_damage


def wez_logged(shooter, target, dt, overtime=False):
    dmg, ata = _orig_wez(shooter, target, dt, overtime)
    rng = float(np.linalg.norm(np.asarray(shooter.pos_ned) - np.asarray(target.pos_ned)))
    LOG["wez"].append((dmg, ata, rng, float(shooter.alt_ft)))
    return dmg, ata


match_mod._wez_damage = wez_logged
_orig_apply = run.apply_knobs


def apply_logged(pilot, knobs, seed):
    _orig_apply(pilot, knobs, seed)
    inner = pilot.indi.update
    rec = LOG["ctl"][pilot.color]
    plant = pilot.plant

    def update(omega, omega_sp, qbar, ang_accel=None, **kw):
        rec.append((float(plant["accelerations/Nz"]), float(np.degrees(plant["aero/alpha-rad"])),
                    float(plant["position/h-sl-ft"]), float(np.degrees(omega_sp[1])), float(np.degrees(np.asarray(omega)[1]))))
        return inner(omega, omega_sp, qbar, ang_accel=ang_accel, **kw)
    pilot.indi.update = update


run.apply_knobs = apply_logged


def side_stats(w_rows, c_rows):
    w = np.array(w_rows) if w_rows else np.zeros((0, 4))
    c = np.array(c_rows)
    inr = (w[:, 2] >= WEZ[0]) & (w[:, 2] <= WEZ[1])
    out = {"wez_frac": float(np.mean(w[:, 0] > 0)), "dmg_dealt": float(w[:, 0].sum())}
    lo = 0.0
    for hi in TIERS:
        out[f"ata_{int(lo)}_{int(hi)}"] = float(np.mean(inr & (w[:, 1] >= lo) & (w[:, 1] < hi)))
        lo = hi
    out["mean_ata"] = float(np.mean(w[:, 1]))
    nz, al, h, qc, q = c.T
    err = qc - q
    out.update(nz_max=float(nz.max()), nz_over9=float(np.mean(nz > 9.0)), nz_under_m3=float(np.mean(nz < -3.0)),
               alpha_max=float(al.max()), alpha_over25=float(np.mean(al > 25.0)),
               alt_mean=float(h.mean()), alt_below3000=float(np.mean(h < 3000.0)),
               perr_rms=float(np.sqrt(np.mean(err ** 2))),
               perr_zc_hz=float(np.sum(np.diff(np.sign(err)) != 0) / (len(err) / 120.0) / 2.0),
               q_rms=float(np.sqrt(np.mean(q ** 2))))
    return out


def play(job):
    LOG["wez"].clear(); LOG["ctl"].clear()
    r = run.play(job)
    w = LOG["wez"]
    blue_w, red_w = w[0::2], w[1::2]                   # 매 틱 (청 사수, 적 사수) 순서로 불린다
    sb = side_stats(blue_w, LOG["ctl"]["Blue"]); sr = side_stats(red_w, LOG["ctl"]["Red"])
    tb = r["blue"] == TARGET
    row = {k: r[k] for k in ("cond", "target", "blue", "red", "scenario", "salt", "winner", "condition",
                             "hp_blue", "hp_red", "blue_mae_q_dps", "red_mae_q_dps")}
    for pre, s in (("t_", sb if tb else sr), ("o_", sr if tb else sb)):
        row.update({pre + k: v for k, v in s.items()})
    return row


def jobs():
    exp = EXPERIMENTS["ASYM"]
    js = [j for j in run.build_jobs(exp, exp["salts"]) if j["cond"] in CONDS and j["target"] == TARGET and j["salt"] in SEEDS]
    base = [dict(j, cond="BASE", target="") for j in js if j["cond"] == CONDS[0]]
    return base + js


def main():
    js = jobs()
    print(f"재생 {len(js)}경기")
    with mp.Pool(14) as pool:
        rows = pool.map(play, js, chunksize=1)
    rec = {}
    for d in ("asym", "main"):
        for r in csv.DictReader(open(os.path.join(KIT, "out", d, "games.csv"), encoding="utf-8")):
            rec[tuple(r[k] for k in KEY)] = r
    same = sum(all(str(x[k]) == rec[tuple(x[q] for q in KEY)][k] or
                   (k.endswith("dps") and abs(float(x[k]) - float(rec[tuple(x[q] for q in KEY)][k])) < 1e-4)
                   for k in ("winner", "condition", "hp_blue", "hp_red", "blue_mae_q_dps", "red_mae_q_dps")) for x in rows)
    out_csv = os.path.join(HERE, "asym_replay_games.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    lines = ["# P2-a: ASYM 기록 재생 (사전 등록 `PREREG_P2.md`)\n",
             f"대상 {TARGET}, 시드 {', '.join(SEEDS)}, {len(rows)}경기. **재생 일치: {same}/{len(rows)}** (승자·종료 사유·HP·mae)\n"]
    if same != len(rows):
        lines.append("재생이 기록과 다르므로 분석하지 않는다.")
    else:
        metrics = [("t_wez_frac", "대상이 상대를 WEZ 안에 둔 시간 비율"), ("o_wez_frac", "상대가 대상을 WEZ 안에 둔 시간 비율"),
                   ("t_dmg_dealt", "대상이 준 피해 합 [HP]"), ("o_dmg_dealt", "상대가 준 피해 합 [HP]"),
                   ("t_ata_0_2", "대상 조준각 < 2° (WEZ 거리 안) 비율"), ("t_ata_2_10", "대상 조준각 2–10° 비율"),
                   ("t_ata_10_20", "대상 조준각 10–20° 비율"), ("t_ata_20_30", "대상 조준각 20–30° 비율"),
                   ("o_ata_0_2", "상대 조준각 < 2° 비율"), ("o_ata_2_10", "상대 조준각 2–10° 비율"),
                   ("t_mean_ata", "대상 평균 조준각 [°]"), ("o_mean_ata", "상대 평균 조준각 [°]"),
                   ("t_nz_max", "대상 최대 n_z"), ("t_nz_over9", "대상 n_z > 9 비율"), ("t_nz_under_m3", "대상 n_z < −3 비율"),
                   ("t_alpha_max", "대상 최대 받음각 [°]"), ("t_alpha_over25", "대상 받음각 > 25° 비율"),
                   ("o_nz_over9", "상대 n_z > 9 비율"),
                   ("t_alt_mean", "대상 평균 고도 [ft]"), ("t_alt_below3000", "대상 3,000 ft 아래 비율"),
                   ("o_alt_below3000", "상대 3,000 ft 아래 비율"),
                   ("t_perr_rms", "대상 피치 오차 RMS [°/s]"), ("t_perr_zc_hz", "대상 피치 오차 영교차 [Hz]"),
                   ("t_q_rms", "대상 피치 각속도 RMS [°/s]"), ("o_perr_rms", "상대 피치 오차 RMS [°/s]")]
        by = collections.defaultdict(list)
        for r in rows:
            by[r["cond"]].append(r)
        lines.append("| 지표 (경기 평균, 84경기씩) | BASE | 지연 2틱 | 지연 6틱 |")
        lines.append("|---|---|---|---|")
        for k, lab in metrics:
            vals = [np.mean([float(r[k]) for r in by[c]]) for c in ("BASE", "F25_D2", "F25_D6")]
            fmt = "{:.3f}" if max(abs(v) for v in vals) < 10 else "{:.1f}"
            lines.append(f"| {lab} | " + " | ".join(fmt.format(v) for v in vals) + " |")
    txt = "\n".join(lines) + "\n"
    open(os.path.join(HERE, "asym_replay_output.md"), "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    main()
