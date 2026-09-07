"""F_SPEC §3 그림 생성 — 문장별 실측 궤적 4패널 (canon 녹화 + 발화 지문 기반).

디자인 원칙(색 예산): 유채색은 이야기의 주인공에게만 —
  · 주황 = 문장이 조종한 6초(발화 창)      · 초록 = 점수차·에너지차(승부의 결과)
  · 기체 궤적은 회색조(챔피언 진회색 실선, 상대 은회색 파선) — 배경 역할
  · ★ = 발화 순간, ✕ = 격추 순간, ▲/▽ = 표시 구간 시작점(챔피언/상대)
  · 진행 방향은 15초 간격 시각 라벨 + 작은 화살표(색 그라데이션 대신)

패널: (1) 평면 궤적(발화 전후 크롭, 격추 포함 보장) (2) 고도–시간
      (3) 비에너지 E_s = h + v²/2g 양측 + 차이 es_rel  (4) 점수차 hp_lead

usage: python -m research.gen_fspec_figs   (산출: docs/figs/fspec_f{n}.png)
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.debrief.replay_debrief import parse_acmi   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON = os.path.join(ROOT, "replays", "canon", "roster_f32_final_128_0")
RULES = os.path.join(ROOT, "research", "data", "blueteam", "induced_rules_f32_slim.json")
FP = os.path.join(ROOT, "research", "campaigns", "daemon_f32", "rules_r1.fingerprint.json")
OUT = os.path.join(ROOT, "docs", "figs")
TAU = 6.0
C_ME, C_FOE, C_FIRE, C_SCORE = "#404040", "#b0b0b0", "orange", "green"


def main() -> int:
    rules = json.load(open(RULES))
    sched = json.load(open(FP))["schedule"]          # case -> [t_fire, rule_idx]
    os.makedirs(OUT, exist_ok=True)
    for i, r in enumerate(rules):
        case = next((c for c in r["covers"] if c in sched and sched[c][1] == i),
                    r["covers"][0])
        tf = sched.get(case, [None, None])[0]
        stem, side = case.split("/")
        d = parse_acmi(os.path.join(CANON, f"vs_{stem}_{side}.acmi"))
        me = d[100] if side == "blue" else d[200]
        foe = d[200] if side == "blue" else d[100]
        t_me = me["t"]

        # 격추 시각(상대 HP 0 도달) — 크롭 창이 격추를 반드시 포함하게
        kill_t = None
        n_hp = min(len(t_me), len(me["Health"]), len(foe["Health"]))
        dead = np.where(foe["Health"][:n_hp] <= 0)[0]
        if len(dead):
            kill_t = float(t_me[dead[0]])
        c0 = max(0.0, (tf or 20.0) - 15.0)
        c1 = (tf or 20.0) + 45.0
        if kill_t is not None:
            c1 = max(c1, kill_t + 5.0)
        c1 = min(float(t_me[-1]), c1)

        fig, ax = plt.subplots(2, 2, figsize=(13, 9))
        fig.suptitle(f"$f_{{{i+1}}}$  [{r['act']}]  vs {stem} ({side} seat)"
                     + (f"   fire t={tf:.1f}s + {TAU:.0f}s" if tf else ""),
                     fontsize=12)

        # (1) 평면 궤적 — 회색조 + 시각 라벨/화살표, 주황 발화 구간만 유채색
        a = ax[0][0]
        for obj, col, ls, lbl, mk in ((foe, C_FOE, "--", "opponent", "v"),
                                      (me, C_ME, "-", "champion", "^")):
            w = (obj["t"] >= c0) & (obj["t"] <= c1)
            a.plot(obj["e"][w] / 1000, obj["n"][w] / 1000, ls, color=col,
                   lw=1.6 if obj is me else 1.2, label=lbl)
            k0 = int(np.searchsorted(obj["t"], c0))
            a.plot(obj["e"][k0] / 1000, obj["n"][k0] / 1000, mk, color=col,
                   ms=11, mec="k", label=f"{lbl} start")
            for tm in np.arange(np.ceil(c0 / 15) * 15, c1, 15):
                k = int(np.searchsorted(obj["t"], tm))
                if k + 20 < len(obj["e"]):
                    a.annotate("", xy=(obj["e"][k + 20] / 1000, obj["n"][k + 20] / 1000),
                               xytext=(obj["e"][k] / 1000, obj["n"][k] / 1000),
                               arrowprops=dict(arrowstyle="->", color=col, lw=1.2))
                    if obj is me:
                        a.annotate(f"{tm:.0f}s", (obj["e"][k] / 1000, obj["n"][k] / 1000),
                                   fontsize=7, xytext=(4, 4), textcoords="offset points",
                                   color="k")
        if tf is not None:
            w = (t_me >= tf) & (t_me <= tf + TAU)
            a.plot(me["e"][w] / 1000, me["n"][w] / 1000, color=C_FIRE, lw=4.5,
                   solid_capstyle="round", label=f"$f_{{{i+1}}}$ active (6s)", zorder=5)
            k = int(np.searchsorted(t_me, tf))
            a.plot(me["e"][k] / 1000, me["n"][k] / 1000, "*", color="k", ms=16,
                   label="fire moment", zorder=6)
        if kill_t is not None and c0 <= kill_t <= c1:
            k = int(np.searchsorted(t_me, kill_t))
            a.plot(me["e"][k] / 1000, me["n"][k] / 1000, "x", color="crimson",
                   ms=13, mew=3, label="kill", zorder=6)
        a.set_xlabel("East [kft]"); a.set_ylabel("North [kft]")
        a.set_title(f"Top-down track   t = {c0:.0f}..{c1:.0f}s   (arrows = heading)")
        a.legend(fontsize=7, loc="best"); a.axis("equal"); a.grid(alpha=.3)

        # (2) 고도–시간 (회색조 + 발화 음영 + 격추 파선)
        a = ax[0][1]
        a.plot(t_me, me["alt"] / 1000, "-", color=C_ME, lw=1.6, label="champion")
        a.plot(foe["t"], foe["alt"] / 1000, "--", color=C_FOE, lw=1.2, label="opponent")
        if tf is not None:
            a.axvspan(tf, tf + TAU, color=C_FIRE, alpha=.3)
        if kill_t is not None:
            a.axvline(kill_t, color="crimson", lw=1.0, ls="--")
        a.set_xlabel("t [s]"); a.set_ylabel("Altitude [kft]")
        a.set_title("Altitude   (orange = firing,  red dashed = kill)")
        a.legend(fontsize=8); a.grid(alpha=.3)

        # (3) 비에너지 — 양측 회색조 + 차이만 초록
        a = ax[1][0]
        KT2FPS, G2 = 1.68781, 64.348
        es_me = me["alt"] + (me["CAS"] * KT2FPS) ** 2 / G2
        es_foe = foe["alt"] + (foe["CAS"] * KT2FPS) ** 2 / G2
        a.plot(t_me, es_me / 1000, "-", color=C_ME, lw=1.6, label="champion $E_s$")
        a.plot(foe["t"], es_foe / 1000, "--", color=C_FOE, lw=1.2,
               label="opponent $E_s$")
        if tf is not None:
            a.axvspan(tf, tf + TAU, color=C_FIRE, alpha=.3)
        a.set_xlabel("t [s]"); a.set_ylabel("$E_s$ [kft]")
        a.set_title("Specific energy  $E_s = h + v^2/2g$   (green = $es_{rel}$)")
        a.grid(alpha=.3); a.legend(fontsize=8, loc="upper left")
        a2 = a.twinx()
        nE = min(len(es_me), len(es_foe))
        a2.plot(t_me[:nE], (es_me[:nE] - es_foe[:nE]) / 1000, "-", color=C_SCORE,
                lw=1.6)
        a2.axhline(0, color=C_SCORE, lw=.5, ls=":")
        a2.set_ylabel("$es_{rel}$ [kft]", color=C_SCORE)
        a2.tick_params(axis="y", labelcolor=C_SCORE)

        # (4) 점수차
        a = ax[1][1]
        a.plot(t_me[:n_hp], me["Health"][:n_hp] - foe["Health"][:n_hp], "-",
               color=C_SCORE, lw=1.8)
        a.axhline(0, color="k", lw=.6)
        if tf is not None:
            a.axvspan(tf, tf + TAU, color=C_FIRE, alpha=.3)
        if kill_t is not None:
            a.axvline(kill_t, color="crimson", lw=1.0, ls="--")
        a.set_xlabel("t [s]")
        a.set_ylabel("$hp_{lead}$ = HP(me) $-$ HP(foe)")
        a.set_title("Score margin   (win = ends positive)")
        a.grid(alpha=.3)

        fig.tight_layout()
        out = os.path.join(OUT, f"fspec_f{i+1:02d}.png")
        fig.savefig(out, dpi=110)
        plt.close(fig)
        print(f"f{i+1:<2} {r['act']:<9} {case:<26} fire@{tf} → {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
