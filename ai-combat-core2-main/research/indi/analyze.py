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
    txt = "\n".join(lines)
    with open(os.path.join(RES, "summary.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
