"""E층 도그파이트 분석 — 개정 A31 §4~§6 의 규칙을 그대로 코드로 옮긴다.

입력: dogfight.py 가 만든 runs.csv (한 경기 한 행). OFAT 실행과 결합 실행을 함께 넣을 수 있다(같은 커밋이어야 짝이 성립).
출력: research/l3_indi/reports/DOGFIGHT_<라벨>.md + results 폴더 안 analysis/{effects.csv, envelope.csv, *.png, *.pdf}

사용:
  python research/l3_indi/dogfight_analysis.py --pilot <pilot 결과 폴더>             A31 §8-2 파일럿 점검
  python research/l3_indi/dogfight_analysis.py <OFAT 폴더> [<결합 폴더>] [--label 이름]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

N_BOOT = 10_000
BOOT_SEED = 20260925                          # A31 §5
PRIMARY = {"hp_diff_d8": 9.4, "net_wez": 0.25}          # A31 §4 δ
SENS = {"hp_diff_d8": (4.7, 18.8), "net_wez": (0.1, 0.5)}   # A31 §4 민감도 δ (작게, 크게) — 표에 등록된 값 그대로
PRIMARY_LABEL = {"hp_diff_d8": "종료 체력차 [HP] (D8)", "net_wez": "WEZ 체류시간 차 [s]"}
POSITIVE_CONTROLS = ("V3_lam_25", "V4_async_2t")      # A31 §5
SHAM = "SHAM"
BASE = "BASE"
GATE_NZ_MAX, GATE_NZ_MIN, GATE_ALPHA_DEG, GATE_FRAC = 9.0, -3.0, 30.0, 0.05   # A31 §5 (사전등록 §7.1·§8)
REPORTED = ("blue_pts", "frac_ata30_blue", "frac_slant_band", "frac_ata_band_blue",
            "frac_fight_speed_blue", "frac_corner_blue", "kcas_mean_blue", "dalt_blue_ft",
            "t_first_wez_blue", "wez_censored_blue", "J_q", "J_p", "corr_q", "q_gain", "sat_ele")
# 첫 WEZ 진입이 없는 경기는 t_first_wez = 종료 시각(검열)이고 wez_censored = 1 이다 (A31 §4 '검열 표시').
E_KEYS_FOR_IDENTITY = ("winner", "condition", "time_s", "hp_blue", "hp_red", "wez_time_blue", "wez_time_red")
PAIR_KEY = ("scenario", "red", "salt")
VAR_ORDER = ("V1_kq", "V2_filt", "V3_lam", "V4_delay", "V4_delay_async", "V5_noise", "V6_turb")
VAR_LABEL = {"V1_kq": "V1 피치 게인 k_q 배율", "V2_filt": "V2 필터 [Hz]", "V3_lam": "V3 λ_q",
             "V4_delay": "V4 동기 지연 [틱]", "V4_delay_async": "V4 비동기 지연 [틱]",
             "V5_noise": "V5 자이로 잡음 σ [°/s]", "V6_turb": "V6 난류"}
BASE_LEVEL = {"V1_kq": 1.0, "V2_filt": 25.0, "V3_lam": 1.0, "V4_delay": 0.0, "V4_delay_async": 0.0,
              "V5_noise": 0.0, "V6_turb": "none"}
TURB_ORDER = ("none", "light", "moderate", "severe")
NUM_FIELDS = None                             # load_runs 가 채운다


# ======================================================================================
# 읽기와 무결성
# ======================================================================================
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


# 경기 결과를 정하는 코드·데이터. 두 실행의 커밋이 달라도 이 경로에 차이가 없으면 같은 실험으로 본다.
RUNNER_PATHS = ("research/l3_indi/dogfight.py", "research/l3_indi/dogfight_grid.json",
                "research/l3_indi/harness.py", "aircombat", "jsbsim_data", "config", "redteams")


def _same_runner(c1: str, c2: str) -> bool:
    import subprocess
    from l3_indi.runner import REPO
    r = subprocess.run(["git", "diff", "--quiet", c1, c2, "--", *RUNNER_PATHS], cwd=REPO)
    return r.returncode == 0


def load_runs(dirs) -> list[dict]:
    rows, commits = [], []
    for d in dirs:
        man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        commits.append(man["git"]["commit"])
        if not man["git"]["clean"]:
            raise RuntimeError(f"{d}: 커밋 안 된 코드로 만든 결과 (manifest clean=False)")
        for r in csv.DictReader(open(os.path.join(d, "runs.csv"), encoding="utf-8")):
            rows.append({k: _num(v) for k, v in r.items()})
    for c in commits[1:]:
        if c != commits[0] and not _same_runner(commits[0], c):
            raise RuntimeError(f"실행 코드가 다른 결과를 섞을 수 없다(짝 비교): {commits[0][:10]} vs {c[:10]} "
                               f"({', '.join(RUNNER_PATHS)} 에 차이)")
    return rows


def integrity(rows) -> list[tuple[str, bool, str]]:
    """A31 §8: wall_clock 0 건, wez_recount_ok 전부 1, 경기 중복 없음, 설정당 경기 수 동일."""
    out = []
    wc = sum(1 for r in rows if r["condition"] == "wall_clock")
    out.append(("wall_clock 종료 0 건", wc == 0, f"{wc} 건"))
    bad = [r["match_id"] for r in rows if int(r["wez_recount_ok"]) != 1]
    out.append(("WEZ·ATA 재계산 = 엔진 (전 경기)", not bad, f"불일치 {len(bad)} 건 {bad[:3]}"))
    ids = Counter(r["match_id"] for r in rows)
    dup = [k for k, v in ids.items() if v > 1]
    out.append(("경기 중복 없음", not dup, f"중복 {len(dup)}"))
    per = Counter(r["setting_name"] for r in rows)
    out.append(("설정당 경기 수 동일", len(set(per.values())) == 1, dict(per) if len(per) <= 6 else f"{min(per.values())}~{max(per.values())}"))
    return out


def by_setting(rows) -> dict:
    d = defaultdict(dict)
    for r in rows:
        d[r["setting_name"]][tuple(r[k] for k in PAIR_KEY)] = r
    return d


# ======================================================================================
# 통계
# ======================================================================================
def boot_ci(x: np.ndarray, rng_seed: int = BOOT_SEED, n: int = N_BOOT, stat=np.mean):
    """짝 단위 복원추출 부트스트랩 95% 백분위 CI (A31 §5)."""
    x = np.asarray(x, float)
    if len(x) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    s = stat(x[idx], axis=1)
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def judge(lo: float, hi: float, delta: float) -> str:
    """A24 §9 3 구간 판정."""
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "판정 불가"
    if lo >= -delta and hi <= delta:
        return "차이 없음"
    if lo > delta or hi < -delta:
        return "차이 있음"
    return "판정 불가"


def final_judge(j: str, st: dict) -> str:
    """A31 §5: 가짜 짝 보정에 실패한 지표는 제외하고, 양성 대조를 못 잡은(둔감) 지표의 '차이 없음' 은
    OFAT·결합 효과 모두 '판정 불가' 로 낮춘다."""
    if st["calibration_failed"]:
        return "제외(가짜 짝 보정 실패)"
    if not st["sensitive"] and j == "차이 없음":
        return "판정 불가(둔감 지표)"
    return j


def paired(S: dict, B: dict, metric: str):
    keys = sorted(set(S) & set(B))
    if len(keys) != len(B) or len(keys) != len(S):
        raise RuntimeError(f"짝이 맞지 않음: 설정 {len(S)}, 기준 {len(B)}, 공통 {len(keys)}")
    return np.array([float(S[k][metric]) - float(B[k][metric]) for k in keys]), keys


def effect_table(rows) -> tuple[list[dict], dict]:
    """모든 설정 × 지표의 짝 차이 평균·중앙값·CI 와 주 지표 3 구간 판정(양성 대조·가짜 짝 규칙 포함)."""
    S = by_setting(rows)
    if BASE not in S:
        raise RuntimeError("BASE 설정이 없다")
    B = S[BASE]
    meta = {r["setting_name"]: r for r in rows}
    out = []
    for name in S:
        if name == BASE:
            continue
        for metric in list(PRIMARY) + list(REPORTED):
            d, _ = paired(S[name], B, metric)
            d = d[np.isfinite(d)]
            lo, hi = boot_ci(d)
            row = {"setting": name, "family": meta[name]["family"], "variable": meta[name]["variable"],
                   "level": meta[name]["level"], "metric": metric, "n": len(d),
                   "mean": float(np.mean(d)) if len(d) else float("nan"),
                   "median": float(np.median(d)) if len(d) else float("nan"),
                   "ci_lo": lo, "ci_hi": hi}
            if metric in PRIMARY:
                dl = PRIMARY[metric]
                row["judge"] = judge(lo, hi, dl)
                row["judge_sens_lo"] = judge(lo, hi, SENS[metric][0])
                row["judge_sens_hi"] = judge(lo, hi, SENS[metric][1])
            out.append(row)
    # 가짜 짝 보정과 양성 대조 규칙 (주 지표만)
    status = {}
    for metric in PRIMARY:
        sham = next((r for r in out if r["setting"] == SHAM and r["metric"] == metric), None)
        pcs = [r for r in out if r["setting"] in POSITIVE_CONTROLS and r["metric"] == metric]
        calib_fail = sham is not None and sham["judge"] == "차이 있음"
        sensitive = any(r["judge"] == "차이 있음" for r in pcs)
        status[metric] = {"sham": sham["judge"] if sham else "없음", "calibration_failed": calib_fail,
                          "sensitive": sensitive, "pc": {r["setting"]: r["judge"] for r in pcs}}
        for r in out:
            if r["metric"] == metric:
                r["judge_final"] = final_judge(r["judge"], status[metric])
    return out, status


def chaos_floor(rows) -> dict:
    """가짜 짝의 짝 단위 기술 통계 (A31 §5 — 판정에는 쓰지 않는다)."""
    S = by_setting(rows)
    if SHAM not in S:
        return {}
    B, H = S[BASE], S[SHAM]
    keys = sorted(set(B) & set(H))
    same = [all(B[k][f] == H[k][f] for f in E_KEYS_FOR_IDENTITY) for k in keys]
    flip = [B[k]["winner"] != H[k]["winner"] for k in keys]
    dhp = np.abs([float(H[k]["hp_diff_d8"]) - float(B[k]["hp_diff_d8"]) for k in keys])
    dwez = np.abs([float(H[k]["net_wez"]) - float(B[k]["net_wez"]) for k in keys])
    return {"n": len(keys), "identical_frac": float(np.mean(same)), "winner_flip_frac": float(np.mean(flip)),
            "abs_dhp_p50": float(np.percentile(dhp, 50)), "abs_dhp_p95": float(np.percentile(dhp, 95)),
            "abs_dwez_p50": float(np.percentile(dwez, 50)), "abs_dwez_p95": float(np.percentile(dwez, 95))}


def _exceed(r, prefix: str = "") -> bool:
    """한 경기의 봉투 초과 (A31 §5 정의: Nz > +9 / < −3 G 또는 α > 30°). prefix '' = 청군(게이트), 'red_' = 적군(보고만)."""
    return (r[f"{prefix}nz_max"] > GATE_NZ_MAX) or (r[f"{prefix}nz_min"] < GATE_NZ_MIN) or \
        (r[f"{prefix}alpha_max_deg"] > GATE_ALPHA_DEG)


def envelope_table(rows) -> list[dict]:
    """설정별 F-16 봉투 사용량과 게이트 판정.

    판정(A33 ⚠, A31 §5 의 절대 5% 규칙을 대체): 같은 IC 짝에서 (설정 초과 여부 − BASE 초과 여부) 평균의
    부트스트랩 95% CI 하한이 0 보다 크면 "기준보다 봉투를 더 넘는 수준" 으로 표시한다(flag).
    A31 원래 규칙(절대 초과율 > 5%)은 flag_abs 로 함께 남긴다.
    """
    S = by_setting(rows)
    B = S.get(BASE)
    meta = {r["setting_name"]: r for r in rows}
    out = []
    for name, M in S.items():
        rs = list(M.values())
        f = float(np.mean([_exceed(r) for r in rs]))
        d_mean = d_lo = d_hi = 0.0
        if B is not None and name != BASE:
            keys = sorted(set(M) & set(B))
            if len(keys) != len(B) or len(keys) != len(M):
                raise RuntimeError(f"봉투 짝이 맞지 않음: {name}")
            d = np.array([float(_exceed(M[k])) - float(_exceed(B[k])) for k in keys])
            d_mean = float(d.mean())
            d_lo, d_hi = boot_ci(d)
        out.append({"setting": name, "family": meta[name]["family"], "variable": meta[name]["variable"],
                    "level": meta[name]["level"], "n": len(rs), "exceed_frac": f,
                    "d_vs_base": d_mean, "d_ci_lo": d_lo, "d_ci_hi": d_hi,
                    "flag": int(d_lo > 0), "flag_abs": int(f > GATE_FRAC),
                    "nz_max_max": max(r["nz_max"] for r in rs), "nz_min_min": min(r["nz_min"] for r in rs),
                    "alpha_max_p95": float(np.percentile([r["alpha_max_deg"] for r in rs], 95)),
                    "alpha_max_max": max(r["alpha_max_deg"] for r in rs),
                    "p_max_max": max(r["p_max_dps"] for r in rs),
                    "q_max_max": max(r["q_max_dps"] for r in rs),
                    "turn_rate_max_p95": float(np.percentile([r["turn_rate_max_dps"] for r in rs], 95)),
                    "turn_rate_max_max": max(r["turn_rate_max_dps"] for r in rs),
                    "kcas_min_min": min(r["kcas_min"] for r in rs),
                    "alt_min_min": min(r["alt_min_ft"] for r in rs),
                    # 적군 (A31 §4 '청군·적군' 봉투 — 판정 없이 기술 통계만)
                    "red_exceed_frac": float(np.mean([_exceed(r, "red_") for r in rs])),
                    "red_nz_max_max": max(r["red_nz_max"] for r in rs),
                    "red_nz_min_min": min(r["red_nz_min"] for r in rs),
                    "red_alpha_max_max": max(r["red_alpha_max_deg"] for r in rs),
                    "red_p_max_max": max(r["red_p_max_dps"] for r in rs),
                    "red_q_max_max": max(r["red_q_max_dps"] for r in rs),
                    "red_turn_rate_max_max": max(r["red_turn_rate_max_dps"] for r in rs),
                    "red_kcas_min_min": min(r["red_kcas_min"] for r in rs),
                    "red_alt_min_min": min(r["red_alt_min_ft"] for r in rs),
                    "cond": dict(Counter(r["condition"] for r in rs))})
    return out


FORFEIT_CONDS = ("hard_deck", "stall", "health_zero")      # 엔진 _judge: 이 사유를 낸 쪽이 진다(양측이면 무승부)


def outcome_table(rows) -> list[dict]:
    """설정별 승패와 종료 사유 분해 (A31 §4 보고 지표, 기술 통계). 판정패·격추는 누가 졌는지까지 나눈다."""
    S = by_setting(rows)
    meta = {r["setting_name"]: r for r in rows}
    out = []
    for name, M in S.items():
        rs = list(M.values())
        c = Counter((r["condition"], r["winner"]) for r in rs)
        row = {"setting": name, "family": meta[name]["family"], "n": len(rs),
               "blue_win": sum(r["winner"] == "blue" for r in rs), "red_win": sum(r["winner"] == "red" for r in rs),
               "draw": sum(r["winner"] == "draw" for r in rs)}
        for cond in FORFEIT_CONDS:
            row[f"blue_lost_{cond}"] = c[(cond, "red")]
            row[f"red_lost_{cond}"] = c[(cond, "blue")]
            row[f"both_{cond}"] = c[(cond, "draw")]
        row["timeout"] = sum(r["condition"] == "timeout" for r in rs)
        row["no_contact"] = sum(r["condition"] == "no_contact" for r in rs)
        row["other"] = len(rs) - row["timeout"] - row["no_contact"] - sum(
            row[f"{k}_{cond}"] for cond in FORFEIT_CONDS for k in ("blue_lost", "red_lost", "both"))
        row["blue_wez_censored_frac"] = float(np.mean([r["wez_censored_blue"] for r in rs]))
        out.append(row)
    return out


def combined_effects(rows, design, status: dict | None = None) -> dict:
    """2^(6-2) 주효과·2 원 교호작용(별칭 묶음)·가산성 (A31 §6). IC 단위 클러스터 부트스트랩.
    status(effect_table 의 지표 상태)를 주면 A31 §5 규칙을 적용한 judge_final 도 붙인다."""
    from l3_indi.dogfight import FACTORS
    S = by_setting(rows)
    cells = {d["name"]: (BASE if not d["set"] else d["name"]) for d in design}
    if any(c not in S for c in cells.values()):
        return {}
    keys = sorted(S[BASE])
    code = np.array([[d["_code"][f] for f in FACTORS] for d in design])                 # 16 × 6
    two = {}
    for i, a in enumerate(FACTORS):
        for j, b in enumerate(FACTORS):
            if j > i:
                col = code[:, i] * code[:, j]
                grp = next((g for g, c in two.items() if np.array_equal(c, col)), None)
                if grp is None:
                    two[a + b] = col
                else:
                    two[f"{grp}={a}{b}"] = two.pop(grp)
    out = {}
    for metric in PRIMARY:
        Y = np.array([[float(S[cells[d["name"]]][k][metric]) for d in design] for k in keys])   # IC × 16
        cols = {f: code[:, i] for i, f in enumerate(FACTORS)}
        cols.update(two)
        eff = {}
        rng = np.random.default_rng(BOOT_SEED)
        idx = rng.integers(0, len(keys), size=(N_BOOT, len(keys)))
        for name, c in cols.items():
            per_ic = (Y[:, c > 0].mean(axis=1) - Y[:, c < 0].mean(axis=1))
            bs = per_ic[idx].mean(axis=1)
            lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
            eff[name] = {"effect": float(per_ic.mean()), "ci_lo": lo, "ci_hi": hi,
                         "judge": judge(lo, hi, PRIMARY[metric])}
            if status is not None:
                eff[name]["judge_final"] = final_judge(eff[name]["judge"], status[metric])
        x16 = [i for i, d in enumerate(design) if all(v > 0 for v in d["_code"].values())][0]
        x01 = [i for i, d in enumerate(design) if all(v < 0 for v in d["_code"].values())][0]
        obs = Y[:, x16] - Y[:, x01]
        lo, hi = boot_ci(obs)
        out[metric] = {"effects": eff, "x16_minus_base": {"mean": float(obs.mean()), "ci_lo": lo, "ci_hi": hi}}
    return out


def combined_high_settings(grid: dict) -> dict:
    """결합 설계 인자별 '높음' 과 같은 설정을 가진 OFAT 수준 이름 {인자: 설정 이름} (격자에서 자동 대응)."""
    from l3_indi.dogfight import FACTORS
    out = {}
    for f in FACTORS:
        high = grid["combined"]["factors"][f]["high"]
        match = [s["name"] for s in grid["settings"] if s["family"] == "ofat" and s["set"] == high]
        if len(match) != 1:
            raise RuntimeError(f"인자 {f} 의 높음 {high} 에 대응하는 OFAT 수준이 {len(match)} 개")
        out[f] = match[0]
    return out


def gate_check(dirs) -> int:
    """A31 §6·§8: OFAT 실행이 무결하고, 결합 설계의 '높음' 수준 6 개가 F-16 봉투 게이트(A33 ⚠: 기준 대비)를 통과하면 0."""
    from l3_indi.dogfight import load_grid
    grid = load_grid()
    high = combined_high_settings(grid)
    rows = load_runs(dirs)
    ok = True
    for name, passed, ev in integrity(rows):
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {ev}")
        ok &= bool(passed)
    env = {r["setting"]: r for r in envelope_table(rows)}
    if BASE not in env:
        print("  [FAIL] BASE 가 OFAT 결과에 없음")
        return 1
    for f, name in high.items():
        r = env.get(name)
        if r is None:
            print(f"  [FAIL] 인자 {f} 높음 = {name}: OFAT 결과에 없음")
            ok = False
            continue
        print(f"  [{'FAIL' if r['flag'] else 'PASS'}] 인자 {f} 높음 = {name}: 봉투 초과 {100 * r['exceed_frac']:.1f}% "
              f"(기준 {100 * env[BASE]['exceed_frac']:.1f}%, 짝 차 {100 * r['d_vs_base']:+.1f}%p "
              f"[{100 * r['d_ci_lo']:+.1f}, {100 * r['d_ci_hi']:+.1f}]; "
              f"n {r['n']}, 최대 Nz {r['nz_max_max']:.2f}, 최소 Nz {r['nz_min_min']:.2f}, α 최대 {r['alpha_max_max']:.1f}°)")
        ok &= not r["flag"]
    print(f"[gate-check] {'PASS → 결합 설계 그대로 실행' if ok else 'FAIL → A31 §6 규칙 적용 필요(자동 실행 중단)'}")
    return 0 if ok else 1


def additivity(effects: list[dict], comb: dict, grid: dict) -> dict:
    """OFAT 단독 효과의 합 vs 결합 X16 실측 (A31 §6)."""
    if not comb:
        return {}
    high_names = combined_high_settings(grid)
    out = {}
    for metric in PRIMARY:
        parts = {f: next((r["mean"] for r in effects if r["setting"] == n and r["metric"] == metric), float("nan"))
                 for f, n in high_names.items()}
        pred = float(np.nansum(list(parts.values())))
        obs = comb[metric]["x16_minus_base"]
        out[metric] = {"ofat_parts": parts, "predicted_sum": pred, "observed": obs,
                       "inside_ci": bool(obs["ci_lo"] <= pred <= obs["ci_hi"])}
    return out


TREND_METRICS = tuple(PRIMARY) + ("J_q",)


def _monotone(vals) -> str:
    """수준 순서로 늘어놓은 점추정의 단조 여부 (A31 §5 '변수별 경향(단조 여부)', 기술 통계)."""
    d = np.diff(np.asarray(vals, float))
    if np.all(d == 0):
        return "일정"
    if np.all(d >= 0):
        return "단조 증가"
    if np.all(d <= 0):
        return "단조 감소"
    return "비단조"


def trend_table(effects) -> list[dict]:
    """OFAT 변수별로 수준 순서(기준 수준 포함, 기준 = 0)에 따른 짝 차이 평균과 단조 여부."""
    out = []
    for var in VAR_ORDER:
        for metric in TREND_METRICS:
            rs = [r for r in effects if r["variable"] == var and r["metric"] == metric]
            if not rs:
                continue
            pts = sorted([(BASE_LEVEL[var], 0.0)] + [(r["level"], r["mean"]) for r in rs],
                         key=lambda p: _level_sort_key(var, p[0]))
            out.append({"variable": var, "metric": metric, "levels": [str(p[0]) for p in pts],
                        "means": [float(p[1]) for p in pts], "trend": _monotone([p[1] for p in pts])})
    return out


def analyze_rows(rows, grid) -> dict:
    """한 경기 묶음의 분석 전체 (보고서·CSV·비교가 같은 계산을 쓰도록 한곳에 모은다)."""
    effects, status = effect_table(rows)
    comb = combined_effects(rows, grid["_combined_design"], status)
    return {"checks": integrity(rows), "effects": effects, "status": status, "floor": chaos_floor(rows),
            "env": envelope_table(rows), "comb": comb, "add": additivity(effects, comb, grid),
            "trend": trend_table(effects), "outcome": outcome_table(rows)}


# ======================================================================================
# 그림
# ======================================================================================
def _level_sort_key(var, lev):
    if var == "V6_turb":
        return TURB_ORDER.index(lev)
    return float(lev)


def _insensitive_tag(status, metric) -> str:
    """둔감 지표(A31 §5)면 그림 라벨에 붙일 꼬리표."""
    st = (status or {}).get(metric)
    return "\n(둔감 지표: '차이 없음' 판정 불가)" if st and not st["sensitive"] else ""


def figures(effects, envelope, comb, out_dir, sham_ci, status=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    metrics = [("hp_diff_d8", PRIMARY["hp_diff_d8"]), ("net_wez", PRIMARY["net_wez"]), ("J_q", None)]
    vars_present = [v for v in VAR_ORDER if any(r["variable"] == v for r in effects)]
    if vars_present:
        fig, axes = plt.subplots(len(metrics), len(vars_present), figsize=(2.6 * len(vars_present), 7.5),
                                 squeeze=False, sharey="row")
        for ci, var in enumerate(vars_present):
            for ri, (metric, delta) in enumerate(metrics):
                ax = axes[ri][ci]
                rs = [r for r in effects if r["variable"] == var and r["metric"] == metric]
                pts = [(BASE_LEVEL[var], 0.0, 0.0, 0.0)] + [(r["level"], r["mean"], r["ci_lo"], r["ci_hi"]) for r in rs]
                pts.sort(key=lambda p: _level_sort_key(var, p[0]))
                xs = np.arange(len(pts))
                y = np.array([p[1] for p in pts])
                ax.errorbar(xs, y, yerr=[y - np.array([p[2] for p in pts]), np.array([p[3] for p in pts]) - y],
                            fmt="o-", color="#1f4e79", ms=4, lw=1.2, capsize=2)
                ax.axhline(0, color="k", lw=0.6)
                if delta:
                    ax.axhspan(-delta, delta, color="#2e7d32", alpha=0.12, lw=0)
                    if metric in sham_ci:
                        lo, hi = sham_ci[metric]
                        ax.axhspan(lo, hi, color="grey", alpha=0.18, lw=0, hatch="//")
                ax.set_xticks(xs)
                ax.set_xticklabels([str(p[0]) for p in pts], fontsize=7, rotation=30)
                if ri == 0:
                    ax.set_title(VAR_LABEL[var], fontsize=8)
                if ci == 0:
                    ax.set_ylabel({"hp_diff_d8": "Δ 체력차 [HP]", "net_wez": "Δ WEZ 시간차 [s]",
                                   "J_q": "Δ J_q (경기 중)"}[metric] + _insensitive_tag(status, metric), fontsize=8)
                ax.tick_params(labelsize=7)
        fig.suptitle("변수별 단독 효과 (기준 대비 짝 차이 평균, 95% CI; 녹색 = ±δ, 회색 빗금 = 가짜 짝 CI)", fontsize=9)
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(os.path.join(out_dir, f"fig_dogfight_ofat.{ext}"), dpi=200)
        plt.close(fig)
    # 봉투
    if envelope:
        env = sorted(envelope, key=lambda r: (r["family"] != "baseline", r["setting"]))
        fig, ax = plt.subplots(figsize=(max(6, 0.35 * len(env)), 3.2))
        xs = np.arange(len(env))
        ax.bar(xs, [100 * r["exceed_frac"] for r in env], color=["#c62828" if r["flag"] else "#607d8b" for r in env])
        base_f = next((r["exceed_frac"] for r in env if r["setting"] == BASE), None)
        if base_f is not None:
            ax.axhline(100 * base_f, color="#1565c0", ls="-", lw=0.8)
        ax.axhline(100 * GATE_FRAC, color="k", ls="--", lw=0.8)
        ax.set_xticks(xs)
        ax.set_xticklabels([r["setting"] for r in env], rotation=70, fontsize=6)
        ax.set_ylabel("봉투 초과 경기 [%]", fontsize=8)
        ax.set_title("F-16 봉투 (Nz > 9 / < −3 G 또는 α > 30°). 빨강 = 기준보다 유의하게 더 초과(A33), "
                     "파랑 실선 = 기준, 점선 = 5%", fontsize=8)
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(os.path.join(out_dir, f"fig_dogfight_envelope.{ext}"), dpi=200)
        plt.close(fig)
    # 결합
    if comb:
        fig, axes = plt.subplots(1, len(PRIMARY), figsize=(10, 3.6))
        for ax, metric in zip(axes, PRIMARY):
            e = comb[metric]["effects"]
            names = list(e)
            y = np.array([e[n]["effect"] for n in names])
            lo = np.array([e[n]["ci_lo"] for n in names])
            hi = np.array([e[n]["ci_hi"] for n in names])
            xs = np.arange(len(names))
            ax.errorbar(xs, y, yerr=[y - lo, hi - y], fmt="o", color="#6a1b9a", capsize=2, ms=4)
            ax.axhline(0, color="k", lw=0.6)
            ax.axhspan(-PRIMARY[metric], PRIMARY[metric], color="#2e7d32", alpha=0.12, lw=0)
            ax.set_xticks(xs)
            ax.set_xticklabels(names, rotation=60, fontsize=6)
            ax.set_title(f"결합 설계 효과 — {PRIMARY_LABEL[metric]}{_insensitive_tag(status, metric)}", fontsize=8)
        fig.tight_layout()
        for ext in ("png", "pdf"):
            fig.savefig(os.path.join(out_dir, f"fig_dogfight_combined.{ext}"), dpi=200)
        plt.close(fig)


# ======================================================================================
# 보고서
# ======================================================================================
def _f(x, nd=2):
    return "–" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:+.{nd}f}"


def pilot(dir_):
    rows = load_runs([dir_])
    print("== 무결성 ==")
    for name, ok, ev in integrity(rows):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {ev}")
    S = by_setting(rows)
    for name, M in S.items():
        rs = list(M.values())
        nc = sum(1 for r in rs if r["condition"] == "no_contact")
        zero = sum(1 for r in rs if r["wez_time_blue"] == 0 and r["wez_time_red"] == 0)
        print(f"== {name}: {len(rs)} 경기, 종료 {dict(Counter(r['condition'] for r in rs))}, "
              f"승 {dict(Counter(r['winner'] for r in rs))}, no_contact {nc}, 양측 WEZ 0 {zero}, "
              f"경기당 벽시계 중앙 {np.median([r['wall_s'] for r in rs]):.0f}s")
    base = list(S[BASE].values())
    degenerate = sum(1 for r in base if r["condition"] == "no_contact"
                     or (r["wez_time_blue"] == 0 and r["wez_time_red"] == 0))
    stop = degenerate >= 0.8 * len(base)
    print(f"== A31 §8-2 중단 조건: BASE 퇴화 {degenerate}/{len(base)} → {'중단' if stop else '계속'}")
    if SHAM in S:
        print("== 가짜 짝(기술 통계):", json.dumps(chaos_floor(rows), ensure_ascii=False))
    eff, status = effect_table(rows)
    for r in eff:
        if r["metric"] in PRIMARY:
            print(f"  {r['setting']:>14} {r['metric']:>10}: 평균 {r['mean']:+.2f} [{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}] "
                  f"중앙 {r['median']:+.2f} → {r['judge']}")
    return 1 if stop else 0


def selftest() -> int:
    """정답을 아는 가상 데이터로 판정·부트스트랩·결합 효과 추정을 검증한다 (경기 없음)."""
    from l3_indi.dogfight import load_grid, FACTORS
    ok_all = True

    def check(name, ok, ev=""):
        nonlocal ok_all
        ok_all &= bool(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {ev}")

    check("판정: CI ⊂ ±δ → 차이 없음", judge(-1, 1, 2) == "차이 없음")
    check("판정: CI > δ → 차이 있음", judge(3, 5, 2) == "차이 있음")
    check("판정: CI < −δ → 차이 있음", judge(-5, -3, 2) == "차이 있음")
    check("판정: CI 가 δ 걸침 → 판정 불가", judge(1, 3, 2) == "판정 불가")
    check("판정: 경계 포함(CI = ±δ) → 차이 없음", judge(-2, 2, 2) == "차이 없음")
    a = boot_ci(np.arange(80.0))
    check("부트스트랩: 같은 시드 → 같은 CI", a == boot_ci(np.arange(80.0)), f"{a}")
    check("부트스트랩: 평균 39.5 가 CI 안", a[0] < 39.5 < a[1])

    grid = load_grid()
    design = grid["_combined_design"]
    rng = np.random.default_rng(1)
    rows = []
    ic_eff = rng.normal(0, 30, 80)                       # IC 마다 다른 난이도(짝으로 상쇄되어야 함)

    def mk(name, fam, var, lev, k, y_hp, y_wez):
        r = {"setting_name": name, "family": fam, "variable": var, "level": lev,
             "scenario": f"s{k % 4}", "red": f"r{k // 4 % 5}", "salt": f"t{k // 20}",
             "match_id": f"{name}__{k}", "hp_diff_d8": y_hp, "net_wez": y_wez,
             "winner": "blue", "condition": "timeout", "time_s": 300.0, "hp_blue": 50.0, "hp_red": 50.0,
             "wez_time_blue": 1.0, "wez_time_red": 1.0, "wez_recount_ok": 1}
        for m in REPORTED:
            r[m] = 0.0
        return r
    for d in design:
        c = d["_code"]
        name = BASE if not d["set"] else d["name"]
        for k in range(80):
            y = 10 * c["A"] + 5 * c["C"] + 3 * c["A"] * c["C"] + ic_eff[k] + rng.normal(0, 1)
            rows.append(mk(name, "baseline" if name == BASE else "combined", "combined", d["level"], k, y, 0.01 * y))
    for name, shift in ((SHAM, 0.0), ("V3_lam_25", -40.0), ("V4_async_2t", -40.0), ("V1_kq_1.5", 7.0)):
        for k in range(80):
            y0 = [r for r in rows if r["setting_name"] == BASE and r["match_id"] == f"{BASE}__{k}"][0]["hp_diff_d8"]
            rows.append(mk(name, "sham" if name == SHAM else "ofat", "x", "1", k, y0 + shift, 0.01 * (y0 + shift)))
    eff, status = effect_table(rows)
    g = {(r["setting"], r["metric"]): r for r in eff}
    check("짝 차이: 이동 +7 을 평균으로 복원", abs(g[("V1_kq_1.5", "hp_diff_d8")]["mean"] - 7.0) < 1e-9)
    check("짝 차이: 가짜 짝(이동 0) → 차이 없음", g[(SHAM, "hp_diff_d8")]["judge"] == "차이 없음")
    check("양성 대조(−40) → 감지 가능", status["hp_diff_d8"]["sensitive"])
    comb = combined_effects(rows, design)
    e = comb["hp_diff_d8"]["effects"]
    ac_key = next(k for k in e if "AC" in k.split("="))
    check("결합: 주효과 A = 2×10 = 20", abs(e["A"]["effect"] - 20) < 1.0, f"{e['A']['effect']:.2f}")
    check("결합: 주효과 C = 2×5 = 10", abs(e["C"]["effect"] - 10) < 1.0, f"{e['C']['effect']:.2f}")
    check("결합: 교호작용 A×C(=B×E) = 2×3 = 6", abs(e[ac_key]["effect"] - 6) < 1.0, f"{ac_key} {e[ac_key]['effect']:.2f}")
    check("결합: 효과 없는 인자 B·D·E·F ≈ 0", all(abs(e[f]["effect"]) < 1.0 for f in "BDEF"),
          ", ".join(f"{f} {e[f]['effect']:+.2f}" for f in "BDEF"))
    x16 = comb["hp_diff_d8"]["x16_minus_base"]["mean"]
    check("결합: X16 − 기준 = 2·(10+5) = 30 (A·C 교호작용은 두 칸 모두 +3)", abs(x16 - 30) < 1.0, f"{x16:.2f}")
    # A31 §5 둔감 지표 규칙은 결합 효과의 '차이 없음' 에도 적용된다
    dull = {m: {"calibration_failed": False, "sensitive": False} for m in PRIMARY}
    cd = combined_effects(rows, design, dull)["hp_diff_d8"]["effects"]
    check("결합: 둔감 지표면 '차이 없음'(B·D·E·F) → 판정 불가(둔감 지표)",
          all(cd[f]["judge"] == "차이 없음" and cd[f]["judge_final"] == "판정 불가(둔감 지표)" for f in "BDEF"))
    check("결합: 둔감 지표라도 '차이 있음'(A) 은 그대로", cd["A"]["judge"] == cd["A"]["judge_final"] == "차이 있음")
    cs = combined_effects(rows, design, status)["hp_diff_d8"]["effects"]
    check("결합: 민감 지표면 최종 = 판정", all(e["judge_final"] == e["judge"] for e in cs.values()))
    # 봉투 게이트 (A33): 기준 5% 초과 → 같은 5% 인 설정은 통과, 기준보다 20%p 더 넘는 설정은 표시
    erows = []
    for name, extra in ((BASE, set()), ("E_same", set()), ("E_more", set(range(20, 36))), ("E_less", set())):
        for k in range(80):
            r = mk(name, "baseline" if name == BASE else "ofat", "x", "1", k, 0.0, 0.0)
            hot = (k < 4 and name != "E_less") or k in extra
            r.update(nz_max=9.5 if hot else 8.0, nz_min=-1.0, alpha_max_deg=15.0, p_max_dps=100.0, q_max_dps=30.0,
                     turn_rate_max_dps=15.0, kcas_min=200.0, alt_min_ft=9000.0,
                     red_nz_max=8.0, red_nz_min=-3.5 if k == 0 else -1.0, red_alpha_max_deg=14.0, red_p_max_dps=90.0,
                     red_q_max_dps=25.0, red_turn_rate_max_dps=14.0, red_kcas_min=210.0, red_alt_min_ft=9500.0)
            erows.append(r)
    ev = {r["setting"]: r for r in envelope_table(erows)}
    check("봉투: 기준 초과 5%, 표시 없음", abs(ev[BASE]["exceed_frac"] - 0.05) < 1e-12 and ev[BASE]["flag"] == 0)
    check("봉투: 기준과 같은 초과 → 표시 없음", ev["E_same"]["flag"] == 0 and ev["E_same"]["d_vs_base"] == 0.0)
    check("봉투: 기준보다 +20%p → 표시", ev["E_more"]["flag"] == 1 and abs(ev["E_more"]["d_vs_base"] - 0.2) < 1e-12,
          f"CI [{ev['E_more']['d_ci_lo']:+.3f}, {ev['E_more']['d_ci_hi']:+.3f}]")
    check("봉투: 기준보다 적게 넘음 → 표시 없음", ev["E_less"]["flag"] == 0 and ev["E_less"]["d_vs_base"] < 0)
    check("봉투: 적군 초과는 적군 값으로 따로 (최소 Nz −3.5 인 1/80 경기)",
          abs(ev[BASE]["red_exceed_frac"] - 1 / 80) < 1e-12 and ev[BASE]["red_nz_min_min"] == -3.5)
    # 민감도 δ 는 A31 §4 표의 값 그대로 (WEZ 는 δ/2 = 0.125 가 아니라 0.1)
    row = next(r for r in eff if r["metric"] == "net_wez" and r["setting"] == "V1_kq_1.5")
    check("민감도 δ: 등록값 (4.7, 18.8) / (0.1, 0.5) 로 판정",
          SENS == {"hp_diff_d8": (4.7, 18.8), "net_wez": (0.1, 0.5)}
          and row["judge_sens_lo"] == judge(row["ci_lo"], row["ci_hi"], 0.1)
          and row["judge_sens_hi"] == judge(row["ci_lo"], row["ci_hi"], 0.5))
    check("민감도 δ: CI [−0.11, +0.11] 은 δ 0.1 에서 판정 불가 (0.125 였다면 차이 없음)",
          judge(-0.11, 0.11, SENS["net_wez"][0]) == "판정 불가" and judge(-0.11, 0.11, 0.125) == "차이 없음")
    # 경향(단조 여부)
    check("경향: 단조 증가 / 감소 / 비단조 / 일정",
          _monotone([0, 1, 1, 3]) == "단조 증가" and _monotone([0.5, 0, -2]) == "단조 감소"
          and _monotone([0, 2, 1]) == "비단조" and _monotone([0, 0]) == "일정")
    tr = {(t["variable"], t["metric"]): t for t in trend_table([
        {"setting": "V1_kq_2", "variable": "V1_kq", "level": "2.0", "metric": "net_wez", "mean": -0.3},
        {"setting": "V1_kq_0.5", "variable": "V1_kq", "level": "0.5", "metric": "net_wez", "mean": 0.1},
        {"setting": "V6_turb_severe", "variable": "V6_turb", "level": "severe", "metric": "net_wez", "mean": -0.9},
        {"setting": "V6_turb_light", "variable": "V6_turb", "level": "light", "metric": "net_wez", "mean": 0.2}])}
    check("경향: 기준 수준(0)을 끼워 수준 순서로 정렬",
          tr[("V1_kq", "net_wez")]["levels"] == ["0.5", "1.0", "2.0"] and tr[("V1_kq", "net_wez")]["trend"] == "단조 감소"
          and tr[("V6_turb", "net_wez")]["levels"] == ["none", "light", "severe"]
          and tr[("V6_turb", "net_wez")]["trend"] == "비단조")
    # 승패 분해: 판정패·격추는 진 쪽 기준
    orows = []
    for k, (cond, win) in enumerate([("hard_deck", "red"), ("hard_deck", "blue"), ("health_zero", "red"),
                                     ("stall", "blue"), ("hard_deck", "draw"), ("timeout", "blue"), ("no_contact", "draw")]):
        r = mk(BASE, "baseline", "-", "-", k, 0.0, 0.0)
        r.update(condition=cond, winner=win, wez_censored_blue=1 if cond == "no_contact" else 0)
        orows.append(r)
    o = outcome_table(orows)[0]
    check("승패 분해: 청군 hard deck 1·격추 1, 적군 hard deck 1·실속 1, 동시 1, 시간 1, 무접촉 1, 기타 0",
          (o["blue_lost_hard_deck"], o["blue_lost_health_zero"], o["red_lost_hard_deck"], o["red_lost_stall"],
           o["both_hard_deck"], o["timeout"], o["no_contact"], o["other"]) == (1, 1, 1, 1, 1, 1, 1, 0)
          and (o["blue_win"], o["red_win"], o["draw"]) == (3, 2, 2) and abs(o["blue_wez_censored_frac"] - 1 / 7) < 1e-12)
    print(f"[selftest] {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--pilot", default=None)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--gate-check", action="store_true",
                    help="OFAT 폴더(들)로 A31 §6 게이트만 확인 (결합 실행 전 필수)")
    ap.add_argument("--label", default=None)
    ap.add_argument("--salts", type=int, default=None,
                    help="격자 솔트 앞 N 개만 분석 (A32: A31 원래 등록분 = 4)")
    ap.add_argument("--compare-salts", type=int, default=None,
                    help="전체와 앞 솔트 N 개 분석의 결론 차이 보고서 (A32 §2)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.gate_check:
        return gate_check(args.dirs)
    if args.pilot:
        return pilot(args.pilot)
    if not args.dirs:
        ap.print_help()
        return 0
    if args.compare_salts:
        return compare_salts(args.dirs, args.compare_salts)
    from l3_indi.dogfight import load_grid
    rows = load_runs(args.dirs)
    grid = load_grid()
    if args.salts:
        rows = _first_salts(rows, grid, args.salts)
    a = analyze_rows(rows, grid)
    tag = f"_s{args.salts}" if args.salts else ""
    out_dir = os.path.join(args.dirs[0], "analysis" + tag)
    os.makedirs(out_dir, exist_ok=True)
    sham_ci = {m: (r["ci_lo"], r["ci_hi"]) for r in a["effects"] if r["setting"] == SHAM and r["metric"] in PRIMARY
               for m in [r["metric"]]}
    figures(a["effects"], a["env"], a["comb"], out_dir, sham_ci, a["status"])
    _write_csv(os.path.join(out_dir, "effects.csv"), a["effects"])
    _write_csv(os.path.join(out_dir, "envelope.csv"),
               [dict(r, cond=json.dumps(r["cond"], ensure_ascii=False)) for r in a["env"]])
    _write_csv(os.path.join(out_dir, "outcomes.csv"), a["outcome"])
    _write_csv(os.path.join(out_dir, "trends.csv"),
               [dict(r, levels=json.dumps(r["levels"]), means=json.dumps(r["means"])) for r in a["trend"]])
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"integrity": a["checks"], "status": a["status"], "chaos_floor": a["floor"], "combined": a["comb"],
                   "additivity": a["add"]}, f, ensure_ascii=False, indent=2, default=str)
    label = args.label or f"DOGFIGHT_{_commit10(args.dirs[0])}{tag}"
    rep = os.path.join(HERE, "reports", f"{label}.md")
    write_report(rep, args.dirs, rows, a)
    print("->", rep)
    return 0


def _first_salts(rows, grid, n: int) -> list:
    keep = set(grid["battery"]["salts"][:n])
    out = [r for r in rows if r["salt"] in keep]
    print(f"[분석] 솔트 {sorted(keep)} 만 사용 → {len(out)} 경기")
    return out


def _commit10(d: str) -> str:
    return json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))["git"]["commit"][:10]


def _write_csv(path: str, rows: list) -> None:
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def compare_salts(dirs, n_salts: int) -> int:
    """A32 §2: 주 결과(전체 솔트)와 A31 등록분(앞 솔트 n 개)의 결론이 다른 곳을 모두 표로 낸다."""
    from l3_indi.dogfight import load_grid
    grid = load_grid()
    rows = load_runs(dirs)
    full = analyze_rows(rows, grid)
    sub_rows = _first_salts(rows, grid, n_salts)
    sub = analyze_rows(sub_rows, grid)
    n_full = len(rows) // len({r["setting_name"] for r in rows})
    n_sub = len(sub_rows) // len({r["setting_name"] for r in sub_rows})
    A, B = f"{n_full} 경기", f"{n_sub} 경기"
    L = [f"# 표본 크기에 따른 결론 차이 — {A} (A32 주 결과) vs {B} (A31 등록분, 앞 솔트 {n_salts} 개)\n",
         f"- 같은 데이터·같은 규칙(A31 §5, A33)이다. 차이는 표본 크기뿐이다. 설정당 {A} / {B}.\n",
         "## 1. 주 지표 상태\n", f"| 지표 | 가짜 짝 ({A}) | 가짜 짝 ({B}) | 양성 대조 ({A}) | 양성 대조 ({B}) | 감지 가능 ({A} / {B}) |",
         "|---|---|---|---|---|---|"]
    for m in PRIMARY:
        s, t = full["status"][m], sub["status"][m]
        L.append(f"| {PRIMARY_LABEL[m]} | {s['sham']} | {t['sham']} | "
                 f"{', '.join(f'{k}: {v}' for k, v in s['pc'].items())} | {', '.join(f'{k}: {v}' for k, v in t['pc'].items())} | "
                 f"{'예' if s['sensitive'] else '아니오'} / {'예' if t['sensitive'] else '아니오'} |")
    F = {(r["setting"], r["metric"]): r for r in full["effects"] if r["metric"] in PRIMARY}
    H = {(r["setting"], r["metric"]): r for r in sub["effects"] if r["metric"] in PRIMARY}
    diff = [k for k in sorted(F) if F[k]["judge_final"] != H[k]["judge_final"]]
    L += [f"\n## 2. 설정별 최종 판정이 다른 곳 ({len(diff)} / {len(F)})\n",
          f"| 설정 | 지표 | {A}: 평균 [95% CI] → 최종 | {B}: 평균 [95% CI] → 최종 |", "|---|---|---|---|"]
    for k in diff:
        f, h = F[k], H[k]
        L.append(f"| {k[0]} | {k[1]} | {_f(f['mean'])} [{_f(f['ci_lo'])}, {_f(f['ci_hi'])}] → {f['judge_final']} | "
                 f"{_f(h['mean'])} [{_f(h['ci_lo'])}, {_f(h['ci_hi'])}] → {h['judge_final']} |")
    if full["comb"] and sub["comb"]:
        L += ["\n## 3. 결합 효과 최종 판정이 다른 곳\n", f"| 지표 | 효과 | {A} | {B} |", "|---|---|---|---|"]
        for m in PRIMARY:
            for name, e in full["comb"][m]["effects"].items():
                g = sub["comb"][m]["effects"][name]
                if e["judge_final"] != g["judge_final"]:
                    L.append(f"| {m} | {name} | {_f(e['effect'])} [{_f(e['ci_lo'])}, {_f(e['ci_hi'])}] → {e['judge_final']} | "
                             f"{_f(g['effect'])} [{_f(g['ci_lo'])}, {_f(g['ci_hi'])}] → {g['judge_final']} |")
        L.append("")
        for m in PRIMARY:
            L.append(f"- 가산성 ({m}): {A} 실측 CI 안 = {full['add'][m]['inside_ci']}, {B} = {sub['add'][m]['inside_ci']}")
    E1 = {r["setting"]: r for r in full["env"]}
    E2 = {r["setting"]: r for r in sub["env"]}
    ediff = [k for k in E1 if E1[k]["flag"] != E2[k]["flag"]]
    L += [f"\n## 4. F-16 봉투 표시(A33)가 다른 곳 — 기준 초과 비율 {A} {100 * E1[BASE]['exceed_frac']:.2f}% / "
          f"{B} {100 * E2[BASE]['exceed_frac']:.2f}%\n",
          f"| 설정 | {A}: 초과 / 기준 대비 [95% CI] | {B}: 초과 / 기준 대비 [95% CI] |", "|---|---|---|"]
    for k in ediff:
        a, b = E1[k], E2[k]
        L.append(f"| {k} | {100 * a['exceed_frac']:.1f}% / {100 * a['d_vs_base']:+.1f}%p [{100 * a['d_ci_lo']:+.1f}, "
                 f"{100 * a['d_ci_hi']:+.1f}] {'**표시**' if a['flag'] else '–'} | {100 * b['exceed_frac']:.1f}% / "
                 f"{100 * b['d_vs_base']:+.1f}%p [{100 * b['d_ci_lo']:+.1f}, {100 * b['d_ci_hi']:+.1f}] "
                 f"{'**표시**' if b['flag'] else '–'} |")
    high = combined_high_settings(grid)
    L.append(f"\n- 결합 설계 높음 수준 6 개의 게이트: {A} {'통과' if not any(E1[n]['flag'] for n in high.values()) else '불통과'}, "
             f"{B} {'통과' if not any(E2[n]['flag'] for n in high.values()) else '불통과'}")
    T1 = {(r["variable"], r["metric"]): r["trend"] for r in full["trend"]}
    T2 = {(r["variable"], r["metric"]): r["trend"] for r in sub["trend"]}
    tdiff = [k for k in T1 if T1[k] != T2[k]]
    L += [f"\n## 5. 변수별 경향(단조 여부)이 다른 곳 ({len(tdiff)} / {len(T1)})\n", f"| 변수 | 지표 | {A} | {B} |", "|---|---|---|---|"]
    L += [f"| {k[0]} | {k[1]} | {T1[k]} | {T2[k]} |" for k in tdiff]
    label = f"DOGFIGHT_{_commit10(dirs[0])}_s{n_salts}_vs_full"
    rep = os.path.join(HERE, "reports", f"{label}.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("->", rep)
    return 0


def write_report(path, dirs, rows, a):
    checks, effects, status, floor = a["checks"], a["effects"], a["status"], a["floor"]
    env, comb, add = a["env"], a["comb"], a["add"]
    L = []
    L.append(f"# E층 도그파이트 결과 — {', '.join(os.path.basename(os.path.normpath(os.path.dirname(d))) + '/' + os.path.basename(os.path.normpath(d)) for d in dirs)}\n")
    L.append("- 규칙: 개정 A31 (§4 지표, §5 판정, §6 결합). 짝 = 같은 (시나리오, 레드, 솔트). 통계량 = 짝 차이 평균, "
             f"부트스트랩 95% CI ({N_BOOT:,} 회, 시드 {BOOT_SEED}).")
    L.append(f"- 경기 {len(rows)}, 설정 {len(set(r['setting_name'] for r in rows))}.\n")
    L.append("## 1. 무결성\n")
    L.append("| 검사 | 결과 | 근거 |\n|---|---|---|")
    for name, ok, ev in checks:
        L.append(f"| {name} | {'PASS' if ok else '**FAIL**'} | {ev} |")
    L.append("\n## 2. 카오스 바닥 (가짜 짝 SHAM vs BASE, 기술 통계)\n")
    if floor:
        L.append(f"- 짝 {floor['n']}: 결과가 완전히 같은 짝 {100 * floor['identical_frac']:.0f}%, 승자 뒤집힘 {100 * floor['winner_flip_frac']:.0f}%")
        L.append(f"- |Δ체력차| p50 {floor['abs_dhp_p50']:.1f} / p95 {floor['abs_dhp_p95']:.1f} HP, "
                 f"|ΔWEZ 시간차| p50 {floor['abs_dwez_p50']:.2f} / p95 {floor['abs_dwez_p95']:.2f} s")
    L.append("\n## 3. 주 지표 판정 상태\n")
    L.append("| 지표 | δ | 가짜 짝 판정 | 보정 | 양성 대조 판정 | 감지 가능 |\n|---|---|---|---|---|---|")
    for m, st in status.items():
        L.append(f"| {PRIMARY_LABEL[m]} | {PRIMARY[m]} | {st['sham']} | {'실패 → 제외' if st['calibration_failed'] else '통과'} | "
                 f"{', '.join(f'{k}: {v}' for k, v in st['pc'].items())} | {'예' if st['sensitive'] else '아니오'} |")
    for m in PRIMARY:
        lo_d, hi_d = SENS[m]
        L.append(f"\n## 4. 설정별 효과 — {PRIMARY_LABEL[m]} (δ = {PRIMARY[m]}; 민감도 δ = {lo_d} / {hi_d})\n")
        L.append(f"| 설정 | 변수 | 수준 | 짝 | 평균 차 | 95% CI | 중앙 차 | 판정 (δ {PRIMARY[m]}) | δ {lo_d} | δ {hi_d} | 최종 |"
                 "\n|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted((r for r in effects if r["metric"] == m), key=lambda r: (r["family"], r["variable"], r["setting"])):
            L.append(f"| {r['setting']} | {r['variable']} | {r['level']} | {r['n']} | {_f(r['mean'])} | "
                     f"[{_f(r['ci_lo'])}, {_f(r['ci_hi'])}] | {_f(r['median'])} | {r['judge']} | {r['judge_sens_lo']} | "
                     f"{r['judge_sens_hi']} | **{r['judge_final']}** |")
    L.append("\n## 4b. 변수별 경향 (A31 §5 '단조 여부', 기술 통계)\n")
    L.append("- 수준 순서대로 짝 차이 평균(점추정)을 늘어놓았다. 기준 수준은 0 이다. 단조 여부는 점추정의 인접 차이 부호로만 정한다(CI 는 §4).\n")
    L.append("| 변수 | 지표 | 수준 → 평균 차 | 경향 |\n|---|---|---|---|")
    for t in a["trend"]:
        seq = ", ".join(f"{lv}: {mv:+.3g}" for lv, mv in zip(t["levels"], t["means"]))
        L.append(f"| {VAR_LABEL[t['variable']]} | {t['metric']} | {seq} | {t['trend']} |")
    L.append("\n## 5. 보고 지표 (판정 없음, 짝 차이 평균 [95% CI])\n")
    L.append("- `t_first_wez_blue`: 청군이 WEZ 에 한 번도 들지 못한 경기는 종료 시각으로 **검열**된 값이다. "
             "`wez_censored_blue` 열이 그 검열 비율의 변화다(A31 §4 '검열 표시'). 설정별 검열 비율 자체는 §5b.\n")
    L.append("| 설정 | " + " | ".join(REPORTED) + " |\n|---|" + "---|" * len(REPORTED))
    names = sorted({r["setting"] for r in effects}, key=lambda n: (n != SHAM, n))
    for n in names:
        cells = []
        for m in REPORTED:
            r = next((x for x in effects if x["setting"] == n and x["metric"] == m), None)
            cells.append("–" if r is None else f"{r['mean']:+.3g} [{r['ci_lo']:+.3g}, {r['ci_hi']:+.3g}]")
        L.append(f"| {n} | " + " | ".join(cells) + " |")
    L.append("\n## 5b. 승패와 종료 사유 분해 (경기 수, 기술 통계)\n")
    L.append("- 판정패(hard deck·실속)와 격추(health_zero)는 **진 쪽** 기준이다. 양측이 같은 틱에 걸리면 무승부로 따로 센다.\n")
    L.append("| 설정 | 경기 | 청군 승 | 적군 승 | 무 | 청군 패: hard deck / 실속 / 격추 | 적군 패: hard deck / 실속 / 격추 | "
             "양측 동시 | 시간 종료 | 무접촉 | 기타 | 청군 WEZ 미진입(검열) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for o in sorted(a["outcome"], key=lambda r: (r["family"] != "baseline", r["setting"])):
        both = sum(o[f"both_{c}"] for c in FORFEIT_CONDS)
        L.append(f"| {o['setting']} | {o['n']} | {o['blue_win']} | {o['red_win']} | {o['draw']} | "
                 f"{o['blue_lost_hard_deck']} / {o['blue_lost_stall']} / {o['blue_lost_health_zero']} | "
                 f"{o['red_lost_hard_deck']} / {o['red_lost_stall']} / {o['red_lost_health_zero']} | {both} | "
                 f"{o['timeout']} | {o['no_contact']} | {o['other']} | {100 * o['blue_wez_censored_frac']:.1f}% |")
    L.append("\n## 6. F-16 성능 봉투 (A33 ⚠ 게이트: Nz > 9 / < −3 G 또는 α > 30° 인 경기 여부의 기준 대비 짝 차이, "
             "95% CI 하한 > 0 이면 표시. A31 §5 원래 규칙 = 절대 비율 > 5%)\n")
    L.append("| 설정 | 초과 비율 | 기준 대비 [%p] | 95% CI | 표시 (A33) | 절대 > 5% (A31) | 최대 Nz | 최소 Nz | α 최대 p95 / 최대 [°] | "
             "최대 롤율 [°/s] | 최대 피치율 [°/s] | 선회율 p95 / 최대 [°/s] | 최저 KCAS | 최저 고도 [ft] | 종료 사유 |"
             "\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(env, key=lambda r: (r["family"] != "baseline", r["setting"])):
        rel = ("–", "–") if r["setting"] == BASE else \
            (f"{100 * r['d_vs_base']:+.1f}", f"[{100 * r['d_ci_lo']:+.1f}, {100 * r['d_ci_hi']:+.1f}]")
        L.append(f"| {r['setting']} | {100 * r['exceed_frac']:.1f}% | {rel[0]} | {rel[1]} | "
                 f"{'**초과**' if r['flag'] else '–'} | {'예' if r['flag_abs'] else '–'} | {r['nz_max_max']:.2f} | "
                 f"{r['nz_min_min']:.2f} | {r['alpha_max_p95']:.1f} / {r['alpha_max_max']:.1f} | {r['p_max_max']:.0f} | "
                 f"{r['q_max_max']:.0f} | {r['turn_rate_max_p95']:.1f} / {r['turn_rate_max_max']:.1f} | {r['kcas_min_min']:.0f} | "
                 f"{r['alt_min_min']:.0f} | {r['cond']} |")
    L.append("\n## 6b. 적군 봉투 (A31 §4 '청군·적군', 판정 없음)\n")
    L.append("- 적군에는 설정을 주입하지 않는다(난류도 청군만). 같은 정의(Nz > 9 / < −3 G 또는 α > 30°)의 초과 비율을 참고로 싣는다.\n")
    L.append("| 설정 | 초과 비율 | 최대 Nz | 최소 Nz | α 최대 [°] | 최대 롤율 [°/s] | 최대 피치율 [°/s] | 선회율 최대 [°/s] | "
             "최저 KCAS | 최저 고도 [ft] |\n|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(env, key=lambda r: (r["family"] != "baseline", r["setting"])):
        L.append(f"| {r['setting']} | {100 * r['red_exceed_frac']:.1f}% | {r['red_nz_max_max']:.2f} | {r['red_nz_min_min']:.2f} | "
                 f"{r['red_alpha_max_max']:.1f} | {r['red_p_max_max']:.0f} | {r['red_q_max_max']:.0f} | "
                 f"{r['red_turn_rate_max_max']:.1f} | {r['red_kcas_min_min']:.0f} | {r['red_alt_min_min']:.0f} |")
    if comb:
        for m in PRIMARY:
            L.append(f"\n## 7. 결합 설계 — {PRIMARY_LABEL[m]}\n")
            L.append("| 효과 | 추정 | 95% CI | 판정 | 최종 |\n|---|---|---|---|---|")
            for name, e in comb[m]["effects"].items():
                L.append(f"| {name} | {_f(e['effect'])} | [{_f(e['ci_lo'])}, {_f(e['ci_hi'])}] | {e['judge']} | "
                         f"**{e.get('judge_final', e['judge'])}** |")
            o = comb[m]["x16_minus_base"]
            L.append(f"\n- 전부 높음(X16) − 기준: {_f(o['mean'])} [{_f(o['ci_lo'])}, {_f(o['ci_hi'])}]")
            if add:
                a = add[m]
                L.append(f"- 가산성: OFAT 단독 효과 합 {_f(a['predicted_sum'])} → 실측 CI 안 = {a['inside_ci']} "
                         f"(단독 효과: {', '.join(f'{k} {_f(v)}' for k, v in a['ofat_parts'].items())})")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
