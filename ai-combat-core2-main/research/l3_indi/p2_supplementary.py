"""P2 보충 분석 — 사전등록(A7) 밖. 보고서가 드러낸 설계 문제 3가지를 실측으로 확인한다.

  (a) 기동 사건 중 능력표 격자(8~24 kft, 200~500 KCAS) 밖 비율과 격자 안 사건만의 C_nz 비율
  (b) 당김 사건 틱 중 |p_sp| >= 30 deg/s 비율 (당김 도중 롤이 G 포착 시간으로 덮어써진 정도)
  (c) RQ1 후보 조건 9개에서 합성 기동 M1~M3 의 능력 제한 플래그(§3.2)

사용: python research/l3_indi/p2_supplementary.py   (궤적 296ce41ff0, 능력표 05b869f2e4 기준)
"""
import sys, io, contextlib, csv, glob, json, os
import numpy as np
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "research")); sys.stdout.reconfigure(encoding="utf-8")
from l3_indi import taxonomy as T, metrics as M
from l3_indi.harness import build, run, Condition, DT
from l3_indi.maneuvers import M2RollReversal, M3RollingPull, M1NzCapture
EV = list(csv.DictReader(open(os.path.join(R, "results/paper/taxonomy/296ce41ff0/events.csv"), encoding="utf-8")))
print("== (a) 능력표 격자 밖 사건 비율 ==")
for t in ("g_capture", "rolling_pull"):
    E = [e for e in EV if e["type"] == t]
    ins = [e for e in E if e["cap_inside_grid"] == "1"]
    nf = np.array([float(e["nz_frac"]) for e in ins])
    alt = np.array([float(e["alt_ft"]) for e in E]); kc = np.array([float(e["kcas"]) for e in E])
    print(f"  {t}: 격자 안 {len(ins)}/{len(E)} ({100*len(ins)/len(E):.1f}%) | 고도<8k {100*np.mean(alt<8000):.1f}%, >24k {100*np.mean(alt>24000):.1f}%, "
          f"KCAS<200 {100*np.mean(kc<200):.1f}%, >500 {100*np.mean(kc>500):.1f}% | 격자 안 nz_frac p10/50/90 "
          f"{np.percentile(nf,10):.2f}/{np.percentile(nf,50):.2f}/{np.percentile(nf,90):.2f}, >1.0 비율 {100*np.mean(nf>1):.1f}%")
    b = np.array([float(e["bank_abs_median_deg"]) for e in E])
    if t == "g_capture":
        print(f"     G 포착 |뱅크| 중앙값 분포: <15° {100*np.mean(b<15):.1f}%, 15-45° {100*np.mean((b>=15)&(b<45)):.1f}%, "
              f"45-90° {100*np.mean((b>=45)&(b<90)):.1f}%, ≥90° {100*np.mean(b>=90):.1f}%")
print("\n== (b) 당김 사건 틱 중 |p_sp|≥30 dps (당김 중 롤) 비율 ==")
class Cap:
    def c_nz(self, a, k): return 7.0, True
acc = {"g_capture": [0, 0], "rolling_pull": [0, 0]}
files = sorted(glob.glob(os.path.join(R, "results/paper/traces/296ce41ff0/npz/*.npz")))
for fp in files[::4]:              # 110경기 표본(4경기마다 1경기)
    z = np.load(fp)
    for side in ("blue", "red"):
        lab, ev, _ = T.classify_side(z, side, Cap())
        psp = np.abs(np.rad2deg(np.asarray(z[f"{side}__sp_p"], float)))
        for L in acc:
            m = lab == L
            acc[L][0] += int(np.sum(m & (psp >= 30))); acc[L][1] += int(np.sum(m))
for L, (a, b) in acc.items():
    print(f"  {L}: {100*a/b:.1f}% ({a}/{b} 틱, {len(files[::4])}경기 표본)")
print("\n== (c) 선택 조건 9개에서 합성 기동의 능력 제한 플래그 (§3.2 규칙) ==")
cap = {(int(r["alt_kft"]), int(r["kcas"])): r for r in csv.DictReader(open(os.path.join(R, "research/l3_indi/reports/capability_05b869f2e4.csv"), encoding="utf-8")) if r["fbw_override"] == "0"}
for a in (8, 14, 24):
    for k in (250, 350, 400):
        cp, cnz = float(cap[(a, k)]["C_p"]), float(cap[(a, k)]["C_nz"])
        out = []
        for man in (M2RollReversal(), M3RollingPull(nz_target=0.6 * cnz), M1NzCapture(nz_target=0.6 * cnz)):
            with contextlib.redirect_stdout(io.StringIO()):
                ts = run(build(Condition(a * 1000.0, float(k))), man)
            w = man.window(); m = M.window_mask(ts, w)
            over = float(np.mean(np.abs(np.rad2deg(ts["sp_p"][m])) > 0.95 * cp))
            out.append(f"{man.name} 제한={M.capability_limited(ts, w, cp)}(초과시간 {100*over:.0f}%, max|p_sp| {np.max(np.abs(np.rad2deg(ts['sp_p'][m]))):.0f})")
        print(f"  {a}kft/{k}KCAS C_p={cp:.0f} C_nz={cnz:.2f}: " + "; ".join(out))
