"""넓은 상대 일반화 분석 (cadet_research/PREREG_BT_ADDENDUM_WIDE.md §5). games.csv 는 읽기만 한다.

  python bt/analysis/wide.py     # → bt/out/analysis/wide_report.md, wide_opponents.png

판정 단위는 상대다. 상대 o 마다 d_o = 같은 셀 (기하·시드) 끼리 짝지은 (변형 − V0) 이진 차이의 평균. 1차 지표 2개 (승률, 패배율).
V2·V3·V6 각각 d_o 의 상대 간 평균에 대한 t 검정 (자유도 상대 수 − 1, 양측), 95% CI, 지표별 Holm (가족 3). 판정 문장은 ⑨ 와 같다.
나머지 (변종·새 유형 나눠 보기, 청과 비슷한 상대·바닥 상대 제외, 한 상대씩 빼기, 경기 단위 McNemar, 앞선 묶음과 나란히) 는 서술용.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from confirm import holm  # noqa: E402
from generalize import ORDER, TUNED, ci, diff, f3, outcome, prepare, verdict  # noqa: E402
from io_utils import read_design, read_games  # noqa: E402

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(BT, "out", "bt-confirm5-wide", "games.csv")
EARLIER = {"patched": os.path.join(BT, "out", "bt-confirm2", "games.csv"),
           "heldout": os.path.join(BT, "out", "bt-confirm2-heldout", "games.csv"),
           "newtypes": os.path.join(BT, "out", "bt-confirm3-newtypes", "games.csv")}
MANIFEST = os.path.join(BT, "opponents_wide", "manifest.csv")
VARIANTS = os.path.join(BT, "thetas", "generalize4.csv")
CELL = ["scenario", "seed_salt"]
ALPHA, FLOOR, BLUE_LIKE = 0.05, 0.05, 4
LABEL = {"win": "승률", "loss": "패배율"}


def per_opponent(d: pd.DataFrame, v: str, col: str) -> pd.Series:
    """상대마다 d_o = mean(변형 − V0), 같은 기하·시드끼리 짝."""
    out = {}
    for o, g in d.groupby("opponent"):
        a, b = g[g.v == v].set_index(CELL)[col], g[g.v == "V0"].set_index(CELL)[col]
        if a.index.duplicated().any() or set(a.index) != set(b.index):
            raise ValueError(f"{o}: {v} 와 V0 의 셀이 짝이 맞지 않는다")
        out[o] = float((a.astype(float) - b.loc[a.index].astype(float)).mean())
    return pd.Series(out)


def t_mean(x: np.ndarray) -> dict:
    n, m = len(x), float(np.mean(x))
    se = float(np.std(x, ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    if not se > 0:
        return dict(n=n, diff=m, ci_lo=m, ci_hi=m, p=1.0 if m == 0 else 0.0, pos=int((x > 0).sum()), neg=int((x < 0).sum()))
    tq = stats.t.ppf(0.975, n - 1)
    return dict(n=n, diff=m, ci_lo=m - tq * se, ci_hi=m + tq * se, p=float(2 * stats.t.sf(abs(m) / se, n - 1)),
                pos=int((x > 0).sum()), neg=int((x < 0).sum()))


def primary(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ("win", "loss"):
        t = [dict(metric=col, v=v, **t_mean(per_opponent(d, v, col).values)) for v in TUNED]
        for r, p in zip(t, holm(np.array([x["p"] for x in t]))):
            r["p_holm"] = p
        rows += t
    return pd.DataFrame(rows)


def subset_line(d: pd.DataFrame, keep, v: str) -> str:
    g = d[d.opponent.isin(keep)]
    if g.opponent.nunique() < 2:
        return f"| {v} | {g.opponent.nunique()} | — | — |"
    w, l = (t_mean(per_opponent(g, v, c).values) for c in ("win", "loss"))
    return f"| {v} | {w['n']} | {ci(w)} | {ci(l)} |"


def plot(d: pd.DataFrame, kinds: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    col_of = {"near": "#2a78d6", "far": "#eb6834"}
    for ax, col in zip(axes, ("win", "loss")):
        for k, v in enumerate(TUNED):
            s = per_opponent(d, v, col)
            jitter = np.linspace(-0.18, 0.18, len(s))
            for (o, y), j in zip(s.sort_values().items(), jitter):
                ax.plot(k + j, y, "o", ms=6, color=col_of[kinds.get(o, "far")], alpha=0.85)
            ax.plot([k - 0.25, k + 0.25], [s.mean()] * 2, color="#0b0b0b", lw=2)
        ax.axhline(0, color="#52514e", lw=0.8)
        ax.set_xticks(range(len(TUNED)), TUNED)
        ax.set_title(f"{'win' if col == 'win' else 'loss'} rate diff vs V0, per opponent", loc="left", fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
    from matplotlib.lines import Line2D
    axes[0].legend([Line2D([], [], marker="o", ls="", color=c) for c in col_of.values()] + [Line2D([], [], color="#0b0b0b", lw=2)],
                   ["near (variant)", "far (new type)", "mean"], frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", default=GAMES)
    ap.add_argument("--manifest", default=MANIFEST)
    for k, v in EARLIER.items():
        ap.add_argument("--" + k, default=v)
    ap.add_argument("--out", default=os.path.join(BT, "out", "analysis"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    var = read_design(VARIANTS)
    name = dict(zip(var.theta_id, var.variant))
    raw = read_games(a.games)
    d = prepare(a.games, name)
    assert set(d.opponent_set) == {"wide"}, set(d.opponent_set)
    man = {r["name"]: r for r in csv.DictReader(open(a.manifest, encoding="utf-8"))}
    opps = sorted(d.opponent.unique())
    kinds = {o: man[o]["kind"] for o in opps}
    p = primary(d)
    idx = p.set_index(["metric", "v"])
    v0win = d[d.v == "V0"].groupby("opponent").win.mean()
    floors = sorted(v0win[v0win < FLOOR].index)
    blue_like = sorted(o for o in opps if int(man[o]["blue_overlap"]) >= BLUE_LIKE)

    L = ["# 넓은 상대 일반화 결과 (사후 추가 실험)", "",
         "계획: `cadet_research/PREREG_BT_ADDENDUM_WIDE.md` (태그 `prereg-bt-wide-v1`). 분석 코드 `bt/analysis/wide.py` 는 태그 커밋에 들어 있다.",
         f"상대 {len(opps)}종 (변종 {sum(k == 'near' for k in kinds.values())}, 새 유형 {sum(k == 'far' for k in kinds.values())}), 상대당 θ 마다 {len(d) // (4 * len(opps))}경기.",
         "판정 단위 = 상대 (상대마다 V0 대비 짝 차이 평균을 구한 뒤 상대 간 평균을 t 검정). 패배율 = 적 승 비율 (무접촉 제외).", "",
         "## 1. 주 판정 (상대 단위, 변형 − V0)", "",
         "| 변형 | 지표 | 상대 수 | 평균 차 (95% CI) | 좋아진 상대 / 나빠진 상대 | p | Holm p (가족 3) | 유의 |", "|---|---|---|---|---|---|---|---|"]
    for r in p.itertuples():
        good, bad = (r.pos, r.neg) if r.metric == "win" else (r.neg, r.pos)
        L.append(f"| {r.v} | {LABEL[r.metric]} | {r.n} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) | {good} / {bad} | {r.p:.3g} | {r.p_holm:.3g} "
                 f"| {'**예**' if r.p_holm < ALPHA else '아니오'} |")
    L += ["", "**판정 (계획서 §5 문장):**", "", "| 변형 | 판정 |", "|---|---|"]
    for v in TUNED:
        w, l = idx.loc[("win", v)], idx.loc[("loss", v)]
        L.append(f"| {v} | **{verdict(w['diff'], w.p_holm, l['diff'], l.p_holm)}** |")

    L += ["", "## 2. 나눠 보기 (서술용, 보정 없음, 상대 단위 평균 차 95% CI)", ""]
    groups = [("변종 (near)", [o for o in opps if kinds[o] == "near"]), ("새 유형 (far)", [o for o in opps if kinds[o] == "far"]),
              (f"청과 비슷한 상대 제외 (노드 이름 겹침 ≥ {BLUE_LIKE}: {', '.join(blue_like) or '없음'})", [o for o in opps if o not in blue_like]),
              (f"바닥 상대 제외 (V0 승률 < {FLOOR:.0%}: {', '.join(floors) or '없음'})", [o for o in opps if o not in floors])]
    for title, keep in groups:
        L += [f"**{title}**", "", "| 변형 | 상대 수 | 승률 차 | 패배율 차 |", "|---|---|---|---|"]
        L += [subset_line(d, keep, v) for v in TUNED]
        L.append("")
    L += ["## 3. 한 상대에 기대는가 (서술용)", "", "상대를 하나씩 빼고 다시 구한 평균 차의 최소·최대. 둘의 부호가 같으면 한 상대가 결론을 뒤집지 못한다.", "",
          "| 변형 | 지표 | 최소 (뺀 상대) | 최대 (뺀 상대) |", "|---|---|---|---|"]
    for col in ("win", "loss"):
        for v in TUNED:
            s = per_opponent(d, v, col)
            loo = pd.Series({o: s.drop(o).mean() for o in s.index})
            L.append(f"| {v} | {LABEL[col]} | {f3(loo.min())} ({loo.idxmin()}) | {f3(loo.max())} ({loo.idxmax()}) |")
    L += ["", "## 4. 상대별 결과 (서술용, 상대당 θ 마다 24경기)", "",
          "| 상대 | 종류 | V0 승 / 패 / 무접촉 | " + " | ".join(f"{v} 승률 차 / 패배율 차" for v in TUNED) + " |", "|---|---|---|" + "---|" * len(TUNED)]
    pw = {v: per_opponent(d, v, "win") for v in TUNED}
    pl = {v: per_opponent(d, v, "loss") for v in TUNED}
    for o in opps:
        g = d[(d.v == "V0") & (d.opponent == o)]
        L.append(f"| {o}{' †' if o in floors else ''} | {'변종' if kinds[o] == 'near' else '새 유형'} | {g.win.mean():.2f} / {g.loss.mean():.2f} / {g.no_contact.mean():.2f} | "
                 + " | ".join(f"{f3(pw[v][o])} / {f3(pl[v][o])}" for v in TUNED) + " |")
    L += ["", "† = 바닥 상대.", "", "## 5. 경기 단위로 본 결과 (서술용, ⑨ 와 같은 방식, 보정 없음)", "",
          "| 변형 | 승률 차 (95% CI) | McNemar p | 패배율 차 (95% CI) | McNemar p | 무접촉 차 |", "|---|---|---|---|---|---|"]
    for v in TUNED:
        w, l, n = (diff(d, v, "V0", c) for c in ("win", "loss", "no_contact"))
        L.append(f"| {v} | {ci(w)} | {w['p_mcnemar']:.3g} | {ci(l)} | {l['p_mcnemar']:.3g} | {ci(n)} |")
    L += ["", "## 6. 상대 묶음 나란히 (서술용, 상대 단위 평균 차, 시드와 상대가 달라 보기만 한다)", "",
          "| 변형 | 지표 | patched (4종) | heldout (4종) | newtypes (6종) | wide (이번) |", "|---|---|---|---|---|---|"]
    earlier = {}
    for k in EARLIER:
        path = getattr(a, k)
        earlier[k] = prepare(path, name) if os.path.exists(path) else None
    for col in ("win", "loss"):
        for v in TUNED:
            cells = []
            for k in EARLIER:
                e = earlier[k]
                cells.append("파일 없음" if e is None else ci(t_mean(per_opponent(e, v, col).values)))
            cells.append(ci(idx.loc[(col, v)]))
            L.append(f"| {v} | {LABEL[col]} | " + " | ".join(cells) + " |")
    L += ["", "## 7. 승·패·무접촉과 결과 전이 (서술용)", "", "| 변형 | 승 | 패 | 무접촉 |", "|---|---|---|---|"]
    r = d.groupby("v")[["win", "loss", "no_contact"]].mean()
    L += [f"| {v} | {r.loc[v, 'win']:.3f} | {r.loc[v, 'loss']:.3f} | {r.loc[v, 'no_contact']:.3f} |" for v in ORDER]
    keys = ["opponent", *CELL]
    base = d[d.v == "V0"].set_index(keys)
    for v in TUNED:
        g = d[d.v == v].set_index(keys).loc[base.index]
        x = pd.crosstab(outcome(base).rename("V0"), outcome(g).rename(v))
        L += ["", f"**V0 → {v}** (경기 수)", "", "| V0 \\ " + v + " | " + " | ".join(x.columns) + " |", "|---|" + "---|" * x.shape[1]]
        L += [f"| {i} | " + " | ".join(str(x.loc[i, c]) for c in x.columns) + " |" for i in x.index]
    plan = 4 * len(opps) * 24
    L += ["", "시뮬레이션에 없는 위험 (다른 적기, 미사일, 연료, G 내성, 센서 한계) 과 모델 충실도 차이는 이 실험으로 확인할 수 없다.", "",
          "## 8. 실행 품질", "", "| 경기 | 계획 | 중복 | wall_clock | disqualified | code_commit | engine_sha |", "|---|---|---|---|---|---|---|",
          f"| {len(raw)} | {plan} | {int(raw.duplicated(['theta_id', 'opponent', *CELL]).sum())} | {int((raw.end_reason == 'wall_clock').sum())} "
          f"| {int((raw.end_reason == 'disqualified').sum())} | {', '.join(sorted(set(raw.code_commit)))} | {', '.join(sorted(set(raw.engine_sha)))} |", "",
          "그림: `wide_opponents.png` (상대별 V0 대비 차, 가로선 = 평균)."]
    open(os.path.join(a.out, "wide_report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    plot(d, kinds, os.path.join(a.out, "wide_opponents.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
