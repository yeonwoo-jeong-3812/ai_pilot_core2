"""예비 실험(관문 2) 보고서. 규칙은 bt/analysis/pilot_rules.md (실행 전에 커밋). games.csv 는 읽기만 한다.

  python bt/analysis/pilot.py        # bt/out/bt-pilot/games_original.csv (원본 상대) → bt/out/pilot_report.md
analyze() 는 bt/analysis/pilot2.py (보정 상대 재예비 실험) 에서도 쓴다.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter

import numpy as np

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
from run_bt import OPPONENTS, SCENARIOS, win_mode  # noqa: E402

GAMES = os.path.join(BT, "out", "bt-pilot", "games_original.csv")   # 원본 상대 예비 실험 (보정 상대 도입 때 이름만 바꿈)
THETAS = os.path.join(BT, "thetas", "pilot_lhs50.csv")
REPORT = os.path.join(BT, "out", "pilot_report.md")
N_PLANNED, B, SEED = 2400, 2000, 20261102
METRICS = {"win": "승률", "wezd": "wez 차 [s]"}
NODE = {"merge_range_ft": "break_defense", "threat_aspect_deg": "break_defense", "break_g_burst": "break_defense",
        "gun_range_ft": "gun_track", "gun_ata_deg": "gun_track", "fight_kcas": "energy_recover",
        "energy_min_ft": "press_offense", "lead_time_s": "press_offense", "closing_min_fps": "yoyo_pull_up",
        "floor_ft": "recover_altitude"}
MODES = ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other")


def metric(r, m):
    return float(r["winner"] == "blue") if m == "win" else float(r["wez_blue"]) - float(r["wez_red"])


def signal(groups: list[np.ndarray]):
    """(V, N, R). groups = θ 별 경기 값 배열."""
    means = np.array([g.mean() for g in groups])
    noise = float(np.mean([g.var(ddof=1) / len(g) for g in groups]))
    v = float(means.var(ddof=1)) - noise
    return v, noise, v / noise


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def analyze(games: str, report: str, title: str, notes: list[str]) -> dict:
    """규칙 (1)~(5) 보고서를 report 에 쓰고 비교용 수치를 돌려준다."""
    with open(games, encoding="utf-8", newline="") as f:
        allrows = list(csv.DictReader(f))
    rows = [r for r in allrows if r["end_reason"] != "wall_clock"]
    with open(THETAS, encoding="utf-8", newline="") as f:
        thetas = {mt.theta_id(t): mt.normalize(t) for t in csv.DictReader(f)}
    tids = [t for t in thetas if any(r["theta_id"] == t for r in rows)]
    by = {t: [r for r in rows if r["theta_id"] == t] for t in tids}
    L = [f"# {title}", "",
         f"규칙: `bt/analysis/pilot_rules.md` (실행 전 커밋). θ {len(tids)}개, 분석 대상 {len(rows)}경기 "
         f"(기록 {len(allrows)} / 계획 {N_PLANNED}). 시드 bt-pilot.", ""]

    # (1) θ 신호
    L += ["## (1) θ 신호", "",
          "V = var(θ 평균) − N, N = mean(경기 간 분산 / n), R = V / N. CI = θ 단위 군집 부트스트랩 "
          f"{B}회 (seed {SEED}) 백분위 95%.", "",
          "| 지표 | var(θ 평균) | 잡음 몫 N | θ 분산 V (95% CI) | 비율 R = V/N (95% CI) |", "|---|---|---|---|---|"]
    rng = np.random.default_rng(SEED)
    res = {}
    for m, name in METRICS.items():
        groups = [np.array([metric(r, m) for r in by[t]]) for t in tids]
        v, n, r = signal(groups)
        boot = np.array([signal([groups[i] for i in rng.integers(0, len(groups), len(groups))]) for _ in range(B)])
        vlo, vhi = np.percentile(boot[:, 0], [2.5, 97.5])
        rlo, rhi = np.percentile(boot[:, 2], [2.5, 97.5])
        res[m] = dict(v=v, n=n, r=r, vlo=vlo, vhi=vhi)
        L.append(f"| {name} | {v + n:.4g} | {n:.4g} | {v:.4g} ({vlo:.4g}, {vhi:.4g}) | {r:.2f} ({rlo:.2f}, {rhi:.2f}) |")

    # (2) 1차 지표
    rw, rz = res["win"]["r"], res["wezd"]["r"]
    if rz <= 0 and rw <= 0:
        primary, why = "wezd", "두 지표 모두 R ≤ 0 → wez 차, 관문 2 불통과"
    elif rz <= 0:
        primary, why = "win", "wez 차 R ≤ 0 → 승률"
    elif rw <= 0:
        primary, why = "wezd", "승률 R ≤ 0 → wez 차"
    elif rw > rz and rw / rz > 1.5:
        primary, why = "win", f"승률 R 이 wez 차 R 의 {rw / rz:.2f}배 (> 1.5)"
    else:
        primary, why = "wezd", (f"wez 차 R 이 더 큼 ({rz / rw:.2f}배)" if rz >= rw else f"승률 R 이 더 크지만 {rw / rz:.2f}배 ≤ 1.5")
    gate = res[primary]["vlo"] > 0 and not (rz <= 0 and rw <= 0)
    L += ["", "## (2) 1차 지표와 관문 2 판정", "",
          f"- 1차 지표: **{METRICS[primary]}** ({why}).",
          f"- θ 분산 V 의 95% CI 하한 = {res[primary]['vlo']:.4g} → **관문 2 {'통과' if gate else '불통과'}**", ""]

    # (3) 범위 점검
    L += ["## (3) 범위 점검: 노드 작동 (승패·wez 는 보지 않음)", "",
          "구간 = θ 값 기준 범위 3등분. 셀 = \"실행 안 됨\" 경기 비율 / 평균 node_frac. 비활성 = 세 구간 모두 ≥ 90%.", "",
          "| 파라미터 | 범위 | 노드 | 하 1/3 | 중 1/3 | 상 1/3 | 판정 |", "|---|---|---|---|---|---|---|"]
    verdicts = {}
    for p in mt.PARAMS:
        name, node, lo, hi = p["name"], NODE[p["name"]], float(p["lo"]), float(p["hi"])
        cells, off = [], []
        for k in range(3):
            g = [r for t in tids for r in by[t]
                 if min(int((thetas[t][name] - lo) / (hi - lo) * 3), 2) == k]
            fr = [json.loads(r["node_frac"]).get(node, 0.0) for r in g]
            if not fr:
                off.append(False)
                cells.append("—")
                continue
            z = sum(x == 0 for x in fr) / len(fr)
            off.append(z >= 0.9)
            cells.append(f"{z:.0%} / {np.mean(fr):.3f} (n={len(fr)})")
        verdict = "비활성" if all(off) else ("구간 비활성" if any(off) else "작동")
        verdicts[name] = verdict
        L.append(f"| {name} | {p['lo']}–{p['hi']} | {node} | " + " | ".join(cells) + f" | {verdict} |")

    # (4) 품질
    ws = np.array([float(r["wall_s"]) for r in allrows])
    n_wall = sum(r["end_reason"] == "wall_clock" for r in allrows)
    n_dq = sum(r["end_reason"] == "disqualified" for r in allrows)
    L += ["", "## (4) 품질", "", "| 항목 | 값 |", "|---|---|",
          f"| wall_clock 경기 | {n_wall} |", f"| disqualified 경기 | {n_dq} |",
          f"| 기록되지 않은 경기 (계획 − 기록) | {N_PLANNED - len(allrows)} |",
          f"| 실패 경기 합계 | {n_wall + n_dq + N_PLANNED - len(allrows)} |",
          f"| 경기당 wall_s 평균 / 최대 | {ws.mean():.1f} / {ws.max():.1f} |", ""]

    # (5) 탐색적
    tm = {m: np.array([np.mean([metric(r, m) for r in by[t]]) for t in tids]) for m in METRICS}
    L += ["## (5) 파라미터별 스피어만 상관 — **탐색적, 확증 아님**", "",
          "범위나 설계 변경 근거로 쓰지 않는다. dummy 는 잡음 기준선. 순위는 |ρ| 기준.", "",
          "| 파라미터 | ρ (승률) | ρ (wez 차) |", "|---|---|---|"]
    rho = {p: {m: spearman(np.array([thetas[t][p] for t in tids]), tm[m]) for m in METRICS}
           for p in mt.NAMES + ["dummy"]}
    for p in sorted(rho, key=lambda p: -abs(rho[p][primary])):
        L.append(f"| {p} | {rho[p]['win']:+.2f} | {rho[p]['wezd']:+.2f} |")

    # win_mode, 기하·상대
    c = Counter(win_mode(r["winner"], r["end_reason"]) for r in rows)
    wins = len(rows) - c[""]
    L += ["", "## 승리 방식 (청 승리만)", "", "| 승 | " + " | ".join(MODES) + " |", "|---|" + "---|" * len(MODES),
          f"| {wins} | " + " | ".join(f"{c[m]} ({c[m] / max(wins, 1):.0%})" for m in MODES) + " |", ""]
    L += ["## 기하·상대별 평균 (전 θ)", "", "| 기하 \\ 상대 | " + " | ".join(OPPONENTS) + " | 전체 |",
          "|---|" + "---|" * (len(OPPONENTS) + 1)]
    for s in SCENARIOS + ("전체",):
        cells = []
        for o in list(OPPONENTS) + ["전체"]:
            g = [r for r in rows if s in ("전체", r["scenario"]) and o in ("전체", r["opponent"])]
            cells.append(f"{np.mean([metric(r, 'win') for r in g]):.3f} / {np.mean([metric(r, 'wezd') for r in g]):+.2f}")
        L.append(f"| {s} | " + " | ".join(cells) + " |")
    L += ["", "셀 = 승률 / wez 차 평균 [s].", ""]
    L += ["## pilot_rules.md 와 다르게 처리한 것", ""] + notes + [""]
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    gun = [json.loads(r["node_frac"]).get("gun_track", 0.0) for r in rows]
    return dict(n=len(rows), res=res, primary=primary, why=why, gate=gate, verdicts=verdicts, modes=c, wins=wins,
                gun_mean=float(np.mean(gun)), gun_never=sum(x == 0 for x in gun) / len(gun),
                opp_win={o: float(np.mean([metric(r, "win") for r in rows if r["opponent"] == o])) for o in OPPONENTS},
                opp_hd={o: float(np.mean([r["end_reason"] == "hard_deck" and r["winner"] == "blue"
                                          for r in rows if r["opponent"] == o])) for o in OPPONENTS})


ORIGINAL_NOTES = [
    "- **없음.** (1)~(5) 는 규칙 그대로 계산했다.",
    "- 실행 기록 (규칙 위반 아님): 첫 실행은 Claude 세션이 끝나며 함께 종료돼 87경기에서 멈췄고 (14:47), "
    "같은 명령으로 재개해 나머지 2,313경기를 돌렸다 (14:49–16:34). run_bt 는 기록된 경기를 건너뛰므로 "
    "중복 0, 누락 0 을 확인했다. 결정적 엔진이라 끊긴 지점과 무관하게 결과는 같다.",
    "- (3) 의 \"구간 비활성\" (gun_ata_deg 하 1/3 = 15–30°) 은 노드 작동 근거로만 표시했다. 범위 수정 여부는 "
    "이 보고서에서 정하지 않는다.",
    "- 원자료 파일 이름: 보정 상대 도입 때 `bt-pilot/games.csv` → `bt-pilot/games_original.csv` 로 이름만 바꿨다 (내용 동일).",
]


if __name__ == "__main__":
    analyze(GAMES, REPORT, "예비 실험 (관문 2) 결과", ORIGINAL_NOTES)
