"""정답을 아는 합성 데이터 생성기 (분석 코드 시험용). 열 이름은 CONTRACT.md §2 의 games.csv 그대로 (pilot2_sample.csv 와 같은 열).

  python bt/analysis/fixtures/synth.py <출력 폴더>      # synth_rq1.csv, synth_morris.csv, synth_morris_null.csv, synth_confirm.csv, synth_surrogate.csv
  from fixtures import synth; synth.rq1(path); synth.TRUTH_RQ1 ...    # 테스트에서

정답은 이 파일의 TRUTH_* 에 있다. 엔진은 돌리지 않는다. seed 고정 (SEED).
1차 지표 Δwez = wez_blue − wez_red. 합성에서는 wez_red = 20.0 으로 두고 wez_blue = 20.0 + Δwez 로 만든다 (값 자체는 비현실적일 수 있다).
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

BT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
from aircombat.bridge import derive_seed  # noqa: E402

SEED = 20261108
SCENARIOS = ("perch_offense", "perch_defense", "neutral")
OPPONENTS = ("A2_GunTracker_00", "B2_Extender_00", "C1_TwoCircleRate_00", "D1_Reactive_00")
COLS = (["stage", "theta_id"] + mt.NAMES + ["dummy", "scenario", "opponent", "opponent_set", "seed_salt", "seed",
         "winner", "end_reason", "win_mode", "hp_blue_raw", "hp_red_raw", "wez_blue", "wez_red"])
WEZ_RED = 20.0

# ── (a) RQ1: Δwez = μ + θ + 기하 + 상대 + θ×기하 + θ×상대 + 기하×상대 + 잔차(시드) ─────────────────────────────
# 균형 완전교차 (θ 64 × 기하 3 × 상대 4 × 시드 4 = 3,072행). 각 항은 서로 직교하게 만들고 (주효과 중심화, 상호작용 이중 중심화,
# 잔차는 (θ, 기하, 상대) 셀 안에서 시드 방향 중심화) 제곱합을 정확히 맞췄다. 그래서 고정효과 ANOVA 의 η² (= 항 제곱합 / 전체 제곱합) 가
# 아래 값과 부동소수 오차 안에서 같아야 한다. θ×기하×상대 3원 상호작용은 0 (잔차에 포함되는 항이지만 합성에서는 없음).
TRUTH_RQ1 = {
    "n_theta": 64, "n_rows": 3072, "grand_mean": -2.4, "total_sd": 3.0,
    "eta2": {"theta": 0.30, "geometry": 0.10, "opponent": 0.20, "theta:geometry": 0.05,
             "theta:opponent": 0.10, "geometry:opponent": 0.05, "residual": 0.20},
    "tolerance": 1e-6,     # CSV 에 소수 10자리로 저장
}


def _rows(stage, th, scen, opp, i, dwez):
    salt = f"{stage}-{i}"
    win = "blue" if dwez > 0 else "red"
    return {"stage": stage, "theta_id": mt.theta_id(th), **{k: th[k] for k in mt.NAMES}, "dummy": th["dummy"],
            "scenario": scen, "opponent": opp, "opponent_set": "patched", "seed_salt": salt, "seed": derive_seed(scen, salt),
            "winner": win, "end_reason": "timeout", "win_mode": "judge" if win == "blue" else "",
            "hp_blue_raw": round(float(np.clip(50 + 5 * dwez, 0, 100)), 2), "hp_red_raw": 50.0,
            "wez_blue": round(WEZ_RED + float(dwez), 10), "wez_red": WEZ_RED}


def _write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _scale(term, ss):
    return term * np.sqrt(ss / np.sum(term ** 2))


def rq1_values():
    """Δwez 배열 [θ, 기하, 상대, 시드] 와 θ 목록."""
    import designs
    t = TRUTH_RQ1
    rng = np.random.default_rng(SEED)
    nt, ng, no, ns = t["n_theta"], len(SCENARIOS), len(OPPONENTS), 4
    shape, n = (nt, ng, no, ns), nt * ng * no * ns
    ss_total = n * t["total_sd"] ** 2

    def main(axis, size):
        v = rng.normal(size=size)
        v = v - v.mean()
        idx = [None] * 4
        idx[axis] = slice(None)
        return np.broadcast_to(v[tuple(idx)], shape)

    def inter(a1, a2, s1, s2):
        v = rng.normal(size=(s1, s2))
        v = v - v.mean(0, keepdims=True) - v.mean(1, keepdims=True) + v.mean()
        idx = [None] * 4
        idx[a1], idx[a2] = slice(None), slice(None)
        return np.broadcast_to(v[tuple(idx)], shape)

    res = rng.normal(size=shape)
    res = res - res.mean(3, keepdims=True)
    terms = {"theta": main(0, nt), "geometry": main(1, ng), "opponent": main(2, no),
             "theta:geometry": inter(0, 1, nt, ng), "theta:opponent": inter(0, 2, nt, no),
             "geometry:opponent": inter(1, 2, ng, no), "residual": res}
    y = t["grand_mean"] + sum(_scale(v, t["eta2"][k] * ss_total) for k, v in terms.items())
    return y, [mt.normalize(x) for x in designs.lhs(nt, SEED)]


def rq1(path):
    y, ths = rq1_values()
    _write(path, [_rows("synth-rq1", ths[a], SCENARIOS[g], OPPONENTS[o], s, y[a, g, o, s])
                  for a in range(len(ths)) for g in range(3) for o in range(4) for s in range(4)])


# ── (b) Morris: bt/thetas/main_morris_r16.csv 의 θ 192개 (궤적 16) × 48경기 ─────────────────────────────────────
# x_p = (θ_p − lo) / (hi − lo) ∈ {0, 1/3, 2/3, 1} (수준 4). 기본효과 EE = (f(x + Δ) − f(x)) / Δ, Δ = 2/3 (SALib 정의, 정규화 단위).
#   f = −3.0·x_fight_kcas  +  b(기하)·x_floor_ft  +  4.0·(x_threat_aspect_deg − 0.5)²,   b = −3.0 (perch_offense, perch_defense), 0 (neutral)
#   나머지 7개 파라미터와 dummy 는 효과 0.
# 경기 값 = f + 셀 효과 (기하·상대, 모든 θ 에 같음) + 잡음 N(0, 1.5²).
# 이론 μ* (잡음 없음, θ 별 48경기 평균 기준, 이 설계 파일로 직접 계산해 확인함):
#   fight_kcas 3.0 (선형, μ = −3.0, σ = 0), floor_ft 2.0 (= 3.0·2/3, 기하별: 공세·수세 3.0, neutral 0),
#   threat_aspect_deg 4/3 (비선형: |EE| 은 늘 4/3, 부호가 위치에 따라 바뀌어 σ > 0 — 이 설계에서 μ = 1/3, σ ≈ 1.29), 나머지 0.
TRUTH_MORRIS = {
    "design_file": "bt/thetas/main_morris_r16.csv", "noise_sd": 1.5,
    "mu_star": {"fight_kcas": 3.0, "floor_ft": 2.0, "threat_aspect_deg": 4.0 / 3.0},
    "important": {"fight_kcas", "floor_ft", "threat_aspect_deg"},
    "not_important": {"merge_range_ft", "gun_range_ft", "gun_ata_deg", "energy_min_ft", "lead_time_s",
                      "break_g_burst", "closing_min_fps", "dummy"},
    "nonlinear": {"threat_aspect_deg"},
    "geometry_mu_star": {"floor_ft": {"perch_offense": 3.0, "perch_defense": 3.0, "neutral": 0.0}},
    "geometry_differs": {"floor_ft"},       # 공세·수세에서 중요, neutral 에서 중요 아님
}
_FLOOR_B = {"perch_offense": -3.0, "perch_defense": -3.0, "neutral": 0.0}
_CELL = {(s, o): 0.5 * i - 1.0 * j for i, s in enumerate(SCENARIOS) for j, o in enumerate(OPPONENTS)}


def _x(th, name):
    p = next(q for q in mt.PARAMS + [mt.DUMMY] if q["name"] == name)
    return (th[name] - float(p["lo"])) / (float(p["hi"]) - float(p["lo"]))


def morris_f(th, scen):
    return (-3.0 * _x(th, "fight_kcas") + _FLOOR_B[scen] * _x(th, "floor_ft")
            + 4.0 * (_x(th, "threat_aspect_deg") - 0.5) ** 2)


def morris(path):
    import run_bt
    ths = run_bt.read_thetas(os.path.join(BT, "thetas", "main_morris_r16.csv"))
    rng = np.random.default_rng(SEED + 1)
    _write(path, [_rows("synth-morris", th, s, o, i, morris_f(th, s) + _CELL[(s, o)] + rng.normal(0, TRUTH_MORRIS["noise_sd"]))
                  for th in ths for s in SCENARIOS for o in OPPONENTS for i in range(4)])


# ── (b2) 대리모델: 본실험과 같은 θ 256개 (main_lhs64.csv 64 + main_morris_r16.csv 192) × 48경기 ─────────────────────
# 값은 (b) 와 같은 함수 morris_f + 셀 효과 + 잡음 N(0, 1.5²). 떼어 두기는 PREREG_BT.md §6.3 의 집단 단위 규칙:
#   rng = numpy.random.default_rng(20261108); Morris 궤적 rng.choice(16, 3, replace=False) 의 θ 36개,
#   이어서 LHS θ (파일 행 순서 0–63) rng.choice(64, 13, replace=False) 의 13개 → 합계 49 θ.
# 정답: 떼어 둔 θ 49개 (궤적 3개 전체 + LHS 13개), 같은 궤적의 θ 가 학습·떼어 둠 양쪽에 나뉘지 않음,
#   기본값 HistGradientBoostingRegressor(random_state=20261108) 의 떼어 둔 R² ≥ 0.5 (이 생성기로 확인한 값 r2_holdout_check),
#   y 를 순수 잡음으로 바꾸면 R² < 0.5 (r2_noise_check).
TRUTH_SURROGATE = {
    "design_files": ("bt/thetas/main_lhs64.csv", "bt/thetas/main_morris_r16.csv"), "n_theta": 256,
    "holdout_seed": 20261108, "holdout_trajectories": 3, "holdout_lhs": 13, "n_holdout": 49,
    "r2_min": 0.5,
    "holdout_trajectory_ids": {0, 5, 12},   # 위 규칙으로 뽑힌 Morris 궤적 (seed 20261108)
    # 참고값 (2026-11-02, 이 생성기 + HistGradientBoostingRegressor(random_state=20261108), 나머지 기본값으로 확인):
    "r2_holdout_check": 0.954,                # 떼어 둔 49 θ 의 R² (≥ 0.5 이어야 함)
    "r2_noise_check": -0.502,                 # y 를 numpy.random.default_rng(1).normal(size=256) 로 바꾼 경우 (< 0.5 이어야 함)
}


def holdout_ids(lhs_ids, morris_ids, morris_traj, seed=20261108):
    """PREREG_BT.md §6.3 떼어 두기 (정답 계산용). lhs_ids: LHS θ id (파일 행 순서), morris_ids·morris_traj: Morris θ id 와 궤적 번호."""
    rng = np.random.default_rng(seed)
    trajs = set(int(t) for t in rng.choice(16, 3, replace=False))
    lhs_pick = rng.choice(64, 13, replace=False)
    return ({i for i, t in zip(morris_ids, morris_traj) if t in trajs} | {lhs_ids[k] for k in lhs_pick}), trajs


def surrogate(path):
    import run_bt
    rng = np.random.default_rng(SEED + 3)
    rows = []
    for name in ("main_lhs64.csv", "main_morris_r16.csv"):
        for th in run_bt.read_thetas(os.path.join(BT, "thetas", name)):
            rows += [_rows("synth-surrogate", th, s, o, i, morris_f(th, s) + _CELL[(s, o)] + rng.normal(0, TRUTH_MORRIS["noise_sd"]))
                     for s in SCENARIOS for o in OPPONENTS for i in range(4)]
    _write(path, rows)


# ── (b3) Morris 잡음 기준선 (PREREG_BT_DEVIATIONS.md #3 의 새 중요 판정 시험용) ──────────────────────────────────────
# main_morris_r16.csv 의 θ 192개 × 48경기. 실제 엔진처럼 **더미만 다른 θ 는 결과가 완전히 같다**: 경기 잡음은 (더미를 뺀 θ, 셀) 로 정한 난수라
# 더미 단계의 셀별 짝 차이 d_c 는 정확히 0. 효과 없는 파라미터 단계는 d_c 가 평균 0 인 잡음뿐 (θ 가 바뀌면 잡음 실현값이 바뀐다).
# 효과 있는 파라미터는 morris_f 와 같은 뚜렷한 평균 이동 (fight_kcas −3.0, floor_ft −3.0 은 공세·수세만, threat_aspect_deg 비선형).
#   y(θ, c) = morris_f(θ, 기하) + 셀 효과 + N(0, 1.5²),   N 은 (더미 뺀 θ, 셀) 로 seed 를 정한 난수.
# 정답 (새 규칙: 관측 μ* 의 부트스트랩 95% CI 하한 > 그 파라미터의 부호 뒤집기 잡음 기준선 (μ* 귀무 분포 95백분위), 2,000회, seed 20261108):
TRUTH_MORRIS_NULL = {
    "design_file": "bt/thetas/main_morris_r16.csv", "noise_sd": 1.5,
    "important": {"fight_kcas", "floor_ft", "threat_aspect_deg"},
    "not_important": {"merge_range_ft", "gun_range_ft", "gun_ata_deg", "energy_min_ft", "lead_time_s",
                      "break_g_burst", "closing_min_fps", "dummy"},
    "dummy_exact_zero": True,               # 더미 단계의 d_c 가 모두 정확히 0 → 더미 μ*·μ·σ·CI·잡음 기준선 모두 0
    "geometry_differs": {"floor_ft"},       # 공세·수세에서 중요, neutral 에서 중요 아님 (셀 16개)
}


def _null_noise(th, scen, opp, i):
    import hashlib
    key = repr(tuple(th[k] for k in mt.NAMES)) + f"|{scen}|{opp}|{i}"        # 더미를 뺀 θ 와 셀
    return np.random.default_rng(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16)).normal(0, TRUTH_MORRIS_NULL["noise_sd"])


def morris_null(path):
    import run_bt
    ths = run_bt.read_thetas(os.path.join(BT, "thetas", "main_morris_r16.csv"))
    _write(path, [_rows("synth-morris-null", th, s, o, i, morris_f(th, s) + _CELL[(s, o)] + _null_noise(th, s, o, i))
                  for th in ths for s in SCENARIOS for o in OPPONENTS for i in range(4)])


# ── (c) 확인 단계: 기준 θ + 후보 θ 3개, θ 마다 432경기 (기하 3 × 상대 4 × 시드 36), 같은 셀끼리 짝 ──────────────────
# 후보 − 기준 짝 차이 Δwez 의 표본 평균과 표본 표준편차 (ddof=1) 를 정확히 맞췄다: 평균 = delta, sd = 2.0 (432쌍).
# 기대 판정 (PREREG_BT.md §6.4: "낫다" = Holm 보정 후 단측 유의 (α 0.05) 이고 95% CI 하한 > 0, "실질적으로 낫다" = 여기에
# 점추정 ≥ 0.5 s, 동등성 = ±0.5 s TOST (α 0.05)). 표준오차 = 2.0/√432 ≈ 0.0962 s.
TRUTH_CONFIRM = {
    "n_per_theta": 432, "pair_sd": 2.0,
    "candidates": {   # 이름: (짝 차이 평균, 낫다, 실질적으로 낫다, 동등)
        "cand_big": {"delta": 0.8, "better": True, "practically_better": True, "equivalent": False,
                     "p_one_sided": 6.1e-16, "ci95": (0.611, 0.989)},
        "cand_small": {"delta": 0.2, "better": True, "practically_better": False, "equivalent": True,
                       "p_one_sided": 0.0191, "ci95": (0.011, 0.389)},
        "cand_zero": {"delta": 0.0, "better": False, "practically_better": False, "equivalent": True,
                      "p_one_sided": 0.5, "ci95": (-0.189, 0.189)},
    },
    # p·CI 는 짝 t (자유도 431) 기준 참고값 (소수 3자리). Holm (후보 3개): cand_big, cand_small 기각, cand_zero 유지.
}


def confirm_thetas():
    """{이름: θ}. 기준 θ 와 후보 3개 (main_lhs64.csv 앞 3개, 합성이라 θ 값은 결과와 무관)."""
    import run_bt
    lhs = run_bt.read_thetas(os.path.join(BT, "thetas", "main_lhs64.csv"))
    return {"baseline": mt.normalize({**mt.BASE, "dummy": mt.DUMMY["base"]}),
            **{name: lhs[i] for i, name in enumerate(TRUTH_CONFIRM["candidates"])}}


def confirm(path):
    rng = np.random.default_rng(SEED + 2)
    cells = [(s, o, i) for s in SCENARIOS for o in OPPONENTS for i in range(36)]
    base = np.array([_CELL[(s, o)] for s, o, _ in cells]) + rng.normal(0, 2.0, len(cells))
    ths = confirm_thetas()
    rows = [_rows("bt-confirm", ths["baseline"], s, o, i, v) for (s, o, i), v in zip(cells, base)]
    for name, c in TRUTH_CONFIRM["candidates"].items():
        d = rng.normal(size=len(cells))
        d = (d - d.mean()) / d.std(ddof=1) * TRUTH_CONFIRM["pair_sd"] + c["delta"]
        rows += [_rows("bt-confirm", ths[name], s, o, i, v) for (s, o, i), v in zip(cells, base + d)]
    _write(path, rows)


def write_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    out = {k: os.path.join(out_dir, f"synth_{k}.csv") for k in ("rq1", "morris", "morris_null", "confirm", "surrogate")}
    rq1(out["rq1"])
    morris(out["morris"])
    confirm(out["confirm"])
    surrogate(out["surrogate"])
    morris_null(out["morris_null"])
    return out


def _self_check():
    """생성기 점검 (분석 코드가 아님): RQ1 항들이 직교해 제곱합이 정확히 나뉘는지, 확인 단계 짝 차이가 정답과 같은지."""
    y, _ = rq1_values()
    ss = np.sum((y - y.mean()) ** 2)
    assert abs(ss - y.size * TRUTH_RQ1["total_sd"] ** 2) < 1e-6 * ss
    assert abs(y.mean() - TRUTH_RQ1["grand_mean"]) < 1e-12


if __name__ == "__main__":
    _self_check()
    for k, v in write_all(sys.argv[1] if len(sys.argv) > 1 else ".").items():
        print(k, v)
