"""새 상대 일반화 재검증 분석 (cadet_research/PREREG_BT_ADDENDUM_GENERALIZE.md §5). games.csv 는 읽기만 한다.

  python bt/analysis/generalize.py     # → bt/out/analysis/generalize_report.md, generalize_diffs.png, generalize_outcomes.png

1차 지표 2개: 승률 (청 승), 패배율 (적 승, 무접촉 제외). V2·V3·V6 vs V0 짝 비교 (같은 기하·상대·시드): 짝 이진 차이 평균의 95% CI (t, n − 1),
McNemar 정확 검정 (양측), 지표별 Holm (가족 3). 판정은 상대 6종 전체. 나머지는 서술용.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anova import load  # noqa: E402
from confirm import CELL, holm  # noqa: E402
from io_utils import read_design, read_games  # noqa: E402
from tuning import win_test  # noqa: E402

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = {"newtypes": os.path.join(BT, "out", "bt-confirm3-newtypes", "games.csv"),
         "patched": os.path.join(BT, "out", "bt-confirm2", "games.csv"),
         "heldout": os.path.join(BT, "out", "bt-confirm2-heldout", "games.csv")}
VARIANTS = os.path.join(BT, "thetas", "generalize4.csv")
TUNED = ("V2", "V3", "V6")
ORDER = ("V0", "V2", "V3", "V6")
ALPHA, FLOOR = 0.05, 0.05
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")
SET_COLOR = {"patched": "#2a78d6", "heldout": "#eb6834", "newtypes": "#1baf7a"}
OUT_COLOR = {"win": "#2a78d6", "loss": "#eb6834", "no_contact": "#1baf7a"}


def prepare(path: str, name: dict) -> pd.DataFrame:
    d = load(path)
    d = d[d.theta_id.isin(name)].copy()
    return d.assign(v=d.theta_id.map(name), win=d.winner == "blue", loss=d.winner == "red", no_contact=d.end_reason == "no_contact",
                    hp=d.hp_blue_raw - d.hp_red_raw, blue_hd=(d.winner == "red") & (d.end_reason == "hard_deck"))


def diff(d: pd.DataFrame, v: str, ref: str, col: str) -> dict:
    """같은 셀끼리 짝지은 이진 차이. 짝이 안 맞으면 ValueError."""
    a, b = d[d.v == v].set_index(CELL), d[d.v == ref].set_index(CELL)
    if a.index.duplicated().any() or b.index.duplicated().any() or set(a.index) != set(b.index):
        raise ValueError(f"{v} 와 {ref} 의 셀이 짝이 맞지 않는다 ({len(a)}, {len(b)})")
    return win_test(a[col].values.astype(float) - b.loc[a.index, col].values.astype(float))


def primary(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ("win", "loss"):
        t = [dict(metric=col, v=v, **diff(d, v, "V0", col)) for v in TUNED]
        for r, p in zip(t, holm(np.array([x["p_mcnemar"] for x in t]))):
            r["p_holm"] = p
        rows += t
    return pd.DataFrame(rows)


def verdict(win_diff: float, win_p: float, loss_diff: float, loss_p: float) -> str:
    """계획서 §5 의 판정 문장. 적용 순서: 일반화됨 → 악화 → 생존만 일반화됨 → 일반화 안 됨."""
    win_sig, loss_sig = win_p < ALPHA, loss_p < ALPHA
    if win_sig and win_diff > 0:
        return "일반화됨"
    if (win_sig and win_diff < 0) or (loss_sig and loss_diff > 0):
        return "악화"
    if loss_sig and loss_diff < 0:
        return "생존만 일반화됨"
    return "일반화 안 됨"


def floors(d: pd.DataFrame) -> list[str]:
    w = d[d.v == "V0"].groupby("opponent").win.mean()
    return sorted(w[w < FLOOR].index)


def outcome(g: pd.DataFrame) -> pd.Series:
    return pd.Series(np.select([g.win, g.no_contact, g.loss], ["win", "no_contact", "loss"], "tie"), index=g.index)


def f3(x):
    return f"{x:+.3f}"


def ci(r):
    return f"{f3(r['diff'])} ({f3(r['ci_lo'])}, {f3(r['ci_hi'])})"


def plot_diffs(res: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, col, title in zip(axes, ("win", "loss"), ("win rate diff vs V0", "loss rate diff vs V0")):
        for k, (s, t) in enumerate(res.items()):
            g = t[t.metric == col]
            x = np.arange(len(g)) + (k - 1) * 0.22
            ax.errorbar(x, g["diff"], yerr=[g["diff"] - g.ci_lo, g.ci_hi - g["diff"]], fmt="o", ms=7, capsize=3, lw=2, color=SET_COLOR[s], label=s)
        ax.axhline(0, color="#52514e", lw=0.8)
        ax.set_xticks(np.arange(len(TUNED)), TUNED)
        ax.set_title(title + " (95% CI)", loc="left", fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_outcomes(r: pd.DataFrame, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vs = list(ORDER)
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    left = np.zeros(len(vs))
    for k in ("win", "loss", "no_contact"):
        val = r.loc[vs, k].values.astype(float)
        ax.barh(vs, val, left=left, color=OUT_COLOR[k], edgecolor="#fcfcfb", linewidth=2, height=0.7, label=k.replace("_", " "))
        for y, (x0, w) in enumerate(zip(left, val)):
            if w >= 0.08:
                ax.text(x0 + w / 2, y, f"{w:.0%}", ha="center", va="center", color="#0b0b0b" if k == "no_contact" else "white", fontsize=8)
        left += val
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of games (newtypes)")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)
    ax.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k, v in PATHS.items():
        ap.add_argument("--" + k, default=v)
    ap.add_argument("--out", default=os.path.join(BT, "out", "analysis"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    var = read_design(VARIANTS)
    name = dict(zip(var.theta_id, var.variant))
    raw = read_games(a.newtypes)
    d = prepare(a.newtypes, name)
    assert set(d.opponent_set) == {"newtypes"}, set(d.opponent_set)
    others = {s: prepare(getattr(a, s), name) for s in ("patched", "heldout")}
    res = {**{s: primary(g) for s, g in others.items()}, "newtypes": primary(d)}
    p = res["newtypes"]
    fl = floors(d)
    rates = d.groupby("v")[["win", "loss", "no_contact"]].mean()

    L = ["# 새 상대 일반화 재검증 결과 (사후 추가 실험)", "",
         "계획: `cadet_research/PREREG_BT_ADDENDUM_GENERALIZE.md` (태그 `prereg-bt-generalize-v1`). 분석 코드 `bt/analysis/generalize.py` 는 태그 커밋에 들어 있다.",
         "짝 = 같은 기하·상대·시드 (θ 당 648쌍). 패배율 = 적 승 비율 (무접촉 제외). 판정은 상대 6종 전체, 나머지는 서술용.", "",
         "## 1. 주 판정 (변형 − V0)", "", "| 변형 | 지표 | n | 차 (95% CI) | 변형만 / V0만 | McNemar p | Holm p (가족 3) | 유의 |", "|---|---|---|---|---|---|---|---|"]
    label = {"win": "승률", "loss": "패배율"}
    L += [f"| {r.v} | {label[r.metric]} | {r.n} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) | {r.b} / {r.c} | {r.p_mcnemar:.3g} | {r.p_holm:.3g} "
          f"| {'**예**' if r.p_holm < ALPHA else '아니오'} |" for r in p.itertuples()]
    L += ["", "**판정 (계획서 §5 문장):**", "", "| 변형 | 판정 |", "|---|---|"]
    idx = p.set_index(["metric", "v"])
    verdicts = {}
    for v in TUNED:
        w, l = idx.loc[("win", v)], idx.loc[("loss", v)]
        verdicts[v] = verdict(w["diff"], w.p_holm, l["diff"], l.p_holm)
        L.append(f"| {v} | **{verdicts[v]}** |")
    L += ["", "## 2. 사전 예상 vs 실제 (판정에 쓰지 않음)", "", "예상: V2·V3·V6 승률 > V0, 패배율 < V0, 이득은 patched 보다 작고 heldout 과 비슷한 크기.", "",
          "| 변형 | 승률 차 | 예상과 같은 부호 | 패배율 차 | 예상과 같은 부호 |", "|---|---|---|---|---|"]
    for v in TUNED:
        w, l = idx.loc[("win", v), "diff"], idx.loc[("loss", v), "diff"]
        L.append(f"| {v} | {f3(w)} | {'예' if w > 0 else '아니오'} | {f3(l)} | {'예' if l < 0 else '아니오'} |")
    L += ["", "## 3. 승·패·무접촉", "", "| 변형 | 승 | 패 | 무접촉 | 무접촉 차 (95% CI, V0 대비) |", "|---|---|---|---|---|"]
    for v in ORDER:
        nc = "—" if v == "V0" else ci(diff(d, v, "V0", "no_contact"))
        L.append(f"| {v} | {rates.loc[v, 'win']:.3f} | {rates.loc[v, 'loss']:.3f} | {rates.loc[v, 'no_contact']:.3f} | {nc} |")
    L += ["", "같은 셀에서 결과 전이 (행 V0 → 열 변형, 경기 수):", ""]
    base = d[d.v == "V0"].set_index(CELL)
    for v in TUNED:
        g = d[d.v == v].set_index(CELL).loc[base.index]
        x = pd.crosstab(outcome(base).rename("V0"), outcome(g).rename(v))
        L += [f"**{v}**", "", "| V0 \\ " + v + " | " + " | ".join(x.columns) + " |", "|---|" + "---|" * x.shape[1]]
        L += [f"| {i} | " + " | ".join(str(x.loc[i, c]) for c in x.columns) + " |" for i in x.index]
        L.append("")
    opp = d.groupby(["opponent", "v"])[["win", "loss", "no_contact"]].mean()
    L += ["## 4. 상대별 승 / 패 / 무접촉", "", "† = 바닥 상대 (V0 승률 < 5%). 상대당 108경기, 값 하나의 오차 대략 ±10%p.", "",
          "| 상대 | " + " | ".join(ORDER) + " |", "|---|" + "---|" * len(ORDER)]
    for o in sorted(d.opponent.unique()):
        L.append(f"| {o}{' †' if o in fl else ''} | " + " | ".join(f"{opp.loc[(o, v), 'win']:.2f} / {opp.loc[(o, v), 'loss']:.2f} / {opp.loc[(o, v), 'no_contact']:.2f}" for v in ORDER) + " |")
    L += ["", f"바닥 상대 제외 (서술용, 보정 없음): 제외 {', '.join(fl) or '없음'}", ""]
    rest = d[~d.opponent.isin(fl)]
    if rest.opponent.nunique():
        L += ["| 변형 | n | 승률 차 (95% CI) | 패배율 차 (95% CI) |", "|---|---|---|---|"]
        for v in TUNED:
            w, l = diff(rest, v, "V0", "win"), diff(rest, v, "V0", "loss")
            L.append(f"| {v} | {w['n']} | {ci(w)} | {ci(l)} |")
    L += ["", "## 5. 복잡한 튜닝이 fight_kcas 단독보다 나은가 (서술용)", "", "| 비교 | 승률 차 (95% CI) | 패배율 차 (95% CI) |", "|---|---|---|"]
    for v in ("V3", "V6"):
        L.append(f"| {v} − V2 | {ci(diff(d, v, 'V2', 'win'))} | {ci(diff(d, v, 'V2', 'loss'))} |")
    L += ["", "## 6. 보조 지표 (서술용)", "", "| 변형 | Δwez [s] | 실제 체력 차 [HP] | 청 하드덱 | e_adv_ft | 승리 방식 (" + " / ".join(MODES) + ") |", "|---|---|---|---|---|---|"]
    for v in ORDER:
        g = d[d.v == v]
        L.append(f"| {v} | {g.dwez.mean():+.2f} | {g.hp.mean():+.1f} | {g.blue_hd.mean():.3f} | {g.e_adv_ft.mean():+.0f} | " + " / ".join(str(int((g.win_mode == m).sum())) for m in MODES) + " |")
    nf = pd.DataFrame([json.loads(x) for x in d.node_frac], index=d.index).fillna(0.0).groupby(d.v).mean().loc[list(ORDER)]
    L += ["", "청 노드 실행 비율 (평균):", "", "| 변형 | " + " | ".join(nf.columns) + " |", "|---|" + "---|" * nf.shape[1]]
    L += [f"| {v} | " + " | ".join(f"{nf.loc[v, c]:.3f}" for c in nf.columns) + " |" for v in nf.index]
    L += ["", "## 7. 세 묶음 나란히 (시드와 상대가 달라 보기만 한다)", "", "| 변형 | 지표 | patched | heldout | newtypes |", "|---|---|---|---|---|"]
    for col in ("win", "loss"):
        for v in TUNED:
            cells = [ci(res[s].set_index(["metric", "v"]).loc[(col, v)]) for s in ("patched", "heldout", "newtypes")]
            L.append(f"| {v} | {label[col]} | " + " | ".join(cells) + " |")
    L += ["", "시뮬레이션에 없는 위험 (다른 적기, 미사일, 연료, G 내성, 센서 한계) 과 모델 충실도 차이는 이 실험으로 확인할 수 없다.", "", "## 8. 실행 품질", "",
          "| 경기 | 계획 | 중복 | wall_clock | disqualified | code_commit | engine_sha |", "|---|---|---|---|---|---|---|",
          f"| {len(raw)} | {4 * 648} | {int(raw.duplicated(['theta_id', *CELL]).sum())} | {int((raw.end_reason == 'wall_clock').sum())} | {int((raw.end_reason == 'disqualified').sum())} "
          f"| {', '.join(sorted(set(raw.code_commit)))} | {', '.join(sorted(set(raw.engine_sha)))} |", "",
          "그림: `generalize_diffs.png` (세 묶음의 V0 대비 승률·패배율 차, 95% CI), `generalize_outcomes.png` (newtypes 승·패·무접촉)."]
    open(os.path.join(a.out, "generalize_report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    plot_diffs(res, os.path.join(a.out, "generalize_diffs.png"))
    plot_outcomes(rates, os.path.join(a.out, "generalize_outcomes.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
