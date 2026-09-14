"""P2 보고서 — 능력표·궤적 수집·기동 분류 결과를 사전등록 규칙(A6, A7)대로 정리한다.

사용: python research/l3_indi/p2_report.py <capability_csv> <traces_dir> <taxonomy_dir>
출력: research/l3_indi/reports/P2_<commit10>.md
"""
from __future__ import annotations

import collections
import contextlib
import csv
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from l3_indi.harness import build, run, Condition, DT          # noqa: E402
from l3_indi.maneuvers import M1NzCapture, M2RollReversal, M3RollingPull, HOLD_S   # noqa: E402
from l3_indi.taxonomy import band95, LABELS, SYNTH             # noqa: E402
from l3_indi.capability import ALTS_KFT, KCAS                  # noqa: E402


def f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}f}"


def nearest(v, grid):
    return min(grid, key=lambda g: abs(g - v))


def main():
    cap_csv, traces_dir, tax_dir = sys.argv[1:4]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from l3_indi.runner import git_state
    commit = git_state()["commit"][:10]
    cap = list(csv.DictReader(open(cap_csv, encoding="utf-8")))
    runs_ = list(csv.DictReader(open(os.path.join(traces_dir, "runs.csv"), encoding="utf-8")))
    S = json.load(open(os.path.join(tax_dir, "summary.json"), encoding="utf-8"))
    L = []
    w = L.append

    w(f"# P2 결과 — 능력표 · 실전 궤적 · 기동 분포 (보고서 커밋 {commit})\n")
    w(f"- 능력표: `{os.path.relpath(cap_csv, HERE)}`  \n- 궤적: `{traces_dir}`  \n- 분류: `{tax_dir}`\n")

    # ---------------- 능력표
    w("\n## 1. 조건별 능력표 (개정 A6)\n")
    for fbw in ("0", "1"):
        rows = {(int(r["alt_kft"]), int(r["kcas"])): r for r in cap if r["fbw_override"] == fbw}
        w(f"\n### FLCS {'on (기준)' if fbw == '0' else 'off (대조)'} — C_nz [G] / C_p [deg/s]\n")
        w("| 고도 kft \\ KCAS | " + " | ".join(str(k) for k in KCAS) + " |")
        w("|---|" + "---|" * len(KCAS))
        for a in ALTS_KFT:
            cells = []
            for k in KCAS:
                r = rows[(a, k)]
                mark = "" if r["trim_valid"] in ("1", "1.0") else " ✗트림"
                cells.append(f"{float(r['C_nz']):.2f} / {float(r['C_p']):.0f}{mark}")
            w(f"| {a} | " + " | ".join(cells) + " |")
        asym = [float(r["C_p_pos"]) - float(r["C_p_neg"]) for r in rows.values()]
        src_nz = collections.Counter("개루프" if float(r["nz_open"]) >= float(r["nz_closed"]) else "폐루프"
                                     for r in rows.values())
        capped = sum(1 for r in rows.values() if float(r["C_nz"]) >= 9.0 - 1e-9)
        invalid = sum(1 for r in rows.values() if r["trim_valid"] not in ("1", "1.0"))
        w(f"\n- 롤율 방향 비대칭 C_p+ − C_p−: 최소 {min(asym):.1f}, 중앙 {np.median(asym):.1f}, 최대 {max(asym):.1f} deg/s")
        w(f"- C_nz 를 정한 쪽: {dict(src_nz)}; 구조 한계 9.0 G 로 잘린 조건 {capped}/{len(rows)}; 트림 무효 {invalid}/{len(rows)}")

    # ---------------- 수집
    w("\n## 2. 실전 궤적 수집 (개정 A5, A8)\n")
    cond = collections.Counter(r["condition"] for r in runs_)
    dur = np.array([float(r["time_s"]) for r in runs_])
    w(f"- {len(runs_)}경기, 기록 {sum(int(r['n_ticks']) for r in runs_) * DT / 3600 * 2:.1f} 기체-시간(양측 합)")
    w(f"- 종료 사유: {dict(cond)}")
    w(f"- 경기 길이 [s]: p10 {np.percentile(dur, 10):.0f}, 중앙 {np.median(dur):.0f}, p90 {np.percentile(dur, 90):.0f}")
    by_part = collections.defaultdict(list)
    for r in runs_:
        by_part[os.path.basename(r["participant"])].append(float(r["time_s"]))
    w("- 참가자별 경기 수 / 평균 길이: " + ", ".join(f"{k} {len(v)}/{np.mean(v):.0f}s" for k, v in sorted(by_part.items())))

    # ---------------- 분포
    w("\n## 3. 실전 기동 분포 (개정 A7)\n")
    w(f"분석 시간: 양측 합 {S['minutes_all_sides']:.0f} 기체-분.\n")
    w("### 3.1 시간 비율 — 괄호 안은 기동 시간(low_g 제외) 대비\n")
    keys = ["all", "participant", "red"] + sorted(k for k in S["time"] if k.startswith("scen:"))
    w("| 범주 | " + " | ".join(keys) + " |")
    w("|---|" + "---|" * len(keys))
    for lab in LABELS:
        cells = []
        for k in keys:
            fr, fm = S["time"][k][0][lab]
            cells.append(f"{100*fr:.1f}%" + ("" if lab == "low_g" else f" ({100*fm:.1f}%)"))
        w(f"| {lab} | " + " | ".join(cells) + " |")
    w("\n### 3.2 민감도 — 기동 시간 대비 비율\n")
    sk = ["기준(30 dps, 2.5 G)"] + list(S["sensitivity"].keys())
    w("| 범주 | " + " | ".join(sk) + " |")
    w("|---|" + "---|" * len(sk))
    for lab in LABELS[:-1]:
        cells = [f"{100*S['time']['all'][0][lab][1]:.1f}%"] + \
                [f"{100*S['sensitivity'][k][0][lab][1]:.1f}%" for k in S["sensitivity"]]
        w(f"| {lab} | " + " | ".join(cells) + " |")
    w("\n### 3.3 사건 특성 — p10 / p50 / p90\n")
    for t, d in S["events"].items():
        w(f"\n**{t}** — {d['count']}건, 기체-분당 {d['per_min']:.2f}건\n")
        w("| 특성 | p10 | p50 | p90 |\n|---|---|---|---|")
        for k, v in d.items():
            if k in ("count", "per_min"):
                continue
            w(f"| {k} | {f(v[0])} | {f(v[1])} | {f(v[2])} |")
    env = S["envelope"]
    w(f"\n### 3.4 기동 구간 비행 조건 (p5 / p10 / p50 / p90 / p95)\n")
    w(f"- 고도 [ft]: " + " / ".join(f"{x:.0f}" for x in env["alt_ft"]))
    w(f"- KCAS: " + " / ".join(f"{x:.0f}" for x in env["kcas"]))
    bw = S["bandwidth"]
    w(f"- 명령 95% 파워 대역폭 [Hz] (기체-경기별 p10/p50/p90): p_sp {f(bw['psp'][0])}/{f(bw['psp'][1])}/{f(bw['psp'][2])}, "
      f"q_sp {f(bw['qsp'][0])}/{f(bw['qsp'][1])}/{f(bw['qsp'][2])}")

    # ---------------- RQ1 조건 선택 규칙
    w("\n## 4. RQ1 조건 선택 (개정 A6 규칙 적용)\n")
    alts = sorted({nearest(env["alt_ft"][i] / 1000.0, ALTS_KFT) for i in (1, 2, 3)})
    ks = sorted({nearest(env["kcas"][i], KCAS) for i in (1, 2, 3)})
    w(f"- 고도 p10/p50/p90 → 격자: {[nearest(env['alt_ft'][i]/1000.0, ALTS_KFT) for i in (1,2,3)]} kft")
    w(f"- KCAS p10/p50/p90 → 격자: {[nearest(env['kcas'][i], KCAS) for i in (1,2,3)]}")
    w(f"- 결과 조건 (중복 제거 후): 고도 {alts} × KCAS {ks}")
    rows0 = {(int(r["alt_kft"]), int(r["kcas"])): r for r in cap if r["fbw_override"] == "0"}
    bad = [(a, k) for a in alts for k in ks if rows0[(a, k)]["trim_valid"] not in ("1", "1.0")]
    w(f"- 트림 무효 조건: {bad if bad else '없음'}")

    # ---------------- 합성 기동 명령 대역폭
    w("\n## 5. 합성 기동 대표성 (개정 A7 R1, R2)\n")
    r1 = S["R1"]
    w(f"### R1 포괄률\n\n- 기동 시간 중 합성 3종 범주(roll_reversal + rolling_pull + g_capture): **{100*r1['covered_frac']:.1f}%**")
    w(f"- 포괄 안 됨(roll_other + unload): **{100*r1['uncovered_frac']:.1f}%** → 판정 기준 20% "
      f"{'**초과 — 포괄 못 하는 유형 있음**' if r1['flag'] else '이내'}\n")
    w("### R2 매개변수 (실전 p10~p90 밖이면 비대표)\n")
    w("| 합성 매개변수 | 합성 수준 | 실전 p10 | p50 | p90 | n | 범위 밖 수준 | 실전 사건 중 수준 사이 비율 |")
    w("|---|---|---|---|---|---|---|---|")
    for k, v in S["R2"].items():
        w(f"| {k} | {v['levels']} | {f(v['real_p10'])} | {f(v['real_p50'])} | {f(v['real_p90'])} | {v['n']} | "
          f"{('**' + str(v['outside']) + '**') if v['outside'] else '없음'} | {f(100*v['frac_real_between_levels'],1)}% |")
    # 합성 기동 명령 대역폭 (조건 중앙값에서)
    c = Condition(alt_ft=nearest(env["alt_ft"][2] / 1000.0, ALTS_KFT) * 1000.0, kcas=float(nearest(env["kcas"][2], KCAS)))
    cnz = float(rows0[(int(c.alt_ft / 1000), int(c.kcas))]["C_nz"])
    w(f"\n### 합성 기동 명령 대역폭 (조건 {c.alt_ft:.0f} ft / {c.kcas:.0f} KCAS, C_nz {cnz:.2f})\n")
    w("| 기동 | p_sp 95% [Hz] | q_sp 95% [Hz] |\n|---|---|---|")
    for man in (M1NzCapture(nz_target=0.6 * cnz), M2RollReversal(), M3RollingPull(nz_target=0.6 * cnz)):
        with contextlib.redirect_stdout(io.StringIO()):
            ts = run(build(c), man)
        m = ts["t"] >= HOLD_S
        w(f"| {man.name} | {f(band95(np.rad2deg(ts['sp_p'][m])))} | {f(band95(np.rad2deg(ts['sp_q'][m])))} |")

    out = os.path.join(HERE, "reports", f"P2_{commit}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("->", out)


if __name__ == "__main__":
    raise SystemExit(main())
