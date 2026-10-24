"""논문에 쓰는 파생 수치 — 결과 보고서에 직접 적히지 않은 값을 원자료에서 다시 계산한다.

  python supplementary/derived_numbers.py   # → supplementary/derived_numbers_output.md, derived_numbers.json

2026-10-24 팀 공부 문서 검토에서 "출처 파일이 없는 숫자"로 지적된 값을 한곳에 모았다.
모두 기존 경기의 재계산이며(경기를 새로 돌리지 않는다) 사후 분석이다. 등록 판정을 바꾸지 않는다.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
import predict as P  # noqa: E402
from experiments import EXPERIMENTS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
OUT: list[str] = []
RES: dict = {}
KEY = ("blue", "red", "scenario", "salt")
AG = list(EXPERIMENTS["E2"]["agents"])
FIT = [c for c in EXPERIMENTS["E2"]["conds"] if c != "BASE"]
TEST = [c for c in EXPERIMENTS["E3"]["conds"] if c != "BASE"]
CURVE = json.load(open(os.path.join(KIT, "out", "main", "curve.json"), encoding="utf-8"))["curve"]["D"]


def say(s=""):
    print(s)
    OUT.append(s)


def read(path):
    return [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["target"] == ""]


def by_cond(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["cond"], r["salt"])].append(r)
    return by


def split(rows, ref="BASE"):
    """조건별 (mae, D, W, O, 경기 수). D = W + O, 짝은 같은 시드·대진·시나리오의 ref 경기."""
    base = {tuple(r[k] for k in KEY): r for r in rows if r["cond"] == ref}
    acc = collections.defaultdict(lambda: [0.0, 0, 0, 0])
    for r in rows:
        if r["cond"] == ref:
            continue
        b = base[tuple(r[k] for k in KEY)]
        a = acc[r["cond"]]
        a[0] += (float(r["blue_mae_q_dps"]) + float(r["red_mae_q_dps"])) / 2
        a[3] += 1
        if r["winner"] != b["winner"]:
            a[1] += 1
        elif r["condition"] != b["condition"]:
            a[2] += 1
    return {c: dict(mae=a[0] / a[3], D=(a[1] + a[2]) / a[3], W=a[1] / a[3], O=a[2] / a[3], n=a[3])
            for c, a in acc.items()}


def main():
    say("# 파생 수치 (사후 재계산, 경기 0판)\n")
    say("보고서에 직접 적히지 않았던 숫자의 출처. 원자료는 고치지 않았다. "
        f"등록 곡선 D = {CURVE[0]:.4f} + {CURVE[1]:.4f}·mae (`out/main/curve.json`).\n")

    # 1. 기술 점수 0.30 — 검증 조건 자체의 평균을 상수로 쓸 때
    main_rows = read(os.path.join(KIT, "out", "main", "games.csv"))
    by = by_cond(main_rows)
    seeds = P.seeds_of(by, "main", FIT)
    V = P.Table(by, FIT + TEST, "BASE", seeds, AG).pick(seeds)
    b, a = np.polyfit([V[c][0] for c in FIT], [V[c][1] for c in FIT], 1)
    e_line = np.array([V[c][1] - (a + b * V[c][0]) for c in TEST])
    y = np.array([V[c][1] for c in TEST])
    rms_line = float(np.sqrt(np.mean(e_line ** 2)))
    rms_oracle = float(np.sqrt(np.mean((y - y.mean()) ** 2)))
    skill_oracle = 1 - rms_line / rms_oracle
    say("## 1. 기술 점수의 세 번째 기준선 (E3 22조건)\n")
    say(f"- 등록 직선 RMS {rms_line:.4f}, 검증 조건 자체 평균({y.mean():.3f})을 상수로 쓴 RMS {rms_oracle:.4f} "
        f"→ 기술 점수 **{skill_oracle:.2f}** (= 1 − √(1 − 표본 밖 R²)).")
    say("- 이 기준선은 결과를 본 뒤에만 알 수 있는 값이다(신탁 기준선). 0.44·0.40은 `out/reanalysis_p0/report_p0.md` A.\n")
    RES["skill_vs_test_mean"] = dict(rms_line=rms_line, rms_const=rms_oracle, skill=skill_oracle,
                                     test_mean=float(y.mean()))

    # 2. E2 적합 범위와 P7 범위 안 오차
    mae_fit = [V[c][0] for c in FIT]
    lo, hi = min(mae_fit), max(mae_fit)
    p7 = split(read(os.path.join(KIT, "out", "p7", "games.csv")))
    delay = ["F25_D2", "F25_D4", "F25_D6", "F25_D8", "F25_D10", "F25_D12"]
    err = {c: p7[c]["D"] - (CURVE[0] + CURVE[1] * p7[c]["mae"]) for c in delay}
    inside = [c for c in delay if p7[c]["mae"] <= hi]
    say("## 2. 실제형(P7) 지연형 조건에서 등록 곡선의 오차와 E2 적합 범위\n")
    say(f"E2 적합 20조건의 mae 범위: {lo:.2f}–{hi:.2f} °/s.\n")
    say("| 조건 | 실제형 mae | D | 등록 곡선 예측 | 오차 (D − 예측) | E2 범위 안 |")
    say("|---|---|---|---|---|---|")
    for c in delay:
        say(f"| {c} | {p7[c]['mae']:.2f} | {p7[c]['D']:.3f} | {CURVE[0] + CURVE[1] * p7[c]['mae']:.3f} | "
            f"{err[c]:+.3f} | {'예' if c in inside else '아니오'} |")
    m_all = float(np.mean(list(err.values())))
    m_in = float(np.mean([err[c] for c in inside]))
    m_d8 = float(np.mean([err[c] for c in delay[:4]]))
    say(f"\n- 6조건 평균 {m_all:+.3f} (등록 판정 T7-2 \"예측 실패\", `p7_output.md`).")
    say(f"- E2 mae 범위 안 {len(inside)}조건({inside[0]}–{inside[-1]}) 평균 **{m_in:+.3f}**.")
    say(f"- D8까지 4조건 평균 {m_d8:+.3f}. 이전 문서의 \"범위 안 −0.06\"은 이 값이다(범위의 정의가 달랐다).\n")
    RES["p7_in_range"] = dict(fit_mae_range=[lo, hi], err=err, mean_all=m_all, inside=inside,
                              mean_inside=m_in, mean_to_D8=m_d8)

    # 3. 흔들림 바닥: SHAM, 원래 구성 약한 열화, 실제형 약한 지연
    cal = read(os.path.join(KIT, "out", "cal", "games.csv"))
    sham = split(cal)["SHAM"]
    sham_seed = {}
    for s in sorted({r["salt"] for r in cal}):
        sham_seed[s] = split([r for r in cal if r["salt"] == s])["SHAM"]["D"]
    e2 = split([r for r in main_rows if r["cond"] in ["BASE"] + FIT])
    weak = sorted([c for c in FIT if e2[c]["mae"] < 1.0], key=lambda c: e2[c]["mae"])
    say("## 3. 흔들림 바닥 (D = W + O)\n")
    say("| 묶음 | 조건 | mae °/s | D | W (승자 변화) | O (종료 사유만) |")
    say("|---|---|---|---|---|---|")
    say(f"| 가짜 변형 (E1, cal 8시드) | SHAM | {sham['mae']:.2f} | {sham['D']:.3f} | {sham['W']:.3f} | {sham['O']:.3f} |")
    for c in weak:
        v = e2[c]
        say(f"| 원래 구성 약한 열화 (E2, mae < 1) | {c} | {v['mae']:.2f} | {v['D']:.3f} | {v['W']:.3f} | {v['O']:.3f} |")
    for c in ("F25_D2", "F25_D4"):
        v = p7[c]
        say(f"| 실제형, 추종 오차가 기준과 같음 (P7) | {c} | {v['mae']:.2f} | {v['D']:.3f} | {v['W']:.3f} | {v['O']:.3f} |")
    say(f"\n- SHAM 시드별 D: {min(sham_seed.values()):.3f}–{max(sham_seed.values()):.3f} "
        f"(`out/cal/report_predict_E1.md` 3행, `tolerance.json`의 바탕).")
    wd = [e2[c]["D"] for c in weak]
    say(f"- 원래 구성 약한 열화 {len(weak)}조건의 D: {min(wd):.3f}–{max(wd):.3f}.")
    base_rows = [r for r in main_rows if r["cond"] == "BASE"]
    base_mae = float(np.mean([(float(r["blue_mae_q_dps"]) + float(r["red_mae_q_dps"])) / 2 for r in base_rows]))
    near = [c for c in weak if e2[c]["mae"] <= base_mae + 0.05]
    nd = [e2[c]["D"] for c in near]
    say(f"- 그중 추종 오차가 기준(BASE mae {base_mae:.2f})과 비슷한(+0.05 °/s 이내) {len(near)}조건 "
        f"({', '.join(near)})의 D: **{min(nd):.3f}–{max(nd):.3f}**. "
        f"F12_D0.5(mae {e2['F12_D0.5']['mae']:.2f})는 오차가 기준보다 커서 빠진다.")
    say(f"- 실제형 2·4틱의 D: {p7['F25_D2']['D']:.3f}–{p7['F25_D4']['D']:.3f}, "
        f"승자 변화 W: {p7['F25_D2']['W']:.3f}–{p7['F25_D4']['W']:.3f}.\n")
    RES["floor"] = dict(sham=sham, sham_seed=sham_seed, weak_e2={c: e2[c] for c in weak},
                        base_mae=base_mae, near_base=near,
                        p7_D2=p7["F25_D2"], p7_D4=p7["F25_D4"])

    # 4. 같은 mae에서 두 구성 비교 (그림 6)
    orig = split([r for r in main_rows if r["cond"] in ("BASE", "F25_D2")])["F25_D2"]
    say("## 4. 같은 mae에서 두 구성 (그림 6의 근거)\n")
    say(f"- 원래 구성 F25_D2: mae {orig['mae']:.2f}, D {orig['D']:.3f} (`out/main`).")
    say(f"- 실제형 F25_D8: mae {p7['F25_D8']['mae']:.2f}, D {p7['F25_D8']['D']:.3f} (`out/p7`).")
    say("- 두 값은 `p7_output.md` §1 표에도 있다(원래 F25_D2 행의 오른쪽, 실제형 F25_D8 행).\n")
    RES["matched_mae"] = dict(orig_F25_D2=orig, real_F25_D8=p7["F25_D8"])

    # 5. P8 종료 방식
    p8 = [r for r in csv.DictReader(open(os.path.join(KIT, "out", "p8", "games.csv"), encoding="utf-8"))]
    cnt = {c: collections.Counter(r["condition"] for r in p8 if r["cond"] == c)
           for c in ("BASE", "CMD48", "R_kq_0.25", "F25_D6", "F25_D8")}
    say("## 5. P8 종료 방식 (`out/p8`, x8 8시드, 조건마다 1,344경기)\n")
    ends = ["health_zero", "hard_deck", "timeout", "no_contact", "stall", "wall_clock"]
    say("| 조건 | " + " | ".join(ends) + " |")
    say("|---" * (len(ends) + 1) + "|")
    for c, k in cnt.items():
        say(f"| {c} | " + " | ".join(str(k.get(e, 0)) for e in ends) + " |")
    say("\n- 명령 지연 0.4 s(CMD48)의 지면 충돌 증가: "
        f"{cnt['BASE']['hard_deck']} → {cnt['CMD48']['hard_deck']}경기.\n")
    RES["p8_end"] = {c: dict(k) for c, k in cnt.items()}

    # 6. 경기 수
    def n(path):
        return sum(1 for _ in csv.DictReader(open(os.path.join(KIT, path), encoding="utf-8")))
    parts = {"out/rep (P4)": n("out/rep/games.csv"), "out/p5 (P5)": n("out/p5/games.csv"),
             "out/p6 (P6)": n("out/p6/games.csv"), "out/p7 (P7)": n("out/p7/games.csv"),
             "supplementary/p7_probe_games.csv (P7 탐침)": n("supplementary/p7_probe_games.csv")}
    say("## 6. P4–P7 경기 수\n")
    for k, v in parts.items():
        say(f"- {k}: {v:,}")
    say(f"- 합계 **{sum(parts.values()):,}** (P7 탐침 포함, 확증 경기만은 {sum(parts.values()) - parts['supplementary/p7_probe_games.csv (P7 탐침)']:,}).\n")
    RES["games_p4_p7"] = parts

    # 7. 승자 변화(W)만 셀 때: 기술 점수와 유형 대비
    say("## 7. 승자 변화(W)만 셀 때 (D 대신 W로 같은 계산)\n")
    e2w = split([r for r in main_rows if r["cond"] in ["BASE"] + FIT + TEST])
    bw, aw = np.polyfit([e2w[c]["mae"] for c in FIT], [e2w[c]["W"] for c in FIT], 1)
    ew = np.array([e2w[c]["W"] - (aw + bw * e2w[c]["mae"]) for c in TEST])
    cw = np.array([e2w[c]["W"] - aw for c in TEST])
    skill_w = 1 - np.sqrt(np.mean(ew ** 2)) / np.sqrt(np.mean(cw ** 2))
    say(f"- E2 W 직선: W = {aw:.3f} + {bw:.4f}·mae. E3 22조건 RMS {np.sqrt(np.mean(ew ** 2)):.3f} 대 상수(W 절편) "
        f"{np.sqrt(np.mean(cw ** 2)):.3f} → 기술 점수 **{skill_w:.2f}**.")

    def wres(stats, cs, a_, b_):
        return float(np.mean([stats[c]["W"] - (a_ + b_ * stats[c]["mae"]) for c in cs]))
    rep = split(read(os.path.join(KIT, "out", "rep", "games.csv")))
    t_d = wres(rep, ["R_kappa_50", "R_kappa_100"], aw, bw) - wres(rep, ["F25_D0.5", "F5_D2", "R_sigma_dps_6"], aw, bw)
    say(f"- P4 T-D (새 시드, E2 W 직선 기준): 둔한(κ 50·100) − 진동형(F25_D0.5, F5_D2, σ 6) 잔차 **{t_d:+.3f}**.")
    b7, a7 = np.polyfit([p7[c]["mae"] for c in delay], [p7[c]["W"] for c in delay], 1)
    t73 = wres(p7, ["R_kappa_25", "R_kappa_50"], a7, b7)
    say(f"- P7 T7-3 (실제형, 지연형 6조건 W 직선 W = {a7:.3f} + {b7:.4f}·mae 기준): 둔한(κ 25·50) 잔차 **{t73:+.3f}**.")
    p8s = split(p8)
    t8 = wres(p8s, ["CMD48", "R_kq_0.25"], a7, b7) - wres(p8s, ["F25_D6", "F25_D8"], a7, b7)
    say(f"- P8 T8 (실제형·새 시드, 같은 W 직선 기준): 둔한(CMD48, k_q 0.25) − 진동형(F25_D6, F25_D8) 잔차 **{t8:+.3f}**.")
    say("- 모두 사후, 구간 없음. 원고 Ⅴ-B의 W 기술 점수와 Ⅴ-C의 W 대비의 출처.\n")
    RES["winner_only"] = dict(e2_line=[float(aw), float(bw)], skill=float(skill_w), p4_TD=t_d,
                              p7_line=[float(a7), float(b7)], p7_T73=t73, p8_T8=t8)

    open(os.path.join(HERE, "derived_numbers_output.md"), "w", encoding="utf-8").write("\n".join(OUT) + "\n")
    json.dump(RES, open(os.path.join(HERE, "derived_numbers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main()
