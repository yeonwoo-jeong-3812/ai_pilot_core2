"""입문 문서(STUDY_GUIDE_INTRO.md) §3의 따라가기 예시 — R_kappa_25 한 조건을 처음부터 끝까지 (읽기 전용, 경기 0판).

  python supplementary/intro_example.py   # → intro_example_output.md (이 파일만 쓴다)

원자료 out/main/games.csv를 읽어 예시 경기 행, 시드별 D, 조건 mae, 등록 곡선의 예측과 잔차를 다시 센다.
mae 계산의 예시는 그림 5의 틱별 기록(fig5_timeseries.csv)에서 다시 계산한다. 등록 판정은 바꾸지 않는다.
"""
from __future__ import annotations

import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
sys.stdout.reconfigure(encoding="utf-8")
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

COND = "R_kappa_25"
KEY = ("blue", "red", "scenario", "salt")
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(KIT, "out", "main", "games.csv"), encoding="utf-8")) if r["target"] == ""]
    base = {tuple(r[k] for k in KEY): r for r in rows if r["cond"] == "BASE"}
    cond = [r for r in rows if r["cond"] == COND]
    say(f"# 입문 문서 따라가기 예시: {COND} (읽기 전용 재계산, 경기 0판)\n")
    say(f"원자료 `out/main/games.csv`. {COND} 경기 {len(cond):,}판, 짝이 되는 BASE 경기 {len(base):,}판.\n")

    say("## 1. 예시 경기 행 (시드 main-0, 청 GunTracker 대 적 Extender)\n")
    say("| 시나리오 | BASE 승자 / 종료 사유 | BASE mae 청·적 | κ 25 승자 / 종료 사유 | κ 25 mae 청·적 | 결과 |")
    say("|---|---|---|---|---|---|")
    for sc in ("headon", "perch_offense", "neutral"):
        k = ("GunTracker", "Extender", sc, "main-0")
        b = base[k]
        c = next(r for r in cond if tuple(r[x] for x in KEY) == k)
        same = (b["winner"], b["condition"]) == (c["winner"], c["condition"])
        say(f"| {sc} | {b['winner']} / {b['condition']} | {b['blue_mae_q_dps']} · {b['red_mae_q_dps']} | "
            f"{c['winner']} / {c['condition']} | {c['blue_mae_q_dps']} · {c['red_mae_q_dps']} | {'같음' if same else '**다름**'} |")

    say("\n## 2. 시드별 결과 변화와 mae\n")
    say("| 시드 | 경기 | 다른 경기 (승자 변화 + 종료 사유만) | D | 조건 mae [°/s] |")
    say("|---|---|---|---|---|")
    tw = to = tn = 0
    for s in [f"main-{i}" for i in range(8)]:
        gs = [r for r in cond if r["salt"] == s]
        w = o = 0
        for g in gs:
            b = base[tuple(g[x] for x in KEY)]
            if g["winner"] != b["winner"]:
                w += 1
            elif g["condition"] != b["condition"]:
                o += 1
        m = np.mean([(float(g["blue_mae_q_dps"]) + float(g["red_mae_q_dps"])) / 2 for g in gs])
        tw += w; to += o; tn += len(gs)
        say(f"| {s} | {len(gs)} | {w + o} ({w} + {o}) | {(w + o) / len(gs):.3f} | {m:.3f} |")
    mae = float(np.mean([(float(g["blue_mae_q_dps"]) + float(g["red_mae_q_dps"])) / 2 for g in cond]))
    D = (tw + to) / tn
    say(f"| 합계 | {tn} | {tw + to} ({tw} + {to}) | **{D:.4f}** | **{mae:.4f}** |")
    say(f"\nW(승자 변화) {tw / tn:.4f}, O(종료 사유만 변화) {to / tn:.4f}, D = W + O.\n")

    curve = json.load(open(os.path.join(KIT, "out", "main", "curve.json"), encoding="utf-8"))["curve"]["D"]
    pred = curve[0] + curve[1] * mae
    say("## 3. 등록 곡선으로 예측과 잔차\n")
    say(f"등록 곡선(`out/main/curve.json`): D = {curve[0]:.4f} + {curve[1]:.4f} × mae.")
    say(f"예측 D = {curve[0]:.4f} + {curve[1]:.4f} × {mae:.4f} = **{pred:.4f}**. 잔차 = 실제 − 예측 = {D:.4f} − {pred:.4f} = **{D - pred:+.4f}**.\n")

    say("## 4. 비교용 기준 값\n")
    bm = float(np.mean([(float(r["blue_mae_q_dps"]) + float(r["red_mae_q_dps"])) / 2 for r in base.values()]))
    say(f"- BASE의 mae(main 8시드, 1,344판): {bm:.3f} °/s")
    by = P.load("main")
    fit = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
    seeds = P.seeds_of(by, "main", fit)
    V = P.Table(by, fit, "BASE", seeds, list(EXPERIMENTS["E2"]["agents"])).pick(seeds)
    lo = min(fit, key=lambda c: V[c][1]); hi = max(fit, key=lambda c: V[c][1])
    say(f"- E2 적합 20조건의 D 범위: {V[lo][1]:.3f}({lo}, mae {V[lo][0]:.2f}) – {V[hi][1]:.3f}({hi}, mae {V[hi][0]:.2f})")

    say("\n## 5. mae 계산의 예시 (그림 5의 틱별 기록)\n")
    ts = [r for r in csv.DictReader(open(os.path.join(HERE, "fig5_timeseries.csv"), encoding="utf-8"))]
    for c in ("BASE", "R_kappa_100", "R_sigma_dps_6"):
        s = [r for r in ts if r["cond"] == c]
        e = [abs(float(r["q_cmd_dps"]) - float(r["q_dps"])) for r in s]
        say(f"- {c}: 틱 {len(s):,}개(= {len(s) / 120:.1f} s × 120 Hz)의 |명령 − 응답| 평균 = {np.mean(e):.3f} °/s "
            "(`fig5_output.md`의 청 기체 mae와 같다; 기록 반올림 때문에 셋째 자리가 다를 수 있다)")
    s = [r for r in ts if r["cond"] == "R_kappa_100"][2400:2405]
    say("\n20 s 부근 다섯 틱의 예 (R_kappa_100, 20.00–20.03 s):\n")
    say("| 시각 [s] | 명령 [°/s] | 실제 [°/s] | 차이의 절댓값 |")
    say("|---|---|---|---|")
    for r in s:
        say(f"| {float(r['t_s']):.4f} | {float(r['q_cmd_dps']):.3f} | {float(r['q_dps']):.3f} | {abs(float(r['q_cmd_dps']) - float(r['q_dps'])):.3f} |")
    open(os.path.join(HERE, "intro_example_output.md"), "w", encoding="utf-8").write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
