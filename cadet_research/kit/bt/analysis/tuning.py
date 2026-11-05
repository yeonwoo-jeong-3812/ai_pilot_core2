"""튜닝 BT 비교 분석 (cadet_research/PREREG_BT_ADDENDUM_TUNING.md §6). games.csv 는 읽기만 한다.

  python bt/analysis/tuning.py        # → bt/out/analysis/tuning_report.md, tuning_winrate.png, tuning_nodefrac.png

1차 지표 승률 (청 승 = 1). 묶음별 V1·V2·V3·V4·V6 vs V0 짝 비교 (같은 기하·상대·시드): 짝 이진 차이 평균의 95% CI (t, n − 1),
McNemar 정확 검정 (불일치 쌍 이항, 양측), Holm (가족 5). 추가 비교 V3 vs V1, V6 vs V3 (Holm 가족 2). V4 vs V0 ±5%p TOST.
판정은 상대 4종 전체. 바닥 상대 (그 묶음 V0 승률 < 5%) 를 뺀 결과, 보조 지표, 탐색 (가)(나)(다) 는 서술용.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anova import load  # noqa: E402
from confirm import CELL, holm, paired  # noqa: E402
from io_utils import read_design, read_games  # noqa: E402

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS = {"patched": os.path.join(BT, "out", "bt-confirm2", "games.csv"),
        "heldout": os.path.join(BT, "out", "bt-confirm2-heldout", "games.csv")}
VARIANTS = os.path.join(BT, "thetas", "tuned6.csv")
MAIN = ("V1", "V2", "V3", "V4", "V6")
EXTRA = (("V3", "V1"), ("V6", "V3"))
EXPECTED = {"V1": "<", "V2": ">", "V3": ">", "V4": "≈", "V6": ">"}
EQ_MARGIN, ALPHA, FLOOR = 0.05, 0.05, 0.05
NODE_V = ("V0", "V1", "V2", "V3", "V6")
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")


def win_test(d: np.ndarray, margin: float = EQ_MARGIN) -> dict:
    """짝 이진 차이 d ∈ {−1, 0, 1} → 평균, 95% CI (t), McNemar 정확 p (양측), TOST p (±margin)."""
    n, m = len(d), d.mean()
    se = d.std(ddof=1) / np.sqrt(n)
    b, c = int((d > 0).sum()), int((d < 0).sum())
    p_mc = stats.binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
    if se > 0:
        tq = stats.t.ppf(0.975, n - 1)
        lo, hi = m - tq * se, m + tq * se
        p_tost = max(stats.t.sf((m + margin) / se, n - 1), stats.t.cdf((m - margin) / se, n - 1))
    else:
        lo = hi = m
        p_tost = 0.0 if abs(m) < margin else 1.0
    return dict(n=n, diff=m, ci_lo=lo, ci_hi=hi, b=b, c=c, p_mcnemar=p_mc, p_tost=p_tost)


def pair_table(df: pd.DataFrame, ids: dict, pairs, family: bool = True) -> pd.DataFrame:
    """pairs = [(변형, 비교 기준)]. 짝 차이 승률 검정 + Holm (가족 = pairs)."""
    rows = []
    for v, ref in pairs:
        pr = paired(df[df.theta_id.isin([ids[v], ids[ref]])], ids[ref])
        rows.append(dict(variant=v, ref=ref, **win_test(pr.d_win.values), d_dwez=pr.d_dwez.mean(), d_hp=pr.d_hp.mean()))
    t = pd.DataFrame(rows)
    if family:
        t["p_holm"] = holm(t.p_mcnemar.values)
    return t


def floor_opponents(df: pd.DataFrame, v0: str) -> list[str]:
    w = df[df.theta_id == v0].assign(win=lambda g: g.winner == "blue").groupby("opponent").win.mean()
    return sorted(w[w < FLOOR].index)


def nodes(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([json.loads(x) for x in df.node_frac], index=df.index).fillna(0.0)


def describe(df: pd.DataFrame) -> pd.DataFrame:
    """θ 별 보조·탐색 지표 (서술용)."""
    g = df.assign(win=df.winner == "blue", hp=df.hp_blue_raw - df.hp_red_raw,
                  blue_down=(df.winner == "red") & (df.end_reason == "health_zero"),
                  blue_hd=(df.winner == "red") & (df.end_reason == "hard_deck"),
                  no_contact=df.end_reason == "no_contact").groupby("variant", sort=True)
    t = g.agg(n=("win", "size"), win=("win", "mean"), dwez=("dwez", "mean"), hp=("hp", "mean"), blue_down=("blue_down", "mean"),
              blue_hd=("blue_hd", "mean"), no_contact=("no_contact", "mean"), hp_blue=("hp_blue_raw", "mean"), e_adv=("e_adv_ft", "mean"))
    for m in MODES:
        t[m] = g.win_mode.apply(lambda s, m=m: int((s == m).sum()))
    return t


def quality(df: pd.DataFrame, nvar: int) -> dict:
    key = ["theta_id", *CELL]
    return dict(games=len(df), expected=nvar * 432, dup=int(df.duplicated(key).sum()),
                wall_clock=int((df.end_reason == "wall_clock").sum()), disqualified=int((df.end_reason == "disqualified").sum()),
                code_commit=sorted(set(df.code_commit)), engine_sha=sorted(set(df.engine_sha)))


def f3(x):
    return f"{x:+.3f}"


def plot_winrate(res: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for k, (s, t) in enumerate(res.items()):
        x = np.arange(len(t)) + (k - 0.5) * 0.25
        ax.errorbar(x, t["diff"], yerr=[t["diff"] - t.ci_lo, t.ci_hi - t["diff"]], fmt="o", capsize=3, label=s)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(np.arange(len(MAIN)), MAIN)
    ax.set_ylabel("win rate diff vs V0 (95% CI)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_nodes(nf: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vs = ("V0", "V1", "V3", "V6")
    fig, axes = plt.subplots(1, len(nf), figsize=(11, 3.8), sharey=True)
    for ax, (s, t) in zip(np.atleast_1d(axes), nf.items()):
        t = t.loc[list(vs)]
        x = np.arange(t.shape[1])
        for k, v in enumerate(vs):
            ax.bar(x + (k - 1.5) * 0.2, t.loc[v], 0.2, label=v)
        ax.set_xticks(x, t.columns, rotation=45, ha="right", fontsize=8)
        ax.set_title(s)
    np.atleast_1d(axes)[0].set_ylabel("blue node_frac (mean)")
    np.atleast_1d(axes)[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patched", default=SETS["patched"])
    ap.add_argument("--heldout", default=SETS["heldout"])
    ap.add_argument("--variants", default=VARIANTS)
    ap.add_argument("--out", default=os.path.join(BT, "out", "analysis"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    var = read_design(a.variants)
    ids = dict(zip(var.variant, var.theta_id))
    name = {t: v for v, t in ids.items()}
    data, qual = {}, {}
    for s, p in (("patched", a.patched), ("heldout", a.heldout)):
        qual[s] = quality(read_games(p), len(ids))      # wall_clock 포함 원본으로 품질 점검
        d = load(p)
        assert set(d.opponent_set) == {s}, (s, set(d.opponent_set))
        data[s] = d.assign(variant=d.theta_id.map(name))
        assert data[s].variant.notna().all(), "tuned6 에 없는 θ"

    main_t, extra_t, eq, floors, nofloor, desc, nf, opp_w = {}, {}, {}, {}, {}, {}, {}, {}
    for s, d in data.items():
        main_t[s] = pair_table(d, ids, [(v, "V0") for v in MAIN])
        extra_t[s] = pair_table(d, ids, EXTRA)
        eq[s] = main_t[s].set_index("variant").loc["V4"]
        floors[s] = floor_opponents(d, ids["V0"])
        nofloor[s] = pair_table(d[~d.opponent.isin(floors[s])], ids, [(v, "V0") for v in MAIN], family=False)
        desc[s] = describe(d)
        nf[s] = nodes(d).groupby(d.variant).mean().loc[list(NODE_V)]
        opp_w[s] = d.assign(win=d.winner == "blue").pivot_table(index="variant", columns="opponent", values="win", aggfunc="mean")

    L = ["# 튜닝 BT 비교 결과 (사후 추가 실험)", "",
         "계획: `cadet_research/PREREG_BT_ADDENDUM_TUNING.md` (태그 `prereg-bt-tuning-v1`). 분석 코드 `bt/analysis/tuning.py` 는 태그 커밋에 들어 있다.",
         "1차 지표 승률. 짝 = 같은 기하·상대·시드 (묶음당 432쌍). 판정은 상대 4종 전체, 바닥 상대 제외·보조·탐색은 서술용.", ""]
    L += ["## 1. 주 판정 (변형 − V0 승률 차)", "",
          "| 묶음 | 변형 | n | 승률 차 (95% CI) | V 만 승 / V0 만 승 | McNemar p | Holm p (가족 5) | 유의 (Holm < 0.05) | TOST p (±5%p) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s, t in main_t.items():
        for r in t.itertuples():
            L.append(f"| {s} | {r.variant} | {r.n} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) | {r.b} / {r.c} | {r.p_mcnemar:.3g} "
                     f"| {r.p_holm:.3g} | {'**예**' if r.p_holm < ALPHA else '아니오'} | {r.p_tost:.3g} |")
    L += ["", "V4 vs V0 동등성 (±5%p TOST, α 0.05): " + ", ".join(
        f"{s} {'**동등**' if e.p_tost < ALPHA else '동등 아님'} (p {e.p_tost:.3g}, 차 {f3(e['diff'])})" for s, e in eq.items()), ""]
    L += ["## 2. 추가 비교 (Holm 가족 2)", "", "| 묶음 | 비교 | 승률 차 (95% CI) | McNemar p | Holm p | 유의 |", "|---|---|---|---|---|---|"]
    for s, t in extra_t.items():
        L += [f"| {s} | {r.variant} − {r.ref} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) | {r.p_mcnemar:.3g} | {r.p_holm:.3g} "
              f"| {'**예**' if r.p_holm < ALPHA else '아니오'} |" for r in t.itertuples()]
    L += ["", "## 3. 사전 예상 방향 vs 실제", "", "실제 = 점추정 부호, 괄호는 Holm 유의 여부 (V4 는 TOST 동등 여부). 판정에 쓰지 않는다.", "",
          "| 변형 | 예상 | " + " | ".join(main_t) + " |", "|---|---|" + "---|" * len(main_t)]
    for v in MAIN:
        cells = []
        for s, t in main_t.items():
            r = t.set_index("variant").loc[v]
            sign = ">" if r["diff"] > 0 else "<" if r["diff"] < 0 else "="
            tag = ("동등" if r.p_tost < ALPHA else "동등 아님") if v == "V4" else ("유의" if r.p_holm < ALPHA else "유의 아님")
            cells.append(f"{sign} ({f3(r['diff'])}, {tag})")
        L.append(f"| {v} | {EXPECTED[v]} V0 | " + " | ".join(cells) + " |")
    L += ["", "## 4. 상대별 승률", "", "† = 바닥 상대 (그 묶음 V0 승률 < 5%).", ""]
    for s, w in opp_w.items():
        cols = list(w.columns)
        L += [f"**{s}**", "", "| 변형 | " + " | ".join(c + (" †" if c in floors[s] else "") for c in cols) + " |", "|---|" + "---|" * len(cols)]
        L += [f"| {v} | " + " | ".join(f"{w.loc[v, c]:.3f}" for c in cols) + " |" for v in w.index]
        L.append("")
    L += ["바닥 상대 제외 (서술용, 판정 아님, 보정 없음):", "", "| 묶음 | 제외 상대 | 변형 | n | 승률 차 (95% CI) |", "|---|---|---|---|---|"]
    for s, t in nofloor.items():
        L += [f"| {s} | {', '.join(floors[s]) or '없음'} | {r.variant} | {r.n} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) |" for r in t.itertuples()]
    L += ["", "## 5. 보조 지표 (서술용)", "",
          "| 묶음 | 변형 | 승률 | Δwez [s] | V0 대비 Δwez | 실제 체력 차 [HP] | V0 대비 체력 차 | 청 하드덱 | 무접촉 | 승리 방식 (" + " / ".join(MODES) + ") |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s, t in desc.items():
        mt = main_t[s].set_index("variant")
        for v, r in t.iterrows():
            dd, dh = (f3(mt.loc[v, "d_dwez"]), f"{mt.loc[v, 'd_hp']:+.1f}") if v in mt.index else ("—", "—")
            L.append(f"| {s} | {v} | {r.win:.3f} | {r.dwez:+.2f} | {dd} | {r.hp:+.1f} | {dh} | {r.blue_hd:.3f} | {r.no_contact:.3f} | "
                     + " / ".join(str(int(r[m])) for m in MODES) + " |")
    L += ["", "## 6. 탐색 분석 (서술용, 판정 없음)", "", "### (가) 청 노드 실행 비율 (평균)", ""]
    for s, t in nf.items():
        cols = ["energy_recover", "break_defense"] + [c for c in t.columns if c not in ("energy_recover", "break_defense")]
        L += [f"**{s}**", "", "| 변형 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        L += [f"| {v} | " + " | ".join(f"{t.loc[v, c]:.3f}" for c in cols) + " |" for v in t.index]
        L.append("")
    L += ["### (나) 공격성과 생존", "", "| 묶음 | 변형 | 청 격추당함 | 청 하드덱 | hp_blue_raw 평균 | e_adv_ft 평균 |", "|---|---|---|---|---|---|"]
    for s, t in desc.items():
        L += [f"| {s} | {v} | {t.loc[v, 'blue_down']:.3f} | {t.loc[v, 'blue_hd']:.3f} | {t.loc[v, 'hp_blue']:.1f} | {t.loc[v, 'e_adv']:+.0f} |"
              for v in NODE_V]
    L += ["", "### (다) V1·V3·V6 의 V0 대비 승률 차: patched vs heldout", "", "| 변형 | 상대 | 묶음 | 승률 차 |", "|---|---|---|---|"]
    for v in ("V1", "V3", "V6"):
        for s, w in opp_w.items():
            L.append(f"| {v} | 전체 | {s} | {f3(main_t[s].set_index('variant').loc[v, 'diff'])} |")
        for s, w in opp_w.items():
            L += [f"| {v} | {c}{' †' if c in floors[s] else ''} | {s} | {f3(w.loc[v, c] - w.loc['V0', c])} |" for c in w.columns]
    L += ["", "시뮬레이션에 없는 위험 (다른 적기, 미사일, 연료, G 내성, 센서 한계) 과 모델 충실도 차이는 이 실험으로 확인할 수 없다.", "",
          "## 7. 실행 품질", "", "| 묶음 | 경기 | 계획 | 중복 | wall_clock | disqualified | code_commit | engine_sha |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {s} | {q['games']} | {q['expected']} | {q['dup']} | {q['wall_clock']} | {q['disqualified']} | {', '.join(q['code_commit'])} "
          f"| {', '.join(q['engine_sha'])} |" for s, q in qual.items()]
    L += ["", "그림: `tuning_winrate.png` (묶음별 V0 대비 승률 차, 95% CI), `tuning_nodefrac.png` (V0·V1·V3·V6 노드 실행 비율)."]
    open(os.path.join(a.out, "tuning_report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    plot_winrate(main_t, os.path.join(a.out, "tuning_winrate.png"))
    plot_nodes(nf, os.path.join(a.out, "tuning_nodefrac.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
