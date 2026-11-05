"""튜닝 BT 비교 사후 탐색 (0단계). 결과를 본 뒤 만들었다. 판정이 아니라 서술용이고, games.csv 는 읽기만 한다.

  python bt/analysis/stage0.py     # → bt/out/analysis/stage0_report.md, stage0_outcomes.png, stage0_range.png

(1) 승·진짜 패·무접촉 3분류. 엔진 리그 규칙 (engine/tournament.py) 은 무접촉을 쌍방 패로 센다.
(2) V6 무접촉 경기를 상대별 6개씩 뽑아 (seed 20261106) 같은 셀의 V0 와 함께 재생, 거리·속도·고도를 잰다.
    재생은 run_bt.play 를 그대로 쓰고 ACMI 기록만 켠다. CSV 와 결과가 같은지 확인한다. 결과는 bt/out/stage0/replay.json 에 둔다.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys

os.environ["CORE2_AUTO_DEBRIEF"] = "0"
HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.dirname(HERE)
sys.path[:0] = [HERE, BT]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from anova import load  # noqa: E402
from confirm import holm  # noqa: E402
from io_utils import read_design  # noqa: E402
from tuning import MAIN, SETS, VARIANTS, win_test  # noqa: E402

OUT = os.path.join(BT, "out", "analysis")
WORK = os.path.join(BT, "out", "stage0")
CACHE = os.path.join(WORK, "replay.json")
CELL = ["scenario", "opponent", "seed_salt"]
SAMPLE_OPP = ("A1_PurePursuer_00", "A2_GunTracker_00", "A3_LagAngler_00", "B1_EnergyFighter_00", "D1_Reactive_00")
N_SAMPLE, SEED = 6, 20261106
COLORS = {"win": "#2a78d6", "loss": "#eb6834", "no_contact": "#1baf7a"}
LABEL = {"win": "win", "loss": "loss", "no_contact": "no contact"}


def load_all() -> pd.DataFrame:
    var = read_design(VARIANTS)
    name = dict(zip(var.theta_id, var.variant))
    d = pd.concat([load(p) for p in SETS.values()], ignore_index=True)
    return d.assign(v=d.theta_id.map(name), win=d.winner == "blue", loss=d.winner == "red", no_contact=d.end_reason == "no_contact")


def rates(d: pd.DataFrame, by) -> pd.DataFrame:
    return d.groupby(by)[["win", "loss", "no_contact"]].mean()


def paired_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for s, g in d.groupby("opponent_set", sort=False):
        base = g[g.v == "V0"].set_index(CELL)
        for v in MAIN:
            x = g[g.v == v].set_index(CELL).loc[base.index]
            row = dict(set=s, v=v)
            for c in ("win", "loss", "no_contact"):
                r = win_test(x[c].values.astype(float) - base[c].values.astype(float))
                row.update({c: r["diff"], c + "_lo": r["ci_lo"], c + "_hi": r["ci_hi"], c + "_p": r["p_mcnemar"]})
            rows.append(row)
    t = pd.DataFrame(rows)
    t["loss_holm"] = t.groupby("set").loss_p.transform(lambda p: holm(p.values))
    return t


def outcome(g: pd.DataFrame) -> pd.Series:
    return pd.Series(np.select([g.win, g.no_contact, g.loss], ["win", "no_contact", "loss"], "tie"), index=g.index)


def transitions(d: pd.DataFrame, v: str, opponents=None) -> pd.DataFrame:
    g = d if opponents is None else d[d.opponent.isin(opponents)]
    keys = ["opponent_set", *CELL]
    a, b = (g[g.v == x].set_index(keys) for x in ("V0", v))
    b = b.loc[a.index]
    return pd.crosstab(outcome(a).rename("V0"), outcome(b).rename(v))


def pick_sample(d: pd.DataFrame) -> list[dict]:
    rng = np.random.default_rng(SEED)
    out = []
    for o in SAMPLE_OPP:
        g = d[(d.v == "V6") & (d.opponent == o) & d.no_contact].sort_values(["scenario", "seed_salt"])
        idx = rng.choice(len(g), min(N_SAMPLE, len(g)), replace=False)
        for r in g.iloc[sorted(idx)].itertuples():
            for v in ("V0", "V6"):
                out.append(dict(v=v, opponent=o, scenario=r.scenario, seed_salt=r.seed_salt, opponent_set=r.opponent_set))
    return out


def replay(args) -> dict:
    """run_bt.play 로 1경기 재생 (ACMI 만 켬) → 궤적 요약."""
    import run_bt
    from aircombat.debrief.trace import parse_trace
    from aircombat.engine.match import Match
    item, theta = args
    prefix = item["seed_salt"].rsplit("-", 1)[0]
    i = int(item["seed_salt"].rsplit("-", 1)[1])
    job = next(j for j in run_bt.build_jobs([theta], prefix, opponent_set=item["opponent_set"], nseeds=i + 1)
               if j["seed_salt"] == item["seed_salt"] and j["scenario"] == item["scenario"] and j["opponent"] == item["opponent"])
    path = os.path.join(WORK, f"{item['v']}_{item['opponent']}_{item['scenario']}_{i}.acmi")
    run_bt.Match = lambda b, r, **k: Match(b, r, **{**k, "acmi_path": path, "log_hz": 10.0})
    res = run_bt.play({**job, "engine_sha": "", "code_commit": ""})
    sides, _ = parse_trace(path)
    b, r = sides["blue"], sides["red"]
    os.remove(path)
    grid = np.arange(0.0, 301.0)
    rng_ft = np.interp(grid, b.t, b.dist, right=np.nan)
    return {**item, "winner": res["winner"], "end_reason": res["end_reason"], "hp_blue_raw": res["hp_blue_raw"], "hp_red_raw": res["hp_red_raw"],
            "wez_blue": res["wez_blue"], "wez_red": res["wez_red"], "min_range": float(np.nanmin(b.dist)), "median_range": float(np.nanmedian(b.dist)),
            "frac_6k": float(np.nanmean(b.dist < 6000)), "frac_3k": float(np.nanmean(b.dist < 3000)),
            "cas_blue": float(np.nanmean(b.cas)), "cas_red": float(np.nanmean(r.cas)),    # parse_trace 가 이미 kt
            "alt_blue": float(np.nanmean(b.alt_ft)), "alt_red": float(np.nanmean(r.alt_ft)),
            "ata_blue": float(np.nanmean(b.ata)), "ata_red": float(np.nanmean(r.ata)), "range_t": [None if np.isnan(x) else round(float(x), 0) for x in rng_ft]}


def run_replays(d: pd.DataFrame) -> pd.DataFrame:
    import run_bt
    if os.path.exists(CACHE):
        return pd.DataFrame(json.load(open(CACHE, encoding="utf-8")))
    os.makedirs(WORK, exist_ok=True)
    thetas = dict(zip(read_design(VARIANTS).variant, run_bt.read_thetas(VARIANTS)))
    items = pick_sample(d)
    with mp.Pool(5) as p:
        rows = p.map(replay, [(x, thetas[x["v"]]) for x in items], chunksize=1)
    json.dump(rows, open(CACHE, "w", encoding="utf-8"))
    return pd.DataFrame(rows)


def check_replay(d: pd.DataFrame, t: pd.DataFrame) -> int:
    """재생이 CSV 와 다른 경기 수."""
    keys = ["v", *CELL]
    m = t.merge(d[keys + ["winner", "end_reason", "wez_blue", "wez_red", "hp_blue_raw", "hp_red_raw"]], on=keys, suffixes=("", "_csv"))
    assert len(m) == len(t)
    same = (m.winner == m.winner_csv) & (m.end_reason == m.end_reason_csv) & np.isclose(m.wez_blue, m.wez_blue_csv) & np.isclose(m.wez_red, m.wez_red_csv)
    return int((~same).sum())


def plot_outcomes(r: pd.DataFrame, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vs = ["V0", "V1", "V2", "V3", "V4", "V6"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, s in zip(axes, ("patched", "heldout")):
        left = np.zeros(len(vs))
        for k in ("win", "loss", "no_contact"):
            val = np.array([r.loc[(s, v), k] for v in vs])
            ax.barh(vs, val, left=left, color=COLORS[k], edgecolor="#fcfcfb", linewidth=2, height=0.7, label=LABEL[k])
            for y, (x0, w) in enumerate(zip(left, val)):
                if w >= 0.08:
                    ax.text(x0 + w / 2, y, f"{w:.0%}", ha="center", va="center", color="white" if k != "no_contact" else "#0b0b0b", fontsize=8)
            left += val
        ax.set_title(s, loc="left", fontsize=11)
        ax.set_xlim(0, 1)
        ax.invert_yaxis() if s == "patched" else None
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(left=False)
        ax.set_xlabel("share of games")
    axes[0].legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.1), frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_range(t: pd.DataFrame, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(SAMPLE_OPP), figsize=(13, 3), sharey=True)
    col = {"V0": "#2a78d6", "V6": "#eb6834"}
    for ax, o in zip(axes, SAMPLE_OPP):
        for v in ("V0", "V6"):
            a = np.array([[np.nan if x is None else x for x in row] for row in t[(t.opponent == o) & (t.v == v)].range_t], float)
            med = np.nanmedian(a, axis=0) / 1000
            ax.plot(med, color=col[v], lw=2, label=v)
        ax.axhline(3, color="#52514e", lw=0.8, ls="--")
        ax.set_title(o.split("_")[0], loc="left", fontsize=10)
        ax.set_xlabel("time [s]")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("median range [kft]")
    axes[0].legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    d = load_all()
    os.makedirs(OUT, exist_ok=True)
    tot = rates(d, ["opponent_set", "v"])
    opp = rates(d, ["opponent_set", "opponent", "v"])
    geo = d.pivot_table(index=["opponent_set", "scenario"], columns="v", values="no_contact", aggfunc="mean")
    p = paired_table(d)
    t = run_replays(d)
    bad = check_replay(d, t)
    L = ["# 0단계: 승·패·무접촉 재분석 (사후 탐색)", "",
         "**튜닝 BT 비교 결과를 본 뒤 만든 분석이다.** 계획서의 판정을 바꾸지 않으며, 모든 p 값은 서술용이다. 데이터: `bt-confirm2` 5,184경기 (읽기만 함).", "",
         "분류: 승 = 청 승, 패 = 적 승, 무접촉 = 300 s 동안 양쪽 무피해. 엔진 리그 규칙 (`engine/tournament.py`) 은 무접촉을 **쌍방 패 (0점)** 로 센다.",
         f"체력 동률 무승부는 전체 {int(((d.winner == 'draw') & ~d.no_contact).sum())}경기로, 위 분류 어디에도 넣지 않았다.", "", "## 1. 변형별 비율", "",
         "| 묶음 | 변형 | 승 | 패 | 무접촉 |", "|---|---|---|---|---|"]
    L += [f"| {s} | {v} | {r.win:.3f} | {r.loss:.3f} | {r.no_contact:.3f} |" for (s, v), r in tot.loc[["patched", "heldout"]].iterrows()]
    L += ["", "## 2. V0 대비 짝 차이 (95% CI)", "", "패 McNemar p 의 Holm 보정은 묶음별 가족 5 (서술용).", "",
          "| 묶음 | 변형 | 승 차 | 패 차 | 패 Holm p | 무접촉 차 |", "|---|---|---|---|---|---|"]
    L += [f"| {r.set} | {r.v} | {r.win:+.3f} ({r.win_lo:+.3f}, {r.win_hi:+.3f}) | {r.loss:+.3f} ({r.loss_lo:+.3f}, {r.loss_hi:+.3f}) | {r.loss_holm:.3g} "
          f"| {r.no_contact:+.3f} ({r.no_contact_lo:+.3f}, {r.no_contact_hi:+.3f}) |" for r in p.itertuples()]
    L += ["", "## 3. 같은 셀에서 결과가 어떻게 바뀌었나 (행 V0 → 열 변형, 경기 수)", ""]
    for title, v, o in (("V6, 전체", "V6", None), ("V2, 전체", "V2", None), ("V6, A3_LagAngler", "V6", ["A3_LagAngler_00"]), ("V6, B1_EnergyFighter", "V6", ["B1_EnergyFighter_00"])):
        x = transitions(d, v, o)
        L += [f"**{title}**", "", "| V0 \\ " + v + " | " + " | ".join(x.columns) + " |", "|---|" + "---|" * x.shape[1]]
        L += [f"| {i} | " + " | ".join(str(x.loc[i, c]) for c in x.columns) + " |" for i in x.index]
        L.append("")
    L += ["## 4. 상대별 승 / 패 / 무접촉 (상대당 108경기, 값 하나의 오차 대략 ±10%p)", "", "| 묶음 | 상대 | " + " | ".join(("V0", "V1", "V2", "V3", "V4", "V6")) + " |", "|---|---|---|---|---|---|---|---|"]
    for (s, o), g in opp.groupby(level=[0, 1], sort=False):
        L.append(f"| {s} | {o} | " + " | ".join(f"{g.loc[(s, o, v), 'win']:.2f} / {g.loc[(s, o, v), 'loss']:.2f} / {g.loc[(s, o, v), 'no_contact']:.2f}" for v in ("V0", "V1", "V2", "V3", "V4", "V6")) + " |")
    L += ["", "## 5. 시작 기하별 무접촉 비율", "", "| 묶음 | 기하 | " + " | ".join(geo.columns) + " |", "|---|---|" + "---|" * geo.shape[1]]
    L += [f"| {s} | {g} | " + " | ".join(f"{r[c]:.3f}" for c in geo.columns) + " |" for (s, g), r in geo.iterrows()]
    L += ["", "## 6. 무접촉 경기의 노드 실행 비율 (V6 무접촉, 상대별 평균)", "", "| 상대 | 경기 | 청 상위 3 | 적 상위 3 |", "|---|---|---|---|"]
    nc = d[(d.v == "V6") & d.no_contact]
    for o, g in nc.groupby("opponent"):
        tops = []
        for col in ("node_frac", "node_frac_red"):
            m = pd.DataFrame([json.loads(x) for x in g[col]]).fillna(0).mean().sort_values(ascending=False).head(3)
            tops.append(", ".join(f"{k} {w:.2f}" for k, w in m.items()))
        L.append(f"| {o} | {len(g)} | {tops[0]} | {tops[1]} |")
    L += ["", "## 7. 표본 재생 (V6 무접촉 + 같은 셀의 V0)", "",
          f"상대별 최대 {N_SAMPLE}경기를 seed {SEED} 로 뽑았다. 재생 {len(t)}경기 중 CSV 와 결과가 다른 경기: **{bad}**.", "",
          "| 상대 | 변형 | 경기 | 종료 사유 | 최소 거리 [ft] | 중앙 거리 [ft] | 6,000 ft 안 시간 | 3,000 ft 안 시간 | 청 / 적 ATA [deg] | 청 / 적 CAS [kt] | 청 / 적 고도 [ft] |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (o, v), g in t.groupby(["opponent", "v"]):
        res = g.end_reason.value_counts().to_dict()
        L.append(f"| {o} | {v} | {len(g)} | {res} | {g.min_range.median():.0f} | {g.median_range.median():.0f} | {g.frac_6k.mean():.3f} | {g.frac_3k.mean():.3f} | {g.ata_blue.mean():.0f} / {g.ata_red.mean():.0f} "
                 f"| {g.cas_blue.mean():.0f} / {g.cas_red.mean():.0f} | {g.alt_blue.mean():.0f} / {g.alt_red.mean():.0f} |")
    L += ["", "표본은 V6 이 무접촉인 경기만 골랐으므로 V6 행은 결과로 선택된 값이고, V0 행은 같은 셀의 경기 (결과 무관) 다. 두 행의 차이를 V6 전체의 효과로 읽으면 안 된다. 상대별 6경기뿐이라 경향만 본다.", "",
          "## 8. 읽는 법 (사후 해석, 가설)", "",
          "- 튜닝의 이득은 승리 증가와 패배 감소로 나뉜다. V6 은 patched 에서 패 −0.438 중 대부분이 승 (+0.361) 으로 갔고, heldout 에서는 패 −0.201 중 승 +0.095, 무접촉 +0.106 으로 절반가량이 무접촉으로 갔다.",
          "- 무접촉은 도주가 아니다. 표본 V6 무접촉 경기는 전체 시간의 86–99% 를 6,000 ft 안에서, 17–28% 를 3,000 ft 안에서 보냈다. 그런데도 WEZ 시간은 양쪽 0 이고 평균 ATA 는 청 68–82°, 적 71–87° 다. 가까이서 돌지만 기수를 맞추지 못하는 교착으로 보인다.",
          "- 리그 규칙으로는 무접촉도 패이므로 승률 1차 지표와 맞다. 승률 차는 득점, 패 차는 생존을 말하며 둘을 나눠 봐야 한다.",
          "- 교착의 원인은 이 분석으로 확정하지 못한다. 재생에서는 거리 변동 폭이 V0 보다 작은 상대가 많았으나 (A1·A2·A3) 표본이 작고 선택 편향이 있다.",
          "", "그림: `stage0_outcomes.png` (승·패·무접촉), `stage0_range.png` (표본 경기의 시간별 중앙 거리, 점선 = 3,000 ft)."]
    open(os.path.join(OUT, "stage0_report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
    plot_outcomes(tot, os.path.join(OUT, "stage0_outcomes.png"))
    plot_range(t, os.path.join(OUT, "stage0_range.png"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
