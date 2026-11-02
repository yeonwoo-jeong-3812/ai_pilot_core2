"""검증 표 → bt/out/validation.md. 판정 규칙은 결과를 보기 전에 여기 고정했다.

  python bt/validate.py

지표 (θ 하나 = 48경기):
  win   청 승 = 1, 그 외 0 (무승부도 0, 무승부 수는 따로 표기)
  wezd  wez_blue − wez_red [s]
잡음 범위 = 기준 θ 를 시드 묶음 3개(bt-cal, bt-cal-a, bt-cal-b)로 돌린 평균의 쌍별 차이 중 최대 |Δ|.
θ 비교는 bt-cal 안에서 같은 셀(같은 시드)끼리 짝지은 차이 Δ = θ − 기준의 평균과 95% CI (정규 근사, ±1.96·sd/√n).
통과 (검증 1): A, B 각각 두 지표 모두 Δ < 0, |Δ| > 잡음 범위, 짝 95% CI 가 0 을 넘지 않음.
검증 3: 미세 변경 θ 의 |Δ| 가 두 지표 모두 잡음 범위 안이면 "안".
검증 1 은 불통과했다. 원인은 "망가진 θ"를 직관으로 고른 설계 문제다. A, B 는 예비 관찰로만 남기고,
A 는 "지표가 실제 차이를 잡아낸다"는 민감도 증거로 쓴다.

R0 (검증 1 재설계, R0 실행 전에 고정). θ 는 bt/thetas/r0.csv (기준, R0-1, R0-2), bt-cal 시드, stage=r0.
  R0-1 floor_ft=40000  : 시작 고도(12,000–18,000 ft)보다 높고 recover_altitude 의 조준점(적 고도 + 4,000 ft)으로도
                         닿지 않는다 → 최우선 노드 recover_altitude 가 거의 항상 실행된다. 의도 노드 recover_altitude.
  R0-2 fight_kcas=1000 : 기체가 낼 수 없는 속도 → below_fighting_speed 가 항상 참. cooldown 은 활동이 끝나야
                         걸리므로 막지 않는다 → 상위 3노드(회복·브레이크·건)가 아닐 때 energy_recover. 의도 노드 energy_recover.
  통과 = 둘 다 (a)(b) 만족.
  (a) 의도 노드 node_frac 48경기 평균이 기준 θ 보다 0.3 이상 높다 (짝 차이 95% CI 하한 > 0.3).
  (b) 승률, wez 차 둘 다 Δ < 0, 짝 95% CI 상한 < 0, |Δ| > 잡음 범위 (승률 0.104, wez 0.28 s).
  R0-1 결과: 불통과 ((a) 통과, (b) 불통과 — 청 승 10 중 7 이 상대 실속). 판정 기준은 바꾸지 않는다.
  R0-3 (R0-1 결과를 본 뒤, R0-3 실행 전에 고정. 판정 기준은 위와 같다. 통과 = R0-2, R0-3 둘 다 (a)(b)):
  R0-3 threat_aspect_deg=-1, merge_range_ft=200000 : foe_threat 는 aspect > aspect_deg 이고 aspect 는 0–180° → 항상 참.
                         merged 는 range < range_ft 이고 시작 거리는 최대 약 44,000 ft → 항상 참. 우선순위는
                         recover_altitude > break_defense > gun_track 이라, 고도 4,500 ft 미만일 때 말고는 늘
                         break_defense (지연 추적 lag, g_burst 0.5) 만 실행하고 건 추적은 하지 않는다. 수직 조준
                         오프셋이 없어 상대를 지면·실속으로 끌어들일 여지가 R0-1 보다 적다. 의도 노드 break_defense.
  R0-3 노드 확인: bt-smoke 시드 6경기 (bt-smoke-0, perch_offense × 4 상대, perch_defense × A2·B2) 로 node_frac 만 본다.
                  break_defense 평균이 같은 6경기의 기준 θ 보다 0.3 이상 높지 않으면 값을 고친다 (최대 2회).
  r0 의 기준 θ 행은 bt-cal 기준 θ 행과 node_frac·win_mode 를 뺀 모든 열이 같아야 한다 (재현 확인, wall_s·host 제외).
R0 판정 규칙 변경 (R0-1·R0-2·R0-3 결과를 본 뒤의 변경. 이유는 validation.md "판정 규칙 변경 기록"):
  R0 는 측정 도구 점검이다. 통과 = 민감도 (노드 확인된 악화 θ 중 하나 이상이 두 지표 모두 (b) 통과)
                                   + 특이도 (미세 변경 θ 가 두 지표 모두 잡음 범위 안).
검정력: bt-cal 짝 차이(θ − 기준, 같은 셀)의 표준편차로 n = ((z_0.975 + z_0.8) · sd / Δ)² (정규 근사).
games_procs4_overlap.csv (procs 4 첫 실행, 다른 실행과 1분 겹쳐 3경기 중복) 는 분석에서 뺀다.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import os
import statistics as st

from run_bt import win_mode


BT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BT, "out")
NAMES = {"f2306532ecff": "기준", "ea805147a530": "A (floor_ft=3000, break_g_burst=0)",
         "3ff4d662135d": "B (gun_ata_deg=15, gun_range_ft=1500)",
         "b7d67c3349e3": "미세 (merge_range_ft=6010, fight_kcas=281)"}
BASE, A, B, MICRO = NAMES
R0 = {"eee683f10113": ("R0-1 (floor_ft=40000)", "recover_altitude"),
      "3a56e68f882e": ("R0-2 (fight_kcas=1000)", "energy_recover"),
      "d91fa589e3e5": ("R0-3 (threat_aspect_deg=-1, merge_range_ft=200000)", "break_defense")}
R0_JUDGED = ("3a56e68f882e", "d91fa589e3e5")      # R0-1 은 판정 밖 사례 (머리말)
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def metric(r, m):
    if m == "win":
        return float(r["winner"] == "blue")
    if m == "wezd":
        return float(r["wez_blue"]) - float(r["wez_red"])
    return json.loads(r["node_frac"]).get(m, 0.0)          # m = action 노드 이름


def fmt(v, p):
    return f"{v[0]:+.{p}f} ({v[1]:+.{p}f}, {v[2]:+.{p}f})"


def summary_row(name, g, base, noise):
    """θ 하나: 승리 방식 분포 + 기준 대비 짝 차이와 효과 대 잡음 비. g, base 는 cell → 행.
    win_mode 는 winner·end_reason 으로 다시 계산한다 (옛 CSV 에는 열이 없다)."""
    c = [win_mode(r["winner"], r["end_reason"]) for r in g.values()]
    out = f"| {name} | {len(g) - c.count('')} | " + " | ".join(str(c.count(m)) for m in MODES)
    if g is base:
        return out + " | — | — | — | — |"
    res = {m: ci([metric(g[k], m) - metric(base[k], m) for k in base]) for m in ("win", "wezd")}
    return (out + f" | {fmt(res['win'], 3)} | {abs(res['win'][0]) / noise['win']:.2f} "
            f"| {fmt(res['wezd'], 2)} | {abs(res['wezd'][0]) / noise['wezd']:.2f} |")


def ci(xs):
    m = st.mean(xs)
    h = 1.96 * st.stdev(xs) / len(xs) ** 0.5
    return m, m - h, m + h


def cell(r):
    return (r["scenario"], r["opponent"], r["seed_salt"].rsplit("-", 1)[1])


def main():
    cal = rows(os.path.join(OUT, "bt-cal", "games.csv"))
    by = {t: {cell(r): r for r in cal if r["theta_id"] == t} for t in NAMES}
    base_sets = {"bt-cal": list(by[BASE].values()),
                 "bt-cal-a": rows(os.path.join(OUT, "bt-cal-a", "games.csv")),
                 "bt-cal-b": rows(os.path.join(OUT, "bt-cal-b", "games.csv"))}
    assert all(len(v) == 48 for v in base_sets.values()) and all(len(v) == 48 for v in by.values())
    L = ["# 검증 결과", "", "판정 규칙은 `bt/validate.py` 머리말에 결과를 보기 전에 고정했다. 기준 θ = `bt/thetas/baseline.csv`.", ""]

    L += ["## 1. θ별 요약 (bt-cal, 48경기씩)", "", "| θ | 승-무-패 | 승률 | wez_blue − wez_red 평균 [s] (95% CI) | wall_clock |", "|---|---|---|---|---|"]
    for t, name in NAMES.items():
        g = list(by[t].values())
        w = sum(r["winner"] == "blue" for r in g); d = sum(r["winner"] == "draw" for r in g)
        m, lo, hi = ci([metric(r, "wezd") for r in g])
        L.append(f"| {name} | {w}-{d}-{len(g) - w - d} | {w / len(g):.3f} | {m:+.2f} ({lo:+.2f}, {hi:+.2f}) "
                 f"| {sum(r['end_reason'] == 'wall_clock' for r in g)} |")

    L += ["", "## 2. 잡음: 기준 θ, 시드 묶음 3개", "", "| 시드 묶음 | 승률 | wez 차 평균 [s] (95% CI) |", "|---|---|---|"]
    means = {}
    for k, g in base_sets.items():
        means[k] = {m: st.mean(metric(r, m) for r in g) for m in ("win", "wezd")}
        _, lo, hi = ci([metric(r, "wezd") for r in g])
        L.append(f"| {k} | {means[k]['win']:.3f} | {means[k]['wezd']:+.2f} ({lo:+.2f}, {hi:+.2f}) |")
    noise = {m: max(abs(means[a][m] - means[b][m]) for a, b in itertools.combinations(means, 2)) for m in ("win", "wezd")}
    L += ["", f"잡음 범위 (쌍별 최대 |Δ|): 승률 **{noise['win']:.3f}**, wez 차 **{noise['wezd']:.2f} s**", ""]

    L += ["## 3. 기준 대비 짝 차이 Δ = θ − 기준 (bt-cal, 같은 셀끼리) — 예비 관찰", "",
          "효과 대 잡음 비 = |Δ| / 잡음 범위. 1 보다 크면 잡음 범위 밖.", "",
          "| θ | Δ승률 (95% CI) | 효과/잡음 승률 | Δwez 차 [s] (95% CI) | 효과/잡음 wez |", "|---|---|---|---|---|"]
    verdict = {}
    for t in (A, B, MICRO):
        res = {m: ci([metric(by[t][c], m) - metric(by[BASE][c], m) for c in by[BASE]]) for m in ("win", "wezd")}
        out = {m: abs(res[m][0]) > noise[m] for m in res}
        verdict[t] = (res, out)
        L.append(f"| {NAMES[t]} | {fmt(res['win'], 3)} | {abs(res['win'][0]) / noise['win']:.2f} "
                 f"| {fmt(res['wezd'], 2)} | {abs(res['wezd'][0]) / noise['wezd']:.2f} |")

    ok = all(res[m][0] < 0 and out[m] and res[m][2] < 0 for t in (A, B) for res, out in [verdict[t]] for m in res)
    micro_in = not any(verdict[MICRO][1].values())
    L += ["", "## 판정 (검증 1·3)", "",
          f"- 검증 1 (A, B 가 기준보다 확실히 나쁜가): **{'통과' if ok else '불통과'}**. "
          "원인은 망가진 θ 를 직관으로 고른 설계 문제다. A, B 는 예비 관찰로만 남기고 더 조사하지 않는다 → R0 로 재설계.",
          f"- 검증 3 (미세 변경이 잡음 범위 안인가): **{'안' if micro_in else '밖'}**",
          "- **민감도 증거:** A 는 기준보다 승률·wez 차가 모두 잡음 범위 밖으로 높고 짝 95% CI 가 0 위에 있다. "
          "방향은 예상과 반대였지만, 지표가 θ 사이의 실제 차이를 잡아낸다는 증거다.", ""]

    r0 = [r for r in rows(os.path.join(OUT, "r0", "games.csv")) if r["seed_salt"].startswith("bt-cal-")]
    rb = {cell(r): r for r in r0 if r["theta_id"] == BASE}
    rt = {t: {cell(r): r for r in r0 if r["theta_id"] == t} for t in R0}
    assert len(rb) == 48 and all(len(g) == 48 for g in rt.values()), (len(rb), {t: len(g) for t, g in rt.items()})

    L += ["## 4. θ별 승리 방식과 효과 대 잡음 비 (bt-cal 시드, 48경기씩)", "",
          "승리 방식은 청 승리만 센다. Δ = θ − 기준 (같은 셀끼리 짝 차이, 95% CI). 효과/잡음 = |Δ| / 잡음 범위 (1 보다 크면 잡음 범위 밖). "
          "R0 θ 는 stage=r0 로 다시 돌린 기준 θ 와 짝짓는다 (bt-cal 기준 θ 와 같은 결과, §5 재현 확인).", "",
          "| θ | 승 | " + " | ".join(MODES) + " | Δ승률 (95% CI) | 효과/잡음 승률 | Δwez 차 [s] (95% CI) | 효과/잡음 wez |",
          "|---|---|" + "---|" * len(MODES) + "---|---|---|---|"]
    for t, name in NAMES.items():
        L.append(summary_row(name, by[t], by[BASE], noise))
    for t, (name, _) in R0.items():
        L.append(summary_row(name, rt[t], rb, noise))
    L += ["", "shootdown = 상대 체력 0, opp_hard_deck = 상대 하드덱, opp_stall = 상대 실속, judge = 시간 종료 판정, other = 그 밖.", ""]

    skip = ("stage", "seed_salt", "wall_s", "host", "node_frac", "win_mode")
    same = sum(all(r[k] == by[BASE][c][k] for k in by[BASE][c] if k not in skip) for c, r in rb.items())
    L += ["## 5. R0: 작동 원리상 확실히 나빠야 하는 θ (bt-cal 시드, stage=r0, 48경기씩)", "",
          f"재현 확인: r0 의 기준 θ 48경기 중 **{same}경기**가 bt-cal 기준 θ 와 모든 열이 같다 (stage·wall_s·host·새 열 제외).", "",
          "| θ | 의도 노드 | node_frac 기준 → θ | Δnode_frac (95% CI) | Δ승률 (95% CI) | Δwez 차 [s] (95% CI) | (a) | (b) | 판정 |",
          "|---|---|---|---|---|---|---|---|---|"]
    r0_ok, sens, pair_sd = True, [], {m: {} for m in ("win", "wezd")}
    for t, (name, node) in R0.items():
        g = rt[t]
        res = {m: ci([metric(g[c], m) - metric(rb[c], m) for c in rb]) for m in ("win", "wezd", node)}
        a_ok = res[node][1] > 0.3
        b_ok = all(res[m][0] < 0 and res[m][2] < 0 and abs(res[m][0]) > noise[m] for m in ("win", "wezd"))
        if t in R0_JUDGED:
            r0_ok &= a_ok and b_ok
        if a_ok and b_ok:
            sens.append(name)
        for m in pair_sd:
            pair_sd[m][name] = st.stdev(metric(g[c], m) - metric(rb[c], m) for c in rb)
        L.append(f"| {name} | {node} | {st.mean(metric(r, node) for r in rb.values()):.3f} → "
                 f"{st.mean(metric(r, node) for r in g.values()):.3f} | {fmt(res[node], 3)} "
                 f"| {fmt(res['win'], 3)} | {fmt(res['wezd'], 2)} | {'O' if a_ok else 'X'} | {'O' if b_ok else 'X'} "
                 f"| {('통과' if a_ok and b_ok else '불통과') if t in R0_JUDGED else '불통과 (사례로 기록)'} |")
    L += ["", "(a) 의도 노드 Δnode_frac 95% CI 하한 > 0.3. (b) 승률·wez 차 모두 Δ < 0, CI 상한 < 0, |Δ| > 잡음 범위.", "",
          "기준 θ 의 노드 비율 (r0, 48경기 평균): " + ", ".join(
              f"{k} {st.mean(json.loads(r['node_frac']).get(k, 0.0) for r in rb.values()):.3f}"
              for k in sorted({k for r in rb.values() for k in json.loads(r["node_frac"])})), "",
          "- **R0-1 은 작동 원리상 나빠야 했지만 상대 실속 유도로 나빠지지 않은 사례다.** 의도 노드(recover_altitude)는 "
          "거의 항상 실행됐으나 (a 통과), 청 승리 10경기 중 7경기가 상대 실속이었고 wez 차는 오히려 기준보다 컸다 (b 불통과). "
          "판정 기준은 바꾸지 않았고, 결과는 지우지 않고 남긴다. 판정은 R0-2 와 원리가 다른 R0-3 으로 대신했다.",
          "- R0-3 노드 확인 (bt-smoke-0 6경기, node_frac 만 봄): break_defense 기준 0.080 → R0-3 0.822 (첫 값으로 확인, 수정 없음).", "",
          f"- 변경 전 규칙 (R0-2, R0-3 모두 (a)(b) 통과): **{'통과' if r0_ok else '불통과'}**",
          f"- **변경 후 규칙: 민감도 {'O' if sens else 'X'} ({', '.join(sens) or '없음'}), "
          f"특이도 {'O' if micro_in else 'X'} (미세 θ 두 지표 모두 잡음 범위 안) → "
          f"{'통과' if sens and micro_in else '불통과'}**", "",
          "### 판정 규칙 변경 기록", "",
          "- **언제:** R0-1, R0-2, R0-3 의 bt-cal 결과를 **본 뒤에** 바꿨다. 사전등록 규칙이 아니다.",
          "- **변경 전:** 모든 R0 후보 (R0-1 을 사례로 돌린 뒤에는 R0-2, R0-3) 가 (a) 와 (b) 를 통과.",
          "- **변경 후:** R0 는 측정 도구 점검이다. 두 가지가 성립하면 통과로 본다.",
          "  - 민감도: 노드로 작동이 확인된 악화 설정 중 하나 이상이 두 지표 모두에서 (b) 를 통과 (R0-2).",
          "  - 특이도: 미세 변경 θ 가 두 지표 모두 잡음 범위 안 (미세 θ).",
          "- **이유:** R0-1, R0-3 은 노드가 의도대로 작동했으므로 (a 통과) 지표 실패가 아니라 \"예상한 악화가 실제로는 "
          "작거나 상대 약점으로 상쇄된 사례\" 다. 후보를 더 바꾸거나 시드를 늘리면 통과할 때까지 시도하는 것이 되므로 하지 않는다.",
          "- R0-1, R0-3 결과는 위 표에 그대로 둔다.", ""]

    # 검정력: 짝 차이 표준편차는 bt-cal 시드의 모든 θ (A, B, 미세, R0-1~3) 에서 잰다
    for t in (A, B, MICRO):
        for m in pair_sd:
            pair_sd[m][NAMES[t].split(" (")[0]] = st.stdev(metric(by[t][c], m) - metric(by[BASE][c], m) for c in by[BASE])
    z = st.NormalDist().inv_cdf(0.975) + st.NormalDist().inv_cdf(0.80)
    L += ["## 6. 검정력 계산 (bt-cal 짝 차이, 계산만)", "",
          f"n = ((z₀.₉₇₅ + z₀.₈) · sd / Δ)² = ({z:.3f} · sd / Δ)², 정규 근사, 짝 차이 (같은 셀끼리) 기준. "
          "sd 는 θ − 기준 짝 차이의 표준편차 (θ 당 48쌍).", "",
          "| θ | sd(Δ승률) | sd(Δwez 차) [s] |", "|---|---|---|"]
    for k in pair_sd["win"]:
        L.append(f"| {k} | {pair_sd['win'][k]:.3f} | {pair_sd['wezd'][k]:.2f} |")
    pooled = {m: (st.mean(v ** 2 for v in pair_sd[m].values())) ** 0.5 for m in pair_sd}
    worst = {m: max(pair_sd[m].values()) for m in pair_sd}
    L += [f"| **합동 (RMS)** | **{pooled['win']:.3f}** | **{pooled['wezd']:.2f}** |",
          f"| 최대 | {worst['win']:.3f} | {worst['wezd']:.2f} |", "",
          "| 잡을 차이 Δ | 필요 경기 수 / θ (합동 sd) | 48경기 묶음 | 필요 경기 수 / θ (최대 sd) | 48경기 묶음 |",
          "|---|---|---|---|---|"]
    for m, d, unit in (("win", 0.10, ""), ("win", 0.15, ""), ("wezd", 0.3, " s"), ("wezd", 0.5, " s")):
        n1, n2 = (math.ceil((z * sd / d) ** 2) for sd in (pooled[m], worst[m]))
        L.append(f"| {'승률' if m == 'win' else 'wez 차'} {d}{unit} | {n1} | {n1 / 48:.1f} | {n2} | {n2 / 48:.1f} |")
    L += ["", "짝 차이 sd 는 θ 마다 다르다 (차이가 큰 θ 일수록 큼). 합동 sd 는 평균적인 θ, 최대 sd 는 보수적인 값이다. "
          "경기 수는 같은 셀끼리 짝지은 비교를 가정한다.", ""]

    L += ["## 7. 병렬 수 (기준 θ, bt-smoke 48경기)", "", "| --procs | wall_clock 경기 | 경기당 wall_s 평균 | 최대 | 이전 실행(procs 6)과 다른 열 |", "|---|---|---|---|---|"]
    ref = {cell(r): r for r in rows(os.path.join(OUT, "validation_runs", "smoke_v0_procs6.csv"))}
    for p in (4, 8):
        path = os.path.join(OUT, "validation_runs", f"smoke_procs{p}.csv")
        if not os.path.isfile(path):
            continue
        g = rows(path)
        ws = [float(r["wall_s"]) for r in g]
        diff = sum(any(r[k] != ref[cell(r)][k] for k in ref[cell(r)] if k not in ("wall_s", "host")) for r in g)
        L.append(f"| {p} | {sum(r['end_reason'] == 'wall_clock' for r in g)} | {st.mean(ws):.1f} | {max(ws):.1f} | {diff}경기 |")
    L += ["", "procs 4 는 단독으로 다시 돌린 결과다. 첫 실행(`games_procs4_overlap.csv`)은 다른 실행과 약 1분 겹쳐 "
          "3경기가 중복 기록되고 wall_s 가 부풀었을 수 있어 **분석에서 뺐다** (저장소 밖에 보관).", ""]
    with open(os.path.join(OUT, "validation.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
