"""V1 분해 분석 (cadet_research/PREREG_BT_ADDENDUM_V1SPLIT.md §5). games.csv 는 읽기만 한다.

  python bt/analysis/v1split.py     # → bt/out/analysis/v1split_report.md, v1split_diffs.png

묶음 (patched, heldout) 마다 V1a (fight_kcas 325 만), V1b (threat_aspect_deg 120 만), V1 (둘 다) 을 V0 와 짝 비교한다 (같은 기하·상대·시드).
1차 지표 2개 (승률, 패배율 = 적 승 비율), 짝 이진 차이 평균의 95% CI (t, n − 1), McNemar 정확 검정 (양측), 묶음·지표별 Holm (가족 3).
나머지 (상호작용, 이전 실행과의 비교, 상대별, 노드 비율) 는 서술용.
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
from generalize import ci, diff, f3  # noqa: E402
from io_utils import read_design, read_games  # noqa: E402
from tuning import win_test  # noqa: E402

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = {"patched": os.path.join(BT, "out", "bt-confirm4", "games.csv"),
         "heldout": os.path.join(BT, "out", "bt-confirm4-heldout", "games.csv")}
EARLIER = {"patched": os.path.join(BT, "out", "bt-confirm2", "games.csv"),
           "heldout": os.path.join(BT, "out", "bt-confirm2-heldout", "games.csv")}
VARIANTS = os.path.join(BT, "thetas", "v1split4.csv")
TESTED = ("V1a", "V1b", "V1")
ORDER = ("V0", "V1a", "V1b", "V1")
ALPHA = 0.05
LABEL = {"win": "승률", "loss": "패배율"}
SET_COLOR = {"patched": "#2a78d6", "heldout": "#eb6834"}


def prepare(path: str, name: dict) -> pd.DataFrame:
    d = load(path)
    d = d[d.theta_id.isin(name)].copy()
    return d.assign(v=d.theta_id.map(name), win=d.winner == "blue", loss=d.winner == "red", no_contact=d.end_reason == "no_contact")


def primary(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ("win", "loss"):
        t = [dict(metric=col, v=v, **diff(d, v, "V0", col)) for v in TESTED]
        for r, p in zip(t, holm(np.array([x["p_mcnemar"] for x in t]))):
            r["p_holm"] = p
        rows += t
    return pd.DataFrame(rows)


def verdict(win_diff: float, win_p: float, loss_diff: float, loss_p: float) -> str:
    """계획서 §5 의 판정 문장."""
    worse = (win_p < ALPHA and win_diff < 0) or (loss_p < ALPHA and loss_diff > 0)
    better = (win_p < ALPHA and win_diff > 0) or (loss_p < ALPHA and loss_diff < 0)
    if worse and better:
        return "엇갈림"
    return "나빠짐" if worse else "좋아짐" if better else "차이 확인 못 함"


def interaction(d: pd.DataFrame, col: str) -> dict:
    """셀마다 (V1 − V0) − (V1a − V0) − (V1b − V0) = V1 − V1a − V1b + V0. 0 이면 두 변경의 효과가 더해진다."""
    s = {v: d[d.v == v].set_index(CELL)[col].astype(float) for v in ORDER}
    idx = s["V0"].index
    x = s["V1"].loc[idx].values - s["V1a"].loc[idx].values - s["V1b"].loc[idx].values + s["V0"].values
    return win_test(x)


def plot(res: dict, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, col in zip(axes, ("win", "loss")):
        for k, (s, t) in enumerate(res.items()):
            g = t[t.metric == col]
            x = np.arange(len(g)) + (k - 0.5) * 0.25
            ax.errorbar(x, g["diff"], yerr=[g["diff"] - g.ci_lo, g.ci_hi - g["diff"]], fmt="o", ms=7, capsize=3, lw=2, color=SET_COLOR[s], label=s)
        ax.axhline(0, color="#52514e", lw=0.8)
        ax.set_xticks(np.arange(len(TESTED)), TESTED)
        ax.set_title(f"{'win' if col == 'win' else 'loss'} rate diff vs V0 (95% CI)", loc="left", fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k, v in PATHS.items():
        ap.add_argument("--" + k, default=v)
        ap.add_argument(f"--earlier-{k}", default=EARLIER[k])
    ap.add_argument("--out", default=os.path.join(BT, "out", "analysis"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    var = read_design(VARIANTS)
    name = dict(zip(var.theta_id, var.variant))
    data, raw, res = {}, {}, {}
    for s in PATHS:
        p = getattr(a, s)
        raw[s] = read_games(p)
        data[s] = prepare(p, name)
        assert set(data[s].opponent_set) == {s}, (s, set(data[s].opponent_set))
        res[s] = primary(data[s])

    L = ["# V1 분해 결과 (사후 추가 실험)", "",
         "계획: `cadet_research/PREREG_BT_ADDENDUM_V1SPLIT.md` (태그 `prereg-bt-v1split-v1`). 분석 코드 `bt/analysis/v1split.py` 는 태그 커밋에 들어 있다.",
         "V1a = V0 + fight_kcas 325, V1b = V0 + threat_aspect_deg 120, V1 = 둘 다. 짝 = 같은 기하·상대·시드 (묶음당 432쌍). 패배율 = 적 승 비율 (무접촉 제외).", "",
         "## 1. 주 판정 (변형 − V0)", "", "| 묶음 | 변형 | 지표 | 차 (95% CI) | 변형만 / V0만 | McNemar p | Holm p (가족 3) | 유의 |", "|---|---|---|---|---|---|---|---|"]
    for s, t in res.items():
        L += [f"| {s} | {r.v} | {LABEL[r.metric]} | {f3(r.diff)} ({f3(r.ci_lo)}, {f3(r.ci_hi)}) | {r.b} / {r.c} | {r.p_mcnemar:.3g} | {r.p_holm:.3g} "
              f"| {'**예**' if r.p_holm < ALPHA else '아니오'} |" for r in t.itertuples()]
    L += ["", "**판정 (계획서 §5 문장):**", "", "| 묶음 | 변형 | 판정 |", "|---|---|---|"]
    for s, t in res.items():
        idx = t.set_index(["metric", "v"])
        for v in TESTED:
            w, l = idx.loc[("win", v)], idx.loc[("loss", v)]
            L.append(f"| {s} | {v} | **{verdict(w['diff'], w.p_holm, l['diff'], l.p_holm)}** |")
    L += ["", "## 2. 두 변경의 효과가 더해지는가 (서술용)", "",
          "셀마다 V1 − V1a − V1b + V0 의 평균. 0 에 가까우면 V1 의 효과 ≈ V1a 효과 + V1b 효과.", "",
          "| 묶음 | 지표 | 상호작용 (95% CI) |", "|---|---|---|"]
    for s, d in data.items():
        for col in ("win", "loss"):
            L.append(f"| {s} | {LABEL[col]} | {ci(interaction(d, col))} |")
    L += ["", "## 3. 승·패·무접촉과 노드 실행 비율 (서술용)", "",
          "| 묶음 | 변형 | 승 | 패 | 무접촉 | break_defense | energy_recover |", "|---|---|---|---|---|---|---|"]
    for s, d in data.items():
        nf = pd.DataFrame([json.loads(x) for x in d.node_frac], index=d.index).fillna(0.0).groupby(d.v).mean()
        r = d.groupby("v")[["win", "loss", "no_contact"]].mean()
        for v in ORDER:
            L.append(f"| {s} | {v} | {r.loc[v, 'win']:.3f} | {r.loc[v, 'loss']:.3f} | {r.loc[v, 'no_contact']:.3f} "
                     f"| {nf.loc[v].get('break_defense', 0.0):.3f} | {nf.loc[v].get('energy_recover', 0.0):.3f} |")
    L += ["", "## 4. 상대별 승률 (서술용, 상대당 108경기)", ""]
    for s, d in data.items():
        w = d.pivot_table(index="v", columns="opponent", values="win", aggfunc="mean").loc[list(ORDER)]
        L += [f"**{s}**", "", "| 변형 | " + " | ".join(w.columns) + " |", "|---|" + "---|" * w.shape[1]]
        L += [f"| {v} | " + " | ".join(f"{w.loc[v, c]:.3f}" for c in w.columns) + " |" for v in w.index]
        L.append("")
    L += ["## 5. 이전 실행 (bt-confirm2, 다른 시드) 의 V1 − V0 와 나란히 (서술용)", "", "| 묶음 | 지표 | 이번 (bt-confirm4) | 이전 (bt-confirm2) |", "|---|---|---|---|"]
    for s, d in data.items():
        p = getattr(a, f"earlier_{s.replace('-', '_')}")
        prev = prepare(p, name) if os.path.exists(p) else None
        for col in ("win", "loss"):
            now = res[s].set_index(["metric", "v"]).loc[(col, "V1")]
            before = ci(diff(prev, "V1", "V0", col)) if prev is not None else "파일 없음"
            L.append(f"| {s} | {LABEL[col]} | {ci(now)} | {before} |")
    L += ["", "## 6. 실행 품질", "", "| 묶음 | 경기 | 계획 | 중복 | wall_clock | disqualified | code_commit | engine_sha |", "|---|---|---|---|---|---|---|---|"]
    for s, r in raw.items():
        L.append(f"| {s} | {len(r)} | {4 * 432} | {int(r.duplicated(['theta_id', *CELL]).sum())} | {int((r.end_reason == 'wall_clock').sum())} "
                 f"| {int((r.end_reason == 'disqualified').sum())} | {', '.join(sorted(set(r.code_commit)))} | {', '.join(sorted(set(r.engine_sha)))} |")
    L += ["", "V1 은 교범 수치를 BT 문턱값으로 옮긴 한 가지 방식이다. 시뮬레이션에 없는 위험과 모델 충실도 차이는 이 실험으로 확인할 수 없다.", "",
          "그림: `v1split_diffs.png` (묶음별 V0 대비 승률·패배율 차, 95% CI)."]
    open(os.path.join(a.out, "v1split_report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    plot(res, os.path.join(a.out, "v1split_diffs.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
