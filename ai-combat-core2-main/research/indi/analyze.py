"""결과 집계 → 논문용 표 (results/indi/summary.md). 있는 결과 파일만 읽는다.

대응 검정 (같은 red·시나리오·시드의 A/B 경기 쌍):
  승점  : 부호 검정(이항, 동점 제외) + Wilcoxon 부호순위
  HP 차 : Wilcoxon 부호순위
  격추  : McNemar 정확 검정(불일치 쌍의 이항) — A 만 격추 vs B 만 격추

    python research/indi/analyze.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from scipy.stats import binomtest, wilcoxon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sweep import _points

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "indi")


def _load(name):
    p = os.path.join(RES, name)
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else None


def _kill(g):
    return g["winner"] == "blue" and g["condition"] == "health_zero"


def tests(ga: list, gb: list) -> dict:
    dp = np.array([_points(b) - _points(a) for a, b in zip(ga, gb)])
    dh = np.array([(b["hp_blue"] - b["hp_red"]) - (a["hp_blue"] - a["hp_red"]) for a, b in zip(ga, gb)])
    up, dn = int((dp > 0).sum()), int((dp < 0).sum())
    ka, kb = [_kill(g) for g in ga], [_kill(g) for g in gb]
    only_b = sum(b and not a for a, b in zip(ka, kb))
    only_a = sum(a and not b for a, b in zip(ka, kb))
    w = lambda x: float(wilcoxon(x).pvalue) if np.any(x != 0) else 1.0
    return dict(n=len(dp), better=up, worse=dn,
                p_sign=float(binomtest(up, up + dn).pvalue) if up + dn else 1.0,
                p_wil_pts=w(dp), p_wil_hp=w(dh),
                kills_a=int(sum(ka)), kills_b=int(sum(kb)),
                p_mcnemar=float(binomtest(only_b, only_b + only_a).pvalue) if only_a + only_b else 1.0)


def _fmt_p(p):
    return f"{p:.3f}" + (" *" if p < 0.05 else "")


def duel_table(d: dict, title: str) -> list[str]:
    out = [f"## {title}", "",
           f"A(기준) = `{d['A']}`", ""] + [f"{k} = `{v}`" for k, v in d["B"].items()] + ["",
           "| 조건 | B | n | 승률 A | 승률 B | Δ승점 [95% CI] | ΔHP [95% CI] | 개선/악화 | p(부호) | p(Wilcoxon HP) | 격추 A→B | p(McNemar) | 한계DQ A/B |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cname, block in d["conds"].items():
        ga = block["games_A"]
        for bname, v in block.items():
            if bname == "games_A":
                continue
            s, t = v["summary"], tests(ga, v["games"])
            out.append(f"| {cname} | {bname} | {s['n']} | {s['win_A']:.3f} | {s['win_B']:.3f} | "
                       f"{s['d_points']:+.3f} [{s['d_points_ci'][0]:+.3f}, {s['d_points_ci'][1]:+.3f}] | "
                       f"{s['d_hp']:+.1f} [{s['d_hp_ci'][0]:+.1f}, {s['d_hp_ci'][1]:+.1f}] | "
                       f"{t['better']}/{t['worse']} | {_fmt_p(t['p_sign'])} | {_fmt_p(t['p_wil_hp'])} | "
                       f"{t['kills_a']}→{t['kills_b']} | {_fmt_p(t['p_mcnemar'])} | {s['dq_A']}/{s['dq']} |")
    return out + [""]


def breakdown(d: dict, cond: str = "nominal") -> list[str]:
    """E3 명목: 시나리오·대항군별 Δ승점 (B 별)."""
    if cond not in d["conds"]:
        return []
    block = d["conds"][cond]
    ga = block["games_A"]
    out = [f"### {cond} — 시나리오·대항군별 Δ승점 (B − A)", ""]
    for key, label in (("scenario", "시나리오"), ("red", "대항군")):
        cats = sorted({g[key] for g in ga})
        out += [f"| {label} | " + " | ".join(b for b in block if b != "games_A") + " |",
                "|---|" + "---|" * (len(block) - 1)]
        for c in cats:
            cells = []
            for bname, v in block.items():
                if bname == "games_A":
                    continue
                pairs = [(a, b) for a, b in zip(ga, v["games"]) if a[key] == c]
                cells.append(f"{np.mean([_points(b) - _points(a) for a, b in pairs]):+.3f} (n={len(pairs)})")
            out.append(f"| {c} | " + " | ".join(cells) + " |")
        out.append("")
    return out


def e4_table(d: dict) -> list[str]:
    out = ["## E4 PSO 최적해", "", f"기준 J₀ = {d['ref']['J']:.4f}, A₀ = {d['ref']['A']:.5f}, 평가 {len(d['log'])}회, "
           f"실격 {sum(e['dq'] for e in d['log'])}", "",
           "| γ | J/J₀ | A/A₀ | k_p | k_q | filt_hz | k_att | k_ff | λ |", "|---|---|---|---|---|---|---|---|---|"]
    for b in d["best"]:
        e = min((e for e in d["log"] if e["gamma"] == b["gamma"]), key=lambda e: e["cost"])
        c = b["cfg"]
        out.append(f"| {b['gamma']:g} | {e['J'] / d['ref']['J']:.3f} | {e['A'] / d['ref']['A']:.3f} | {c['k_p']:.1f} | "
                   f"{c['k_q']:.1f} | {c['filt_hz']:.1f} | {c['k_att']:.2f} | {c['k_ff']:.2f} | {c['lam']:.2f} |")
    return out + ["", f"파레토 비지배점 {len(d['pareto'])}개 (J/J₀ {d['pareto'][0]['J_ratio']:.3f}–"
                      f"{d['pareto'][-1]['J_ratio']:.3f}, A/A₀ {d['pareto'][-1]['A_ratio']:.3f}–{d['pareto'][0]['A_ratio']:.3f})", ""]


def e2_table(d: dict) -> list[str]:
    out = ["## E2 단일 변수 민감도", "",
           "| 변수 | 값 | J/J₀ | 추종실격 | Δ승점 [95% CI] | ΔHP [95% CI] | 승률 | p(부호) | 한계DQ | Nz max |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    base = d["games"][0] if d.get("games") else None
    for i, r in enumerate(d["rows"]):
        du = r.get("duel")
        if du is None:
            out.append(f"| {r['var']} | {r['value']} | {r['J_ratio']:.3f} | {r['bench_dq']} | — | — | — | — | — | — |")
            continue
        t = tests(base, d["games"][i]) if base else {"p_sign": float("nan")}
        out.append(f"| {r['var']} | {r['value'] if r['value'] is None else round(r['value'], 3)} | {r['J_ratio']:.3f} | "
                   f"{r['bench_dq']} | {du['d_points']:+.3f} [{du['d_points_ci'][0]:+.3f}, {du['d_points_ci'][1]:+.3f}] | "
                   f"{du['d_hp']:+.1f} [{du['d_hp_ci'][0]:+.1f}, {du['d_hp_ci'][1]:+.1f}] | {du['win_rate']:.3f} | "
                   f"{_fmt_p(t['p_sign'])} | {du['dq']} | {du['nz_max']:.2f} |")
    return out + [""]


PROC = [("lag_p_ms", "롤 응답 지연 [ms]"), ("lag_q_ms", "피치 응답 지연 [ms]"), ("rms_p", "롤레이트 추종 RMSE [°/s]"),
        ("rms_q", "피치레이트 추종 RMSE [°/s]"), ("g_ratio", "G 실현률"), ("act_ail", "에일러론 활동"),
        ("act_elev", "승강타 활동"), ("wez_s", "WEZ 체류 [s]"), ("gun_s", "조준해(ATA<2°) 체류 [s]"),
        ("off_frac", "공세 위치 비율"), ("def_frac", "수세 위치 비율"), ("e_adv_ft", "에너지 우위 [ft]")]
FIRST = [("t_first_wez", "최초 WEZ 진입"), ("t_first_gun", "최초 조준해")]


def holm(ps: list[float]) -> list[float]:
    """Holm–Bonferroni 보정 p (단조 증가 보장). 과정 지표 표 하나(조건·B별 12 지표)를 한 가족으로 본다."""
    m = len(ps)
    order = np.argsort(ps)
    adj, run = [0.0] * m, 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i]))
        adj[i] = run
    return adj


def process_table(d: dict, title: str) -> list[str]:
    """교전 과정 지표의 대응 비교 (combat_blue 가 기록된 duel 결과만). 평균 A, 평균 B, 평균 Δ, Wilcoxon p."""
    out = [f"## {title} — 교전 과정 지표 (blue, 대응 비교)", ""]
    for cname, block in d["conds"].items():
        ga = block["games_A"]
        if not ga or "combat_blue" not in ga[0]:
            continue
        for bname, v in block.items():
            if bname == "games_A":
                continue
            gb = v["games"]
            out += [f"### {cname} · {bname} (n={len(ga)})", "",
                    "| 지표 | A 평균 | B 평균 | Δ(B−A) 평균 | p(Wilcoxon) | p(Holm) |", "|---|---|---|---|---|---|"]
            rows = []
            for key, lab in PROC:
                pa = [(a["combat_blue"].get(key), b["combat_blue"].get(key)) for a, b in zip(ga, gb)]
                pa = [(x, y) for x, y in pa if x is not None and y is not None and x == x and y == y]
                if not pa:
                    continue
                xa, xb = np.array(pa).T
                dd = xb - xa
                rows.append((lab, xa.mean(), xb.mean(), dd.mean(),
                             float(wilcoxon(dd).pvalue) if np.any(dd != 0) else 1.0))
            for (lab, ma, mb, md, p), ph in zip(rows, holm([r[4] for r in rows])):
                out.append(f"| {lab} | {ma:.4g} | {mb:.4g} | {md:+.4g} | {p:.3f} | {_fmt_p(ph)} |")
            for key, lab in FIRST:
                ta = [a["combat_blue"].get(key) for a in ga]
                tb = [b["combat_blue"].get(key) for b in gb]
                ra, rb = np.mean([x is not None for x in ta]), np.mean([x is not None for x in tb])
                both = [(x, y) for x, y in zip(ta, tb) if x is not None and y is not None]
                if both:
                    xa, xb = np.array(both).T
                    dd = xb - xa
                    p = float(wilcoxon(dd).pvalue) if np.any(dd != 0) else 1.0
                    med = f"{np.median(xa):.1f} → {np.median(xb):.1f} s (둘 다 달성 n={len(both)}, p={_fmt_p(p)})"
                else:
                    med = "—"
                out.append(f"| {lab} 달성률 / 중앙 시각 | {ra:.2f} | {rb:.2f} | {rb - ra:+.2f} | {med} |")
            out.append("")
    return out


def cond_ms(name: str) -> float:
    """조건 이름 → 측정 지연 [ms] (dt<틱>, nominal=0, delay30=4틱, delay90=11틱)."""
    ticks = {"nominal": 0, "delay30": 4, "delay90": 11}.get(name)
    if ticks is None:
        ticks = int(name.lstrip("bdt"))
    return ticks / 120 * 1000


def dose_table(ds: list[dict], title: str) -> list[str]:
    """지연 반응 곡선: 설정별 지연에 따른 승률·G 실현률·공세 비율 (여러 duel 결과를 합쳐 A 공유)."""
    series = {}                                         # 설정 → {ms: games}
    for d in ds:
        for cname, block in d["conds"].items():
            ms = cond_ms(cname)
            series.setdefault("A", {})[ms] = block["games_A"]
            for k, v in block.items():
                if k != "games_A":
                    series.setdefault(k, {})[ms] = v["games"]
    msl = sorted({m for s in series.values() for m in s})
    out = [f"## {title}", "", "| 설정 | 지표 | " + " | ".join(f"{m:.0f} ms" for m in msl) + " |",
           "|---|---|" + "---|" * len(msl)]
    for k, s in series.items():
        for lab, f in (("승률", lambda g: np.mean([_points(x) for x in g])),
                       ("G 실현률", lambda g: np.nanmedian([x["combat_blue"].get("g_ratio") or np.nan for x in g])),
                       ("공세 비율", lambda g: np.mean([x["combat_blue"]["off_frac"] for x in g]))):
            out.append(f"| {k} | {lab} | " + " | ".join(f"{f(s[m]):.3f}" if m in s else "—" for m in msl) + " |")
    return out + [""]


def main() -> int:
    lines = ["# INDI 최적화 연구 — 결과 요약 (자동 생성: research/indi/analyze.py)", "",
             "\\* = p < 0.05. Δ 는 같은 (대항군, 시나리오, 시드) 대응 쌍의 B − A 평균.", ""]
    e4, e3, e5 = (_load(n) for n in ("e4.json", "e3_nominal.json", "e5.json"))
    e2 = _load("e2_n100.json") or _load("e2.json")          # 표본 확대본 우선
    if e4:
        lines += e4_table(e4)
    if e3:
        lines += duel_table(e3, "E3 기준 vs 최적 (명목 조건)") + breakdown(e3)
    if e5:
        lines += duel_table(e5, "E5 강건성")
    if e2:
        lines += e2_table(e2)
    for name, title in (("e4_wide.json", None), ("e3_wide_nominal.json", "배치 2: 범위 확장 해 (명목)"),
                        ("e3_wide_delay.json", "배치 2: 범위 확장 해 (지연)"),
                        ("e3_mirror.json", "배치 2: 양측 튜닝 (red = γ=0 INDI)")):
        d = _load(name)
        if d and title:
            lines += duel_table(d, title)
        elif d:
            lines += ["## 배치 2: E4 범위 확장 (k_p 4–40, k_att 2–16)", ""] + e4_table(d)[2:]
    d = _load("e3_process.json")
    if d:
        lines += duel_table(d, "배치 3: 교전 과정 지표 실험 (승패)") + process_table(d, "배치 3")
    dose = [d for d in (_load("e5_dose.json"), _load("e5_dose_rev.json")) if d]
    if dose:
        lines += dose_table(dose, "배치 4: 측정 지연 반응 곡선 (P1)")
    for name, title in (("e3_tree_textbook.json", "배치 4: blue 트리 textbook_headon (P2)"),
                        ("e3_tree_starter.json", "배치 4: blue 트리 starter (P2)")):
        d = _load(name)
        if d:
            lines += duel_table(d, title) + process_table(d, title)
    txt = "\n".join(lines)
    with open(os.path.join(RES, "summary.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
