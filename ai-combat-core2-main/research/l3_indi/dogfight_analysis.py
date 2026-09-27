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
PRIMARY_LABEL = {"hp_diff_d8": "종료 체력차 [HP] (D8)", "net_wez": "WEZ 체류시간 차 [s]"}
POSITIVE_CONTROLS = ("V3_lam_25", "V4_async_2t")      # A31 §5
SHAM = "SHAM"
BASE = "BASE"
GATE_NZ_MAX, GATE_NZ_MIN, GATE_ALPHA_DEG, GATE_FRAC = 9.0, -3.0, 30.0, 0.05   # A31 §5 (사전등록 §7.1·§8)
REPORTED = ("blue_pts", "frac_ata30_blue", "frac_slant_band", "frac_ata_band_blue",
            "frac_fight_speed_blue", "frac_corner_blue", "kcas_mean_blue", "dalt_blue_ft",
            "t_first_wez_blue", "J_q", "corr_q", "q_gain", "sat_ele")
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
                row["judge_half"] = judge(lo, hi, dl / 2)
                row["judge_double"] = judge(lo, hi, dl * 2)
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


def _exceed(r) -> bool:
    """한 경기의 봉투 초과 (A31 §5 정의: 청군 Nz > +9 / < −3 G 또는 α > 30°)."""
    return (r["nz_max"] > GATE_NZ_MAX) or (r["nz_min"] < GATE_NZ_MIN) or (r["alpha_max_deg"] > GATE_ALPHA_DEG)


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
                    "turn_rate_max_p95": float(np.percentile([r["turn_rate_max_dps"] for r in rs], 95)),
                    "kcas_min_min": min(r["kcas_min"] for r in rs),
                    "cond": dict(Counter(r["condition"] for r in rs))})
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
            r.update(nz_max=9.5 if hot else 8.0, nz_min=-1.0, alpha_max_deg=15.0, p_max_dps=100.0,
                     turn_rate_max_dps=15.0, kcas_min=200.0)
            erows.append(r)
    ev = {r["setting"]: r for r in envelope_table(erows)}
    check("봉투: 기준 초과 5%, 표시 없음", abs(ev[BASE]["exceed_frac"] - 0.05) < 1e-12 and ev[BASE]["flag"] == 0)
    check("봉투: 기준과 같은 초과 → 표시 없음", ev["E_same"]["flag"] == 0 and ev["E_same"]["d_vs_base"] == 0.0)
    check("봉투: 기준보다 +20%p → 표시", ev["E_more"]["flag"] == 1 and abs(ev["E_more"]["d_vs_base"] - 0.2) < 1e-12,
          f"CI [{ev['E_more']['d_ci_lo']:+.3f}, {ev['E_more']['d_ci_hi']:+.3f}]")
    check("봉투: 기준보다 적게 넘음 → 표시 없음", ev["E_less"]["flag"] == 0 and ev["E_less"]["d_vs_base"] < 0)
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
    from l3_indi.dogfight import load_grid
    rows = load_runs(args.dirs)
    grid = load_grid()
    if args.salts:
        keep = set(grid["battery"]["salts"][:args.salts])
        rows = [r for r in rows if r["salt"] in keep]
        print(f"[분석] 솔트 {sorted(keep)} 만 사용 → {len(rows)} 경기")
    checks = integrity(rows)
    effects, status = effect_table(rows)
    floor = chaos_floor(rows)
    env = envelope_table(rows)
    comb = combined_effects(rows, grid["_combined_design"], status)
    add = additivity(effects, comb, grid)
    tag = f"_s{args.salts}" if args.salts else ""
    out_dir = os.path.join(args.dirs[0], "analysis" + tag)
    os.makedirs(out_dir, exist_ok=True)
    sham_ci = {m: (r["ci_lo"], r["ci_hi"]) for r in effects if r["setting"] == SHAM and r["metric"] in PRIMARY
               for m in [r["metric"]]}
    figures(effects, env, comb, out_dir, sham_ci, status)
    with open(os.path.join(out_dir, "effects.csv"), "w", newline="", encoding="utf-8") as f:
        keys = sorted({k for r in effects for k in r})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(effects)
    with open(os.path.join(out_dir, "envelope.csv"), "w", newline="", encoding="utf-8") as f:
        keys = [k for k in env[0] if k != "cond"] + ["cond"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in env:
            w.writerow(dict(r, cond=json.dumps(r["cond"], ensure_ascii=False)))
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"integrity": checks, "status": status, "chaos_floor": floor, "combined": comb,
                   "additivity": add}, f, ensure_ascii=False, indent=2, default=str)
    commit = json.load(open(os.path.join(args.dirs[0], "manifest.json"), encoding="utf-8"))["git"]["commit"]
    label = args.label or f"DOGFIGHT_{commit[:10]}{tag}"
    rep = os.path.join(HERE, "reports", f"{label}.md")
    write_report(rep, args.dirs, rows, checks, effects, status, floor, env, comb, add)
    print("->", rep)
    return 0


def write_report(path, dirs, rows, checks, effects, status, floor, env, comb, add):
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
        L.append(f"\n## 4. 설정별 효과 — {PRIMARY_LABEL[m]} (δ = {PRIMARY[m]})\n")
        L.append("| 설정 | 변수 | 수준 | 짝 | 평균 차 | 95% CI | 중앙 차 | 판정 | δ/2 | 2δ | 최종 |\n|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted((r for r in effects if r["metric"] == m), key=lambda r: (r["family"], r["variable"], r["setting"])):
            L.append(f"| {r['setting']} | {r['variable']} | {r['level']} | {r['n']} | {_f(r['mean'])} | "
                     f"[{_f(r['ci_lo'])}, {_f(r['ci_hi'])}] | {_f(r['median'])} | {r['judge']} | {r['judge_half']} | "
                     f"{r['judge_double']} | **{r['judge_final']}** |")
    L.append("\n## 5. 보고 지표 (판정 없음, 짝 차이 평균 [95% CI])\n")
    L.append("| 설정 | " + " | ".join(REPORTED) + " |\n|---|" + "---|" * len(REPORTED))
    names = sorted({r["setting"] for r in effects}, key=lambda n: (n != SHAM, n))
    for n in names:
        cells = []
        for m in REPORTED:
            r = next((x for x in effects if x["setting"] == n and x["metric"] == m), None)
            cells.append("–" if r is None else f"{r['mean']:+.3g} [{r['ci_lo']:+.3g}, {r['ci_hi']:+.3g}]")
        L.append(f"| {n} | " + " | ".join(cells) + " |")
    L.append("\n## 6. F-16 성능 봉투 (A33 ⚠ 게이트: Nz > 9 / < −3 G 또는 α > 30° 인 경기 여부의 기준 대비 짝 차이, "
             "95% CI 하한 > 0 이면 표시. A31 §5 원래 규칙 = 절대 비율 > 5%)\n")
    L.append("| 설정 | 초과 비율 | 기준 대비 [%p] | 95% CI | 표시 (A33) | 절대 > 5% (A31) | 최대 Nz | 최소 Nz | α 최대 p95 / 최대 [°] | 최대 롤율 [°/s] | 선회율 p95 [°/s] | 최저 KCAS | 종료 사유 |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(env, key=lambda r: (r["family"] != "baseline", r["setting"])):
        rel = ("–", "–") if r["setting"] == BASE else \
            (f"{100 * r['d_vs_base']:+.1f}", f"[{100 * r['d_ci_lo']:+.1f}, {100 * r['d_ci_hi']:+.1f}]")
        L.append(f"| {r['setting']} | {100 * r['exceed_frac']:.1f}% | {rel[0]} | {rel[1]} | "
                 f"{'**초과**' if r['flag'] else '–'} | {'예' if r['flag_abs'] else '–'} | {r['nz_max_max']:.2f} | "
                 f"{r['nz_min_min']:.2f} | {r['alpha_max_p95']:.1f} / {r['alpha_max_max']:.1f} | {r['p_max_max']:.0f} | "
                 f"{r['turn_rate_max_p95']:.1f} | {r['kcas_min_min']:.0f} | {r['cond']} |")
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
