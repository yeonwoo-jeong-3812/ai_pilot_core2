"""하드덱 진단 보고서 → bt/out/diag_hard_deck.md. 읽기만 한다.

  python bt/diag_trace.py && python bt/diag_report.py

입력: bt/out/bt-pilot/games_original.csv (원본 상대 예비 실험), bt/out/diag/ (diag_trace.py 결과), bt/out/bt-diag/games_diag1.csv (반사실),
kit/out/*/games.csv (INDI 논문 실험, 있으면).
"""
from __future__ import annotations

import collections as C
import csv
import glob
import json
import math
import os
import statistics as st
import sys

BT = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(BT)
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
from run_bt import OPPONENTS, SCENARIOS, win_mode  # noqa: E402

OUT = os.path.join(BT, "out")
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")


def rows(p):
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def ci(xs):
    m = st.mean(xs)
    h = 1.96 * st.stdev(xs) / len(xs) ** 0.5
    return m, m - h, m + h


def main():
    L = ["# 하드덱 진단", "",
         "질문: 예비 실험 청 승리의 69% 가 상대 하드덱인 이유. **진단만 한다** (설계·지표 결정 없음). "
         "엔진, `kit/agents/` 원본 상대, 기존 결과 CSV 는 고치지 않았다.", "",
         "**가설:** 상대 4종의 `low_altitude floor_ft` 가 1,200 ft (하드덱 + 200 ft) 라 이 엔진 물리로는 회복 개시가 늦어, "
         "청이 낮은 고도로 끌어들이면 상대가 하드덱을 뚫는다.", ""]

    # 1. 기존 데이터
    pilot = rows(os.path.join(OUT, "bt-pilot", "games_original.csv"))
    hd = [r for r in pilot if r["end_reason"] == "hard_deck"]
    L += ["## 1. 기존 데이터 (예비 실험 2,400경기)", "",
          f"- 하드덱 종료 {len(hd)}경기: **상대(홍)가 닿음 {sum(r['winner'] == 'blue' for r in hd)}**, "
          f"청이 닿음 {sum(r['winner'] == 'red' for r in hd)}, 동시 {sum(r['winner'] == 'draw' for r in hd)}.", "",
          "| 구분 | 경기 | 상대 하드덱 | 비율 | 청 하드덱 |", "|---|---|---|---|---|"]
    for key, keys in (("opponent", list(OPPONENTS)), ("scenario", list(SCENARIOS))):
        for k in keys:
            g = [r for r in pilot if r[key] == k]
            n = sum(r["end_reason"] == "hard_deck" and r["winner"] == "blue" for r in g)
            b = sum(r["end_reason"] == "hard_deck" and r["winner"] == "red" for r in g)
            L.append(f"| {k} | {len(g)} | {n} | {n / len(g):.3f} | {b} |")

    s = json.load(open(os.path.join(OUT, "diag", "trace_summary.json"), encoding="utf-8"))
    cls = C.Counter(x["cls"] for x in s)
    prev = C.Counter()
    for x in s:
        nodes = [r["red_node"] for r in rows(os.path.join(OUT, "diag", "traces", f"{x['i']:02d}.csv"))]
        prev[nodes[max(j for j, n in enumerate(nodes) if n != "climb")]] += 1
    L += ["", f"### 하드덱 경기 추적 (무작위 {len(s)}경기, seed 20261102, bt-pilot 시드 그대로 재실행)", "",
          f"- 재현: **{sum(x['reproduced'] for x in s)}/{len(s)}** 경기가 CSV 와 승자·종료 사유·종료 시각까지 같다.",
          f"- 분류: (a) climb 작동 후 뚫음 **{cls['a']}**, (b) climb 미작동 {cls['b']}, (c) 기타 {cls['c']}. "
          "상대 4종 모두 최우선 노드가 `low_altitude(floor_ft 1200) → climb` 이라 climb 실행 = low_altitude 작동.",
          f"- climb 직전 홍 노드: " + ", ".join(f"{k} {v}" for k, v in prev.most_common()) + ". 홍은 청을 쫓거나 "
          "(pursue/extend) 방어 기동(break) 중에 강하하다 1,200 ft 를 지났다.", "",
          "| # | 상대 | 기하 | 작동 고도 ft | 강하각 ° | KCAS | 작동→하드덱 s | 회복 중 최대 G | 청 고도 ft | 청 노드 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for x in s:
        if x["cls"] != "a":
            continue
        L.append(f"| {x['i']} | {x['opponent'][:2]} | {x['scenario']} | {x['alt_act']:.0f} | {x['gamma_act']:.1f} "
                 f"| {x['kcas_act']:.0f} | {x['t_end'] - x['t_act']:.2f} | {x['nz_max_after']:.1f} "
                 f"| {x['blue_alt_act']:.0f} | {x['blue_node_act']} |")
    a = [x for x in s if x["cls"] == "a"]
    L += ["", "작동 고도는 20 Hz 표본이라 1,200 ft 바로 아래로 찍힌다. 15초 시계열은 `bt/out/diag/traces/` (git 제외).", ""]

    # 2. 물리
    n_short9 = sum(x["loss_gmax"] > x["margin"] for x in a)
    n_shortn = sum(x["loss_nzmax"] > x["margin"] for x in a)
    L += ["## 2. 물리 확인 (원호 근사)", "",
          "R = V² / (g(n − 1)), 필요 고도 = R(1 − cos γ). 여유 = 작동 고도 − 1,000 ft. "
          "n 은 ① 리미터 한계 (작동 시점 `g_max`, 20경기 모두 9.0 G) ② 실제로 낸 최대 G 두 가지로 계산. 당김 시작 지연은 무시 (낙관적).", "",
          "| # | 강하각 ° | V ft/s | 여유 ft | 필요 ① 9 G | 필요 ② 실제 G | ① 부족? | ② 부족? |", "|---|---|---|---|---|---|---|---|"]
    for x in a:
        L.append(f"| {x['i']} | {x['gamma_act']:.1f} | {x['v_act']:.0f} | {x['margin']:.0f} | {x['loss_gmax']:.0f} "
                 f"| {x['loss_nzmax']:.0f} | {'예' if x['loss_gmax'] > x['margin'] else '아니오'} "
                 f"| {'예' if x['loss_nzmax'] > x['margin'] else '아니오'} |")
    L += ["", f"- 9 G 로 바로 당겨도 **{n_short9}/{len(a)}** 경기는 남은 여유 안에서 회복할 수 없다 "
          f"(여유 {min(x['margin'] for x in a):.0f}–{max(x['margin'] for x in a):.0f} ft, "
          f"필요 {min(x['loss_gmax'] for x in a):.0f}–{max(x['loss_gmax'] for x in a):.0f} ft).",
          f"- 실제로 낸 G (최대 {min(x['nz_max_after'] for x in a):.1f}–{max(x['nz_max_after'] for x in a):.1f} G) 로는 "
          f"**{n_shortn}/{len(a)}** 경기가 부족하다. climb 은 `g_burst` 미지정 → 기본 0 (지속 봉투 천장) 이라 "
          "9 G 를 쓰지 않는다. 9 G 로 회복 가능했던 경기도 여기서 부족해진다.", ""]

    # 3. 반사실
    diag = rows(os.path.join(OUT, "bt-diag", "games_diag1.csv"))
    thetas = {mt.theta_id(t): t for t in (mt.normalize(r) for r in rows(os.path.join(BT, "thetas", "diag.csv")))}
    L += ["## 3. 반사실 실험 (bt-diag 시드, 상대 floor_ft 1200 → 4000 복사본, 나머지 바이트 동일)", "",
          "| 청 floor_ft | 상대 | 경기 | 승률 | 상대 하드덱 | 청 하드덱 | 격추승 비율 | wez 차 평균 [s] (95% CI) | 승리 방식 " +
          "(" + "/".join(MODES) + ") |", "|---|---|---|---|---|---|---|---|---|"]
    win = {}
    for tid, th in sorted(thetas.items(), key=lambda kv: kv[1]["floor_ft"]):
        for label, f4 in (("원본 (1200)", False), ("수정 (4000)", True)):
            g = [r for r in diag if r["theta_id"] == tid and r["opponent"].endswith("_f4000") == f4]
            if not g:
                continue
            w = sum(r["winner"] == "blue" for r in g) / len(g)
            win[(th["floor_ft"], f4)] = w
            m = C.Counter(win_mode(r["winner"], r["end_reason"]) for r in g)
            wz = ci([float(r["wez_blue"]) - float(r["wez_red"]) for r in g])
            L.append(f"| {th['floor_ft']:.0f} | {label} | {len(g)} | {w:.3f} "
                     f"| {sum(r['end_reason'] == 'hard_deck' and r['winner'] == 'blue' for r in g) / len(g):.3f} "
                     f"| {sum(r['end_reason'] == 'hard_deck' and r['winner'] == 'red' for r in g) / len(g):.3f} "
                     f"| {m['shootdown'] / len(g):.3f} | {wz[0]:+.2f} ({wz[1]:+.2f}, {wz[2]:+.2f}) "
                     f"| {'/'.join(str(m[k]) for k in MODES)} |")
    if len(win) == 6:
        L += ["", "청 floor_ft 에 따른 승률 (3000 → 4500 → 7000):",
              f"- 원본 상대: {win[(3000.0, False)]:.3f} → {win[(4500.0, False)]:.3f} → {win[(7000.0, False)]:.3f}",
              f"- 수정 상대: {win[(3000.0, True)]:.3f} → {win[(4500.0, True)]:.3f} → {win[(7000.0, True)]:.3f}", ""]
    L += ["상대별 (청 θ 3개 합산):", "", "| 상대 | 원본 승률 | 원본 상대 하드덱 | 수정 승률 | 수정 상대 하드덱 |", "|---|---|---|---|---|"]
    for o in OPPONENTS:
        cells = []
        for f4 in (False, True):
            g = [r for r in diag if r["opponent"] == (o + "_f4000" if f4 else o)]
            cells += [f"{sum(r['winner'] == 'blue' for r in g) / len(g):.3f}",
                      f"{sum(r['end_reason'] == 'hard_deck' and r['winner'] == 'blue' for r in g) / len(g):.3f}"]
        L.append(f"| {o} | " + " | ".join(cells) + " |")

    f4 = json.load(open(os.path.join(OUT, "diag", "trace_f4000.json"), encoding="utf-8"))
    L += ["", f"### 수정 상대도 하드덱을 뚫는 경기 추적 ({len(f4)}경기 / 수정 상대 하드덱 {f4[0]['n_hd_f4000']}경기, "
          f"재현 {sum(x['reproduced'] for x in f4)}/{len(f4)})", "",
          "| 작동 고도 ft | 강하각 ° | climb 첫 표본 뱅크 ° | climb 중 평균 |뱅크| ° | climb 중 최저 강하각 ° | climb 중 평균 G | 작동→하드덱 s |",
          "|---|---|---|---|---|---|---|"]
    for x in f4:
        L.append(f"| {x['alt_act']:.0f} | {x['gamma_act']:.0f} | {x['bank_act']:.0f} | {x['bank_mean_climb']:.0f} "
                 f"| {x['gamma_min_climb']:.0f} | {x['nz_mean_climb']:.1f} | {x['t_end'] - x['t_act']:.1f} |")
    L += ["", "4,000 ft 에서 climb 이 작동해도 그 순간 홍은 이미 −45° ~ −72° 로 강하 중이고 크게 기울어 (뱅크 21°–146°) 있다. "
          "climb 은 날개 수평 최대 G 당김이 아니라 \"청 위치 + 4,000 ft\" 를 향한 pure 추적이고 g_burst 0 (지속 봉투) 이라, "
          "평균 5.5–5.9 G 로 기운 채 당긴다. 강하각이 초당 약 10° 씩만 줄어 5–6 초 뒤 하드덱에 닿는다. "
          "원호 근사로는 6 G 날개 수평이면 약 1,700 ft 로 회복되는 조건 (여유 약 2,950 ft) 이다.", ""]

    # 4. INDI
    L += ["", "## 4. INDI 논문 실험과 비교 (`kit/out/*/games.csv`, condition 열)", "",
          "| 파일 | 경기 | hard_deck | 비율 |", "|---|---|---|---|"]
    found = sorted(glob.glob(os.path.join(KIT, "out", "*", "games.csv")))
    for f in found:
        rr = rows(f)
        if not rr or "condition" not in rr[0]:
            continue
        n = sum(r["condition"] == "hard_deck" for r in rr)
        L.append(f"| {os.path.relpath(f, KIT)} | {len(rr)} | {n} | {n / len(rr):.3f} |")
    if not found:
        L.append("| (없음) | | | |")
    L += ["", "INDI 실험은 상대 구성(에이전트)이 다르지만, 같은 엔진에서 하드덱 종료가 17–28% (smoke 60%) 로 흔하다.", ""]
    # 판정
    L += ["## 판정", "",
          "**가설은 부분적으로 맞다.** 원인은 회복 개시 고도 하나가 아니라, 상대의 회복 노드 전체가 이 엔진 물리에 맞지 않는 것이다.", "",
          f"- **맞는 부분 — 1,200 ft 는 물리적으로 너무 낮다.** 추적한 하드덱 {len(a)}경기 모두 (a): low_altitude 는 작동했고, "
          "작동 후 0.25–0.9 초 만에 하드덱에 닿았다. 여유는 130–190 ft 인데, 9 G 를 즉시 써도 "
          f"{n_short9}/{len(a)} 경기는 회복이 불가능한 강하각·속도였다.",
          "- **맞는 부분 — floor 를 올리면 상대 하드덱이 준다.** 반사실에서 상대 하드덱 비율이 줄고 격추승이 늘었다 (§3 표).",
          "- **틀린 부분 — floor 4,000 ft 로도 없어지지 않는다.** 수정 상대도 하드덱이 남는다. 4,000 ft 에서 climb 이 작동해도 "
          "가파른 강하 + 큰 뱅크 + 지속 봉투 G (g_burst 0) + 청을 기준으로 한 조준점 때문에 회복하지 못한다 (§3 추적).",
          "- **청 floor_ft 효과는 유지된다.** 수정 상대에서도 청 floor_ft 3000 → 7000 에서 승률이 내려간다 (§3). "
          "다만 원본 상대에서는 그 차이 대부분이 상대 하드덱이고, 수정 상대에서는 격추승 비중이 커진다.", "",
          "## 가설 외 원인", "",
          "1. **climb 동작 자체.** 상대의 회복 노드는 `pursuit: pure, aim_above_ft: 4000` (청 위치 + 4,000 ft 를 향한 추적) 이고 "
          "`g_burst` 미지정 (기본 0, 지속 봉투) 이다. 날개 수평 최대 G 회복이 아니어서 floor 를 올려도 가파른 강하에서는 늦다.",
          "2. **청이 상대를 끌어내린다.** climb 직전 홍 노드는 pursue/extend/break 이다. 청 recover_altitude (floor_ft) 와 "
          "yoyo_dive_cut 이 낮은 고도에서 기동하고, 상대가 쫓아 내려오다 가파른 강하에 들어간다. "
          "청 floor_ft 가 낮을수록 상대 하드덱이 많다 (§3).",
          "3. **상대마다 다르다.** A2_GunTracker 가 가장 많이 (예비 실험 47%), C1_TwoCircleRate 는 거의 안 (2.5%) 뚫는다.",
          "4. **엔진 공통 현상.** INDI 논문 실험 (다른 상대 구성) 도 하드덱 종료가 17–28% 다 (§4).", ""]
    with open(os.path.join(OUT, "diag_hard_deck.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
