"""P0 동결 검증 — results/exploratory/ 의 각 파일을 **현재 커밋 코드로 다시 생성해** 대조한다.

"이 파일은 이 코드로 만들어졌다" 를 주장하지 않고 실행으로 확인한다.

· 생성 스크립트가 있는 파일: 임시 디렉터리로 재실행 → 원본과 셀 단위 대조
  (요약 CSV 의 wall_time_s 는 벽시계라 제외. 시계열 CSV 는 SHA-256 전체 비교).
· 생성 스크립트가 없는 파일(고아): 재현 불가로 기록하되, 다른 파일과 겹치는 값이
  있으면 교차 일치 여부를 확인해 기록한다.
· 결과: results/exploratory/MANIFEST.csv, results/exploratory/README.md
· 마지막에 데이터 파일을 읽기 전용으로 바꾼다.

사용: python scripts/freeze_exploratory.py        (전체 약 5분)
"""
from __future__ import annotations

import csv
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EX = os.path.join(REPO, "results", "exploratory")
SCRIPTS = os.path.join(REPO, "scripts")
PY = sys.executable
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, REPO)


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()


def gen_commit(gen: str) -> str:
    """생성 스크립트 파일을 마지막으로 바꾼 커밋 (워킹트리와 다르면 '(dirty)')."""
    script = os.path.join("scripts", gen.split()[0])
    if not os.path.exists(os.path.join(REPO, script)):
        return ""
    h = subprocess.check_output(["git", "log", "-1", "--format=%h", "--", script], cwd=REPO, text=True).strip()
    return h + (" (dirty)" if git_dirty([script]) else "")


def git_dirty(paths) -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=REPO, text=True)
    return bool(out.strip())


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def n_rows(path: str) -> int:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return max(0, sum(1 for _ in f) - 1)


def run(cmd, cwd=REPO):
    r = subprocess.run([PY, *cmd], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{cmd} 실패:\n{r.stderr[-2000:]}")


def compare_csv(orig: str, new: str, skip=("wall_time_s",)) -> str:
    """셀 단위 대조. 반환: 'identical' | 'identical_except_walltime' | 'DIFF: ...'"""
    if sha256(orig) == sha256(new):
        return "identical"
    with open(orig, newline="", encoding="utf-8-sig") as f:
        A = list(csv.reader(f))
    with open(new, newline="", encoding="utf-8-sig") as f:
        B = list(csv.reader(f))
    if len(A) != len(B):
        return f"DIFF: rows {len(A)-1} vs {len(B)-1}"
    # 열 구성이 달라도(구버전 스키마) 공통 열의 값이 같으면 "값 재현" 으로 본다.
    bidx = {c: i for i, c in enumerate(B[0])}
    common = [(i, bidx[c]) for i, c in enumerate(A[0]) if c in bidx and c not in skip]
    only_old = [c for c in A[0] if c not in bidx]
    bad = [(ri, A[0][ai]) for ri in range(1, len(A)) for ai, bi in common if A[ri][ai] != B[ri][bi]]
    if bad:
        cols = sorted({c for _, c in bad})
        return f"DIFF: {len(bad)} cells in {len({r for r,_ in bad})} rows, cols={cols[:6]}"
    if A[0] != B[0]:
        return (f"values_identical_older_schema (공통 {len(common)}열 전부 일치; 현행 코드는 "
                f"{len(B[0])}열, 구본 {len(A[0])}열; 구본에만 있는 열 {only_old})")
    return "identical_except_walltime"


# --------------------------------------------------------------------------------------
# 파일별 메타데이터 (조건은 스크립트 원문을 읽어 확인한 값, docs/FINDINGS 3절과 동일)
# --------------------------------------------------------------------------------------
C_STEP_10K = "10000ft/350KCAS, 뱅크스텝, 8s, throttle 0.8, shim k_att 4.5"
C_CORNER = "15000ft/400KCAS, 80deg뱅크 지속선회, 12s, throttle 1.0, shim k_att 4.0"
YAW_DAMP = "요 감쇠 r_sp=-1.5r (배치 법칙과 동일)"
YAW_TAN = "g*tan(phi)/V (잘못된 식)"
G_KIN = "기구학 n_act (Nz 대비 최대 26% 과대)"
G_NZ = "accelerations/Nz"

ENTRIES = [
    # (상대경로, 생성 명령 or None, 조건, 요축, G 계산, 알려진 문제)
    ("indi_step_sweep/summary.csv", "run_indi_step_sweep.py", C_STEP_10K, YAW_DAMP, G_KIN,
     "G 관련 열(g_exceeded 등) 절대값 무효"),
    ("indi_step_sweep/timeseries.csv", "run_indi_step_sweep.py", C_STEP_10K, YAW_DAMP, G_KIN, ""),
    ("indi_step_limiter_compare/summary.csv", "run_indi_step_sweep.py --limiter-compare",
     C_STEP_10K, YAW_DAMP, G_KIN, "리미터 on/off 결과 완전 동일 (널 결과)"),
    ("indi_step_limiter_compare/timeseries.csv", "run_indi_step_sweep.py --limiter-compare",
     C_STEP_10K, YAW_DAMP, G_KIN, ""),
    ("corner_pull_sweep/summary.csv", "run_corner_pull_sweep.py", C_CORNER, YAW_DAMP, G_KIN,
     "7G/9G 목표 도달 불가 -> 54/100행 settle 검열; overshoot_g/g_exceeded 절대값 무효"),
    ("corner_pull_sweep/timeseries.csv", "run_corner_pull_sweep.py", C_CORNER, YAW_DAMP, G_KIN, ""),
    ("indi_step_sweep_coordinated/summary.csv", "run_indi_step_sweep_coordinated.py",
     C_STEP_10K, YAW_TAN, G_KIN, "요축 지령식 오류 (tan); 2026-09-14 16:25 재생성본(구본 덮어씀)"),
    ("indi_step_sweep_coordinated/timeseries.csv", "run_indi_step_sweep_coordinated.py",
     C_STEP_10K, YAW_TAN, G_KIN, ""),
    ("indi_step_sweep_coordinated_15k400/summary.csv",
     "run_indi_step_sweep_coordinated.py --alt-ft 15000 --kcas 400",
     "15000ft/400KCAS, 뱅크스텝, 8s, throttle 0.8, shim k_att 4.5", YAW_TAN, G_KIN, "요축 지령식 오류 (tan)"),
    ("indi_step_sweep_coordinated_15k400/timeseries.csv",
     "run_indi_step_sweep_coordinated.py --alt-ft 15000 --kcas 400",
     "15000ft/400KCAS, 뱅크스텝, 8s, throttle 0.8, shim k_att 4.5", YAW_TAN, G_KIN, ""),
    ("heading_rate_verification.csv", "verify_heading_rate.py", C_STEP_10K, YAW_TAN, "해당없음", ""),
    ("stability_filter_map.csv", "run_stability_filter_map.py", C_CORNER + ", G5 고정",
     YAW_DAMP, G_KIN, "overshoot_g 기구학; lag_q_s 는 xcorr_peak<0.8 이면 무의미"),
    ("rudder_authority_analysis.csv", "run_rudder_authority.py",
     "15000ft/400,450KCAS, 뱅크스텝 30-60deg, 10s, throttle 0.8, shim k_att 4.5",
     "5종 대조(tan/sin/kin/beta0/zero)", "해당없음", "beta0 PI 는 수렴 못함(명령 포화)"),
    ("g_onset_sweep_15k400/summary.csv", "run_g_onset_sweep.py --kcas 400",
     "15000ft/400KCAS, 순수당김 3s, throttle 1.0, shim k_att 4.0", YAW_DAMP, G_NZ + " (기구학 병기)",
     "lag_q_s 대부분 0 또는 500ms 클립 -> 사용 불가"),
    ("g_onset_sweep_15k400/timeseries.csv", "run_g_onset_sweep.py --kcas 400",
     "15000ft/400KCAS, 순수당김 3s, throttle 1.0, shim k_att 4.0", YAW_DAMP, G_NZ, ""),
    ("g_onset_sweep_15k450/summary.csv", "run_g_onset_sweep.py --kcas 450",
     "15000ft/450KCAS, 순수당김 3s, throttle 1.0, shim k_att 4.0", YAW_DAMP, G_NZ + " (기구학 병기)",
     "lag_q_s 사용 불가"),
    ("g_onset_sweep_15k450/timeseries.csv", "run_g_onset_sweep.py --kcas 450",
     "15000ft/450KCAS, 순수당김 3s, throttle 1.0, shim k_att 4.0", YAW_DAMP, G_NZ, ""),
    ("stability_boundary_summary.csv", "(고아) run_corner_pull_sweep.run_one 재구성으로 대조",
     C_CORNER + ", G5 고정", YAW_DAMP, G_KIN, "원 생성 스크립트 없음"),
    ("stability_boundary_summary_classified.csv", "classify_stability_bands.py",
     C_CORNER + ", G5 고정", YAW_DAMP, G_KIN, "임계 1.5 는 이 30조합으로 교정(교정=적용 데이터)"),
    ("repeat_variance.csv", None, "indi_step bank45_k1_f25 / corner_pull G5_k1_f25 10회 반복",
     YAW_DAMP, G_KIN, "원 생성 스크립트 없음"),
    ("envelope_violation_scan.csv", None, C_CORNER, YAW_DAMP, G_KIN,
     "원 생성 스크립트 없음; 기구학 G 기반 포락선 위반 -> 무효"),
    ("rudder_zero_compare.csv", None, C_STEP_10K, YAW_DAMP + " / 러더 0", G_KIN,
     "원 생성 스크립트 없음; heading_drift_deg_8s 열 psi wrap 버그"),
    ("coordinated_vs_original_compare.csv", None, C_STEP_10K, "원본 vs 협조선회(구버전)", G_KIN,
     "원 생성 스크립트 없음; 협조선회판 구버전 기준"),
    ("corner_pull_diag/G5_k2_f25_diag_timeseries.csv", None, C_CORNER, YAW_DAMP, G_KIN, "원 생성 스크립트 없음"),
    ("corner_pull_diag/G5_k2_f35_diag_timeseries.csv", None, C_CORNER, YAW_DAMP, G_KIN, "원 생성 스크립트 없음"),
    ("corner_pull_diag/G5_k2_f50_diag_timeseries.csv", None, C_CORNER, YAW_DAMP, G_KIN, "원 생성 스크립트 없음"),
    ("g_envelope_output.txt", "measure_g_envelope.py (stdout)",
     "봉투 격자 10/15/25kft x 200-500KCAS 등", "해당없음", "해당없음",
     "텍스트 덤프(표 아님); 논문용은 CSV 로 재측정 필요"),
]


def reproduce_all(tmp: str) -> dict:
    """생성 명령별로 한 번씩 재실행. {상대경로: 재생성 파일 경로}"""
    out = {}
    S = lambda n: os.path.join(SCRIPTS, n)

    def sweep(dirname, args):
        d = os.path.join(tmp, dirname)
        run([S(args[0]), *args[1:], "--out-dir", d])
        out[f"{dirname}/summary.csv"] = os.path.join(d, "summary.csv")
        out[f"{dirname}/timeseries.csv"] = os.path.join(d, "timeseries.csv")

    t = time.perf_counter()
    sweep("indi_step_sweep", ["run_indi_step_sweep.py"])
    sweep("indi_step_limiter_compare", ["run_indi_step_sweep.py", "--limiter-compare"])
    sweep("corner_pull_sweep", ["run_corner_pull_sweep.py"])
    sweep("indi_step_sweep_coordinated", ["run_indi_step_sweep_coordinated.py"])
    sweep("indi_step_sweep_coordinated_15k400",
          ["run_indi_step_sweep_coordinated.py", "--alt-ft", "15000", "--kcas", "400"])
    for kc in ("400", "450"):
        sweep(f"g_onset_sweep_15k{kc}", ["run_g_onset_sweep.py", "--kcas", kc])
        stray = os.path.join(REPO, "results", f"g_onset_15k{kc}_summary.csv")   # 스크립트가 쓰는 사본
        if os.path.exists(stray):
            os.remove(stray)
    print(f"  sweeps done ({time.perf_counter()-t:.0f}s)")

    # 출력 경로가 고정된 스크립트: 실행 후 임시로 옮긴다
    for script, fname in (("verify_heading_rate.py", "heading_rate_verification.csv"),
                          ("run_rudder_authority.py", "rudder_authority_analysis.csv")):
        run([S(script)])
        src = os.path.join(REPO, "results", fname)
        dst = os.path.join(tmp, fname)
        shutil.move(src, dst)
        out[fname] = dst

    p = os.path.join(tmp, "stability_filter_map.csv")
    run([S("run_stability_filter_map.py"), "--out", p])
    out["stability_filter_map.csv"] = p

    p = os.path.join(tmp, "stability_boundary_summary_classified.csv")
    run([S("classify_stability_bands.py"), "--in",
         os.path.join(EX, "stability_boundary_summary.csv"), "--out", p])
    out["stability_boundary_summary_classified.csv"] = p

    # 고아 stability_boundary: 원 격자를 run_one 으로 재구성
    from run_corner_pull_sweep import run_one, SUMMARY_HEADER
    import contextlib, io
    p = os.path.join(tmp, "stability_boundary_summary.csv")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_HEADER)
        w.writeheader()
        for k in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
            for fz in (10.0, 15.0, 25.0, 35.0, 50.0):
                with contextlib.redirect_stdout(io.StringIO()):
                    _, s = run_one(5.0, k, fz)
                w.writerow(s)
    out["stability_boundary_summary.csv"] = p
    print(f"  all reproductions done ({time.perf_counter()-t:.0f}s)")
    return out


def orphan_cross_checks() -> dict:
    """고아 파일의 값이 재현 가능한 파일과 겹치는지 확인."""
    res = {}
    rd = lambda rel: list(csv.DictReader(open(os.path.join(EX, rel), newline="", encoding="utf-8-sig")))
    step = {r["run_id"]: r for r in rd("indi_step_sweep/summary.csv")}
    corner = {r["run_id"]: r for r in rd("corner_pull_sweep/summary.csv")}

    rv = [r for r in rd("repeat_variance.csv") if r["experiment"] in ("indi_step", "corner_pull")]
    s, c = step["bank45_k1_f25"], corner["G5_k1_f25"]
    exp = {"indi_step": (s["settle_time_s"], s["overshoot_deg"], s["rms_total_dps"]),
           "corner_pull": (c["settle_time_s"], c["overshoot_g"], c["rms_q_tracking_dps"])}
    ok = all((r["settle_time_or_field1"], r["overshoot_or_field2"], r["rms_or_field3"]) == exp[r["experiment"]]
             for r in rv if r["rep"].isdigit())
    res["repeat_variance.csv"] = ("교차일치: indi_step bank45_k1_f25 / corner_pull G5_k1_f25 값과 동일"
                                  if ok else "교차불일치")

    ev = rd("envelope_violation_scan.csv")
    bad = 0
    for r in ev:
        src = corner if r["experiment"] == "corner_pull_sweep" else step
        t = src.get(r["run_id"])
        if t is None or any(r[k] != t[k2] for k, k2 in (("oscillating", "oscillating"),
                                                          ("max_g_exceed_pos", "max_g_exceed_pos"),
                                                          ("max_g_exceed_neg", "max_g_exceed_neg"))):
            bad += 1
    res["envelope_violation_scan.csv"] = (f"교차일치: {len(ev)}행 전부 sweep summary 값과 동일(파생 표)"
                                          if bad == 0 else f"교차불일치 {bad}/{len(ev)}행")

    rz = rd("rudder_zero_compare.csv")
    keymap = {"settle_time_s": "settle_time_s", "overshoot_deg": "overshoot_deg",
              "sat_rudder_pct": "sat_rudder_pct", "rms_total_dps": "rms_total_dps"}
    base = [r for r in rz if r["zero_rudder"] == "False"]
    bad = sum(1 for r in base for k, k2 in keymap.items()
              if r[k] != step[f"bank{float(r['bank_deg']):g}_k1_f25"][k2])
    res["rudder_zero_compare.csv"] = (f"부분 교차일치: zero_rudder=False {len(base)}행이 indi_step_sweep 과 동일, "
                                      f"True 행은 대조 대상 없음" if bad == 0 else f"교차불일치 {bad}셀")

    cvo = rd("coordinated_vs_original_compare.csv")
    res["coordinated_vs_original_compare.csv"] = (
        f"대조 불가: version 값 {sorted({r['version'] for r in cvo})}, 구버전 협조선회판 기준")

    # corner_pull_diag 시계열 vs corner_pull_sweep 시계열 (같은 run_id 의 omega_q, cmd_elevator)
    ts = {}
    with open(os.path.join(EX, "corner_pull_sweep", "timeseries.csv"), newline="") as f:
        for r in csv.DictReader(f):
            if r["run_id"] in ("G5_k2_f25", "G5_k2_f35", "G5_k2_f50"):
                ts.setdefault(r["run_id"], []).append(r)
    for rid in ("G5_k2_f25", "G5_k2_f35", "G5_k2_f50"):
        rel = f"corner_pull_diag/{rid}_diag_timeseries.csv"
        d = rd(rel)
        cols = [c for c in ("omega_q_dps", "cmd_elevator", "omega_sp_q_dps") if c in d[0]]
        n = min(len(d), len(ts.get(rid, [])))
        bad = sum(1 for i in range(n) for c in cols if abs(float(d[i][c]) - float(ts[rid][i][c])) > 1e-6)
        res[rel] = (f"교차일치: {n}스텝 x {cols} 가 corner_pull_sweep 시계열과 동일"
                    if bad == 0 and n == len(d) else f"교차불일치 {bad}셀 / {n}스텝")
    return res


def main() -> int:
    gens = sorted({os.path.join("scripts", g.split()[0]) for _, g, *_ in ENTRIES
                   if g and not g.startswith("(")} | {"scripts/sweep_diagnostics.py"})
    if git_dirty(gens):
        print("생성 스크립트에 커밋 안 된 변경이 있음 — 커밋 후 실행할 것:", gens)
        return 2
    head = git_head()
    print(f"[freeze] code commit {head}")
    tmp = tempfile.mkdtemp(prefix="freeze_")
    try:
        repro = reproduce_all(tmp)
        cross = orphan_cross_checks()

        # g_envelope_output.txt: 표준출력 재실행 대조 (엔진 배너 줄 제외)
        # 원본(추적 파일)은 콘솔 인코딩을 설정하지 않아 cp949 파이프에서 em-dash 로 죽는다.
        # 스크립트는 건드리지 않고 자식 프로세스 환경만 UTF-8 로 지정한다.
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PY, os.path.join(SCRIPTS, "measure_g_envelope.py")], cwd=REPO, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise RuntimeError("measure_g_envelope.py 실패: " + r.stderr[-1500:])
        noise = ("JSBSim", "Engine ", "[JSBSim-ML", "startup")
        clean = lambda s: [ln.rstrip() for ln in s.splitlines() if ln.strip() and not any(x in ln for x in noise)]
        new_txt = clean(r.stdout)
        old_txt = clean(open(os.path.join(EX, "g_envelope_output.txt"), encoding="utf-8", errors="replace").read())
        env_status = ("identical_text" if new_txt == old_txt else
                      f"DIFF: {sum(1 for a, b in zip(old_txt, new_txt) if a != b)}줄 다름, "
                      f"길이 {len(old_txt)} vs {len(new_txt)}")

        rows = []
        for rel, gen, cond, yaw, gcalc, issues in ENTRIES:
            path = os.path.join(EX, rel)
            if rel == "g_envelope_output.txt":
                status = env_status
            elif rel in repro:
                status = compare_csv(path, repro[rel])
            else:
                status = "재현불가(생성 스크립트 없음); " + cross.get(rel, "")
            rows.append({
                "file": rel, "sha256": sha256(path),
                "rows": n_rows(path) if rel.endswith(".csv") else "",
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))),
                "generator": gen or "(없음)",
                "code_commit": gen_commit(gen) if gen and not gen.startswith("(") else "",
                "repro_status": status,
                "conditions": cond, "yaw_law": yaw, "g_calc": gcalc, "known_issues": issues,
                "paper_use": "금지 — 탐색 단계 자료 (docs/EXPERIMENT_PLAN.md §6)",
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    man = os.path.join(EX, "MANIFEST.csv")
    if os.path.exists(man):
        os.chmod(man, stat.S_IWRITE | stat.S_IREAD)
    with open(man, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    for r in rows:
        print(f"  {r['file']:<52} {r['repro_status']}")

    # 동결: 데이터 파일 읽기 전용
    for dp, _, fs in os.walk(EX):
        for fn in fs:
            if fn not in ("MANIFEST.csv", "README.md"):
                os.chmod(os.path.join(dp, fn), stat.S_IREAD)
    print(f"\n-> {man}\n[freeze] data files set read-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
