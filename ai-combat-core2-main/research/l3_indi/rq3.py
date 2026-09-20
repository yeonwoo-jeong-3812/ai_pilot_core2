"""RQ3 — 내부 루프(INDI) 충실도가 기수 지향·기동유형 실현으로 어떻게 이어지는가 (사전등록 A24 + A25).

구조
  1) 적 궤적: E1 직진 / E2 우선회 / E3 좌선회 — 청군과 독립이므로 (조건·패턴·기하·길이)마다 한 번만 계산해 모든 설정이 공유한다.
  2) 청군
       P (주, A25)   : 배치된 L2 `BFMGuidance`(lead pursuit 고정, BT 미사용)로 적을 추격. 25 s.
       B (충실도 축) : 고정 시퀀스 — [1,3) 우선회 +60° → t=3 반전 −60° → t=6 뱅크 유지 + Nz 0.9·C_nz. 15 s.
       A (부록 대조) : 고정 시퀀스 단일 당김 — 유도 없이는 M층 신호가 없음을 보이는 음성 대조. 15 s.
       C (보조)      : 적 없음, 뱅크 45°/70° + Nz 0.9·C_nz — 선회율 경쟁(방위 90°·180° 도달).
       D (부록 롤)   : 적이 평면 밖 — 롤로 평면 정렬 후 당김. S2·S3·S5 만.
  3) 지표: M층(ATA 최소·T_ATA30·평균 지향오차), 기동유형 충실도(flow 일치·전환 지연·궤적 편차), T층 부지표, 대가(ΔKCAS·Δ고도).

사용: python research/l3_indi/rq3.py --pilot --geom <geometries.json>
      python research/l3_indi/rq3.py --geom <geometries.json>
      python research/l3_indi/rq3.py --analyze <results dir>
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import REPO, DT, Condition, Params, Uncertainty, build, run, gcmd   # noqa: E402

DUR_GUIDED = 25.0                                        # A25-2(b)
DUR_OPEN = 15.0
SETTINGS = {"S3": ((1.0, 1.5, 0.5), 15.0, 1.0), "S2": ((1.0, 1.0, 1.0), 25.0, 1.0),
            "S4": ((1.0, 1.0, 1.0), 25.0, 4.0), "S1p": ((1.0, 1.0, 1.0), 25.0, 10.0),
            "S5": ((1.0, 1.0, 1.0), 25.0, 25.0)}
KCAS_SET = (250.0, 350.0, 400.0)
ALT_FT = 14000.0
ENEMIES = {"E1": 0.0, "E2": 60.0, "E3": -60.0}           # 적 뱅크 목표 [deg] (0 = 직진)
ENEMY_NZ = 2.0
TURN_DIR_MIN_DPS = 3.0                                   # Pilot._turn_dir 과 같은 규칙
TURN_DIR_HZ = 20.0
FLOW_HOLD_S = 0.5                                        # A24-6(b) 연속 유지 요건
FIDELITY_WIN = (1.0, 15.0)                               # A25-2(e) 궤적 편차 창
ALPHA_EXCLUDE_DEG = 30.0                                 # A25-2(c) 이탈 제외 규칙
WEZ_ATA_DEG, WEZ_TIER10, WEZ_MIN_FT, WEZ_MAX_FT = 30.0, 10.0, 500.0, 3000.0
B_BANKS = (45.0, 60.0, 75.0)                             # A26-2(a) 충실도 축의 독립 반복
ATA30_MIN_START = 30.0                                   # T_ATA30 은 시작 ATA 가 이보다 큰 기하에서만 정의


# ======================================================================================
# 명령 — 고정 시퀀스 (부록 A·B, 보조 C, 부록 D)
# ======================================================================================
class FixedSequence:
    """고정 시퀀스 기동. steps = [(t_start, bank_deg, nz_mode)] — nz_mode: 'level' 또는 C_nz 배율."""

    def __init__(self, steps, c_nz, name="seq", duration_s=DUR_OPEN):
        self.steps = steps
        self.c_nz = c_nz
        self.name = name
        self.duration_s = duration_s
        self.per_tick = False

    def window(self):
        return (0.0, self.duration_s)

    def _active(self, t):
        cur = self.steps[0]
        for s in self.steps:
            if t >= s[0] - 1e-9:
                cur = s
        return cur

    def command(self, t, k, st):
        _, bank, nz_mode = self._active(t)
        target = np.deg2rad(bank)
        # 유지 국면: 수평 유지 Nz. 단 φ₀ > 90° 기하가 있으므로 2 G 로 상한을 둔다(A24-11).
        nz = (min(1.0 / max(float(np.cos(st["phi"])), 0.2), 2.0) if nz_mode == "level"
              else float(nz_mode) * self.c_nz)
        return gcmd(target - st["phi"], nz, st)


class PursuitScript:
    """A25-2(a): 배치된 L2(BFMGuidance)로 스크립트 적기를 추격. L1(BT)은 쓰지 않는다.

    적 상태는 미리 계산된 배열에서 읽으므로 설정 간 입력이 완전히 같다.
    """

    def __init__(self, red, duration_s=DUR_GUIDED, pursuit="lead"):
        from aircombat.guidance.bfm_guidance import BFMGuidance
        self.red, self.duration_s, self.pursuit = red, duration_s, pursuit
        self.g = BFMGuidance()
        self.per_tick = False
        self.rig = None

    def window(self):
        return (0.0, self.duration_s)

    def command(self, t, k, st):
        from aircombat.guidance.bfm_guidance import AircraftKinematics
        r, P = self.red, self.rig.plant
        j = min(k, len(r["t"]) - 1)
        me = AircraftKinematics(
            pos_ned=np.array(self.rig.pilot._pos, float),
            vel_ned=np.array([P["velocities/v-north-fps"], P["velocities/v-east-fps"],
                              P["velocities/v-down-fps"]], float),
            phi=st["phi"], theta=st["theta"], psi=st["psi"],
            v_fps=st["vt"], kcas=st["kcas"], q=st["q"])
        fp = np.array([r["px"][j], r["py"][j], r["pz"][j]], float)
        fv = np.array([r["vn"][j], r["ve"][j], r["vd"][j]], float)
        return self.g.compute(me, fp, fv, pursuit=self.pursuit,
                              foe_theta=float(r["theta"][j]), foe_psi=float(r["psi"][j]))


def maneuver_for(kind: str, cap: dict, bank0: float):
    c = cap["C_nz"]
    if kind == "A":                     # 부록 대조: 단일 당김 (뱅크 유지 + 1 s 후 당김)
        return FixedSequence([(0.0, bank0, "level"), (1.0, bank0, 0.9)], c, "A")
    if kind.startswith("B"):            # 충실도 축: 우선회 → 반전 → 당김 (뱅크 크기 A26-2(a))
        b = float(kind.split("_")[1]) if "_" in kind else 60.0
        return FixedSequence([(0.0, 0.0, "level"), (1.0, b, "level"),
                              (3.0, -b, "level"), (6.0, -b, 0.9)], c, kind)
    if kind.startswith("C"):            # 보조: 선회율 경쟁 (적 없음)
        b = float(kind.split("_")[1])
        return FixedSequence([(0.0, b, "level"), (1.0, b, 0.9)], c, kind)
    if kind == "D":                     # 부록: 평면 밖 → 롤 정렬 후 당김
        return FixedSequence([(0.0, 0.0, "level"), (1.0, 80.0, "level"), (3.0, 80.0, 0.9)], c, "D")
    raise KeyError(kind)


# ======================================================================================
# 실행
# ======================================================================================
def fly(cond: Condition, man, k_scale, filt, lam_q, pos0=(0.0, 0.0, 0.0), psi0_deg=0.0):
    """한 기체를 비행시키고 참 궤적을 돌려준다. pos0 = (N, E, D) [ft], D 는 기준 고도로부터 아래로."""
    alt = cond.alt_ft - pos0[2]
    with contextlib.redirect_stdout(io.StringIO()):
        rig = build(Condition(alt, cond.kcas, psi_deg=psi0_deg),
                    Params(k_scale=tuple(k_scale), filt_hz=filt),
                    Uncertainty(g0_row_scale=(1.0, lam_q, 1.0)))
        rig.pilot._pos[0] += pos0[0]
        rig.pilot._pos[1] += pos0[1]
        if isinstance(man, PursuitScript):
            man.rig = rig
        ts = run(rig, man)
    # harness 는 위치를 기록하지 않으므로 NED 속도를 적분해 복원 (Pilot 과 같은 오일러 적분)
    v = np.stack([ts["vn"], ts["ve"], ts["vd"]], axis=1)
    p0 = np.array([pos0[0], pos0[1], -alt], float)
    pos = p0 + np.cumsum(v, axis=0) * DT
    out = {c: ts[c] for c in ts if c != "_meta"}
    out["px"], out["py"], out["pz"] = pos[:, 0], pos[:, 1], pos[:, 2]
    return out


def enemy_track(cond: Condition, ekind: str, cap: dict, psi0_deg: float, pos0, dur: float):
    bank = ENEMIES[ekind]
    steps = [(0.0, bank, "level")] if bank == 0.0 else [(0.0, bank, ENEMY_NZ / cap["C_nz"])]
    man = FixedSequence(steps, cap["C_nz"], f"enemy_{ekind}", duration_s=dur)
    return fly(cond, man, (1.0, 1.0, 1.0), 25.0, 1.0, pos0=pos0, psi0_deg=psi0_deg)


# ======================================================================================
# 기하·충실도
# ======================================================================================
def geometry_series(blue: dict, red: dict):
    from aircombat.geometry.combat_geometry import CombatGeometry
    from aircombat.geometry.units import M_TO_FT
    FT_TO_M = 1.0 / M_TO_FT
    n = min(len(blue["t"]), len(red["t"]))
    ata = np.full(n, np.nan)
    rng = np.full(n, np.nan)
    for k in range(n):
        pb = np.array([blue["px"][k], blue["py"][k], blue["pz"][k]])
        pr = np.array([red["px"][k], red["py"][k], red["pz"][k]])
        vb = np.array([blue["vn"][k], blue["ve"][k], blue["vd"][k]])
        vr = np.array([red["vn"][k], red["ve"][k], red["vd"][k]])
        g = CombatGeometry(pb * FT_TO_M, pr * FT_TO_M, vb * FT_TO_M, vr * FT_TO_M,
                           blue["phi"][k], blue["theta"][k], blue["psi"][k], red["theta"][k], red["psi"][k])
        ata[k] = g.ata_deg()
        rng[k] = float(np.linalg.norm(pr - pb))
    return ata, rng


def geom_at(blue: dict, red: dict, k: int):
    """한 틱의 (ATA, AA, 거리) — 시작 기하가 의도대로 실현됐는지 확인용."""
    from aircombat.geometry.combat_geometry import CombatGeometry
    from aircombat.geometry.units import M_TO_FT
    f = 1.0 / M_TO_FT
    pb = np.array([blue["px"][k], blue["py"][k], blue["pz"][k]]) * f
    pr = np.array([red["px"][k], red["py"][k], red["pz"][k]]) * f
    vb = np.array([blue["vn"][k], blue["ve"][k], blue["vd"][k]]) * f
    vr = np.array([red["vn"][k], red["ve"][k], red["vd"][k]]) * f
    g = CombatGeometry(pb, pr, vb, vr, blue["phi"][k], blue["theta"][k], blue["psi"][k],
                       red["theta"][k], red["psi"][k])
    return float(g.ata_deg()), float(g.aa_deg()), float(np.linalg.norm(pr - pb) * M_TO_FT)


def turn_dir_series(psi: np.ndarray) -> np.ndarray:
    """Pilot._turn_dir 과 같은 규칙: 20 Hz 헤딩 차분, |ψ̇| > 3 deg/s 일 때만 ±1."""
    step = int(round((1.0 / TURN_DIR_HZ) / DT))
    out = np.zeros(len(psi), int)
    for k in range(step, len(psi)):
        d = np.degrees((psi[k] - psi[k - step] + np.pi) % (2 * np.pi) - np.pi) * TURN_DIR_HZ
        out[k] = 1 if d > TURN_DIR_MIN_DPS else (-1 if d < -TURN_DIR_MIN_DPS else 0)
    return out


def flow_series(blue: dict, red: dict) -> list[str]:
    """aircombat.tactics.conditions 의 판정 함수를 그대로 사용."""
    from aircombat.tactics.conditions import one_circle, two_circle

    class Ctx:
        __slots__ = ("my_turn_dir", "foe_turn_dir")

    mine = turn_dir_series(blue["psi"])
    foe = turn_dir_series(red["psi"])
    ctx = Ctx()
    out = []
    for k in range(min(len(mine), len(foe))):
        ctx.my_turn_dir, ctx.foe_turn_dir = int(mine[k]), int(foe[k])
        out.append("one" if one_circle(ctx) else ("two" if two_circle(ctx) else "none"))
    return out


def first_time(mask: np.ndarray, t: np.ndarray, censor: float) -> float:
    idx = np.nonzero(mask)[0]
    return float(t[idx[0]]) if len(idx) else censor


def ideal_track(ts: dict, pdot_max: float, qdot_max: float):
    """A24-7: ω_sp 를 각가속도 한계로만 따라간 이상 응답 → 헤딩·위치 궤적."""
    n = len(ts["t"])
    p = np.zeros(n); q = np.zeros(n)
    for k in range(1, n):
        p[k] = p[k - 1] + np.clip(ts["sp_p"][k] - p[k - 1], -np.deg2rad(pdot_max) * DT, np.deg2rad(pdot_max) * DT)
        q[k] = q[k - 1] + np.clip(ts["sp_q"][k] - q[k - 1], -np.deg2rad(qdot_max) * DT, np.deg2rad(qdot_max) * DT)
    phi = ts["phi"][0] + np.cumsum(p) * DT
    # 자세 → 비행경로: 속도 크기는 실제 런에서 빌린다 (A24-7 근사)
    V = np.sqrt(ts["vn"] ** 2 + ts["ve"] ** 2 + ts["vd"] ** 2)
    gamma = np.arcsin(np.clip(-ts["vd"][0] / max(V[0], 1e-6), -1, 1))
    psi = np.zeros(n); psi[0] = ts["psi"][0]
    gam = np.full(n, gamma)
    for k in range(1, n):
        psid = q[k] * np.sin(phi[k]) / max(np.cos(gam[k - 1]), 0.2)
        gamd = q[k] * np.cos(phi[k])
        psi[k] = psi[k - 1] + psid * DT
        gam[k] = gam[k - 1] + gamd * DT
    vel = np.stack([V * np.cos(gam) * np.cos(psi), V * np.cos(gam) * np.sin(psi), -V * np.sin(gam)], axis=1)
    pos = np.array([ts["px"][0], ts["py"][0], ts["pz"][0]]) + np.cumsum(vel, axis=0) * DT
    return psi, pos


# ======================================================================================
# 한 런
# ======================================================================================
def job_fn(job):
    from l3_indi.design import capability
    from l3_indi import metrics as M
    cond = Condition(ALT_FT, job["kcas"])
    cap = capability(cond)
    k, filt, lam = SETTINGS[job["setting"]]
    dur = job["dur"]
    row = {kk: job[kk] for kk in job if not kk.startswith("_")}
    row["C_nz"] = cap["C_nz"]

    if job["kind"] == "P":
        red = cached_track(job)
        man = PursuitScript(red, duration_s=dur)
    else:
        red = cached_track(job) if job["enemy"] != "none" else None
        man = maneuver_for(job["kind"], cap, job["bank0"])
        man.duration_s = dur
    blue = fly(cond, man, k, filt, lam)
    t = blue["t"]
    w = (1.0, dur)

    # T층 부지표와 제외 규칙 (A25-2(c))
    row["J_q"] = M.tracking_J(blue, "q", w)
    row["J_p"] = M.tracking_J(blue, "p", w)
    row["oscillating"] = M.oscillation(blue, DT)["oscillating"]
    row["departure"] = M.departure(blue)
    row["alpha_max_deg"] = float(np.max(np.rad2deg(blue["alpha"])))
    row["excluded"] = int(row["departure"] >= 1 or row["alpha_max_deg"] > ALPHA_EXCLUDE_DEG)
    row["nz_max"] = float(np.max(blue["nz"]))
    row["nz_mean"] = float(np.mean(blue["nz"][t >= 1.0]))
    qq, sq = np.abs(np.rad2deg(blue["q"])), np.abs(np.rad2deg(blue["sp_q"]))
    m1 = t >= 1.0
    row["q_gain"] = float(np.mean(qq[m1]) / max(np.mean(sq[m1]), 1e-9))      # 과응답 배율
    # 대가
    row["dkcas"] = float(blue["kcas"][-1] - blue["kcas"][0])
    row["dalt_ft"] = float(blue["alt"][-1] - blue["alt"][0])
    # 선회율 경쟁 (적 불필요)
    dpsi = np.abs(np.rad2deg(np.unwrap(blue["psi"]) - np.unwrap(blue["psi"])[0]))
    row["T_psi90"] = first_time(dpsi >= 90.0, t, dur)
    row["T_psi180"] = first_time(dpsi >= 180.0, t, dur)
    # 이상 응답 대비 궤적 편차 (충실도 (c), 창 고정 A25-2(e))
    psi_i, pos_i = ideal_track(blue, job["pdot_max"], job["qdot_max"])
    lo, hi = FIDELITY_WIN[0], min(FIDELITY_WIN[1], dur)
    m = (t >= lo) & (t <= hi)
    kend = int(np.nonzero(m)[0][-1])
    row["dev_heading_rms_deg"] = float(np.sqrt(np.mean((np.rad2deg(np.unwrap(blue["psi"]) - np.unwrap(psi_i))[m]) ** 2)))
    row["dev_pos_end_ft"] = float(np.linalg.norm(
        np.array([blue["px"][kend], blue["py"][kend], blue["pz"][kend]]) - pos_i[kend]))

    if red is None:
        return row

    ata, rng = geometry_series(blue, red)
    n = len(ata)
    tt = t[:n]
    mw = tt >= 1.0
    row["ata0"], row["aa0"], row["range0_ft"] = geom_at(blue, red, 0)
    # M층 주 지표 (A25-2(d))
    row["ata_min"] = float(np.nanmin(ata))
    row["ata_mean"] = float(np.nanmean(ata[mw]))
    row["T_ata30"] = (first_time(ata <= WEZ_ATA_DEG, tt, dur)
                      if row["ata0"] > ATA30_MIN_START else float("nan"))
    # 보조
    row["T_ata10"] = first_time(ata <= WEZ_TIER10, tt, dur)
    wez = (ata <= WEZ_ATA_DEG) & (rng >= WEZ_MIN_FT) & (rng <= WEZ_MAX_FT)
    row["T_wez"] = first_time(wez, tt, dur)
    row["wez_s"] = float(np.sum(wez) * DT)
    row["ata_end"] = float(ata[-1])
    row["range_min_ft"] = float(np.nanmin(rng))
    row["range_end_ft"] = float(rng[-1])
    k1 = int(round(1.0 / DT))
    los = np.array([red["px"][k1] - blue["px"][k1], red["py"][k1] - blue["py"][k1], red["pz"][k1] - blue["pz"][k1]])
    ph, th, ps = blue["phi"][k1], blue["theta"][k1], blue["psi"][k1]
    yb = np.array([np.sin(ph) * np.sin(th) * np.cos(ps) - np.cos(ph) * np.sin(ps),
                   np.sin(ph) * np.sin(th) * np.sin(ps) + np.cos(ph) * np.cos(ps), np.sin(ph) * np.cos(th)])
    row["plane_off_t1_deg"] = float(np.degrees(np.arcsin(
        abs(float(np.dot(los / np.linalg.norm(los), yb / np.linalg.norm(yb)))))))

    want = job["flow_intent"]
    if want == "na":                       # 적이 직진(E1)이거나 단일 당김이면 flow 가 정의되지 않는다
        row["flow_match_frac"] = float("nan")
        row["flow_switch_delay_s"] = float("nan")
        return row
    flow = flow_series(blue, red)
    after = int(round(job["switch_t"] / DT))
    seg = flow[after:n]
    row["flow_match_frac"] = float(np.mean([f == want for f in seg])) if seg else float("nan")
    need = int(round(FLOW_HOLD_S / DT))
    delay = dur
    run_len = 0
    for i, f in enumerate(seg):
        run_len = run_len + 1 if f == want else 0
        if run_len >= need:
            delay = (i - need + 1) * DT
            break
    row["flow_switch_delay_s"] = delay
    return row


_TRACK_CACHE = {}


def cached_track(job):
    """적 궤적 — (조건·패턴·기하·뱅크·길이)마다 한 번만 계산해 모든 설정이 공유 (A24-5)."""
    key = (job["kcas"], job["enemy"], job["geom"], job["bank0"], job["dur"])
    if key in _TRACK_CACHE:
        return _TRACK_CACHE[key]
    from l3_indi.design import capability
    cond = Condition(ALT_FT, job["kcas"])
    g = job["_geom"]
    # 적 초기 위치 (A24-11): 뱅크 φ₀ 가 정하는 **양력 평면 안**, 청군 기수에서 ATA₀ 떨어진 방향, 거리 R₀.
    #   LOS = cos(ATA)·x_b − sin(ATA)·z_b, 청군은 ψ=0·θ=0·φ=φ₀ → y_b 성분 0 (평면 내).
    ata, phi = np.deg2rad(g["ata_deg"]), np.deg2rad(job["bank0"])
    los = np.array([np.cos(ata), np.sin(ata) * np.sin(phi), -np.sin(ata) * np.cos(phi)])
    pos0 = tuple(g["range_ft"] * los)
    psi0 = g["ata_deg"] + g["aa_deg"]      # CombatGeometry.aa_deg 규약에 맞춘 적 헤딩 (수평 투영 근사)
    red = enemy_track(cond, job["enemy"], capability(cond), psi0, pos0, job["dur"])
    _TRACK_CACHE[key] = red
    return red


# ======================================================================================
def _flow_intent(kind: str, enemy: str) -> str:
    """B 는 t=3 s 에 좌선회로 반전한다 → 우선회 적(E2)과는 one_circle, 좌선회 적(E3)과는 two_circle."""
    if kind.startswith("B"):
        return "one" if enemy == "E2" else ("two" if enemy == "E3" else "na")
    if kind == "D":                        # 우뱅크 80° 정렬 후 당김 → 우선회
        return "two" if enemy == "E2" else ("one" if enemy == "E3" else "na")
    return "na"


def build_jobs(geoms, pilot: bool):
    from l3_indi.ideal_share import open_loop_limits
    lim = open_loop_limits()
    settings = ("S2", "S5") if pilot else tuple(SETTINGS)
    kcas_list = (350.0,) if pilot else KCAS_SET
    gs = geoms[:2] if pilot else geoms
    enemies = ("E1", "E2") if pilot else tuple(ENEMIES)
    jobs = []
    for kcas in kcas_list:
        L = lim[(ALT_FT, kcas)]
        base = {"kcas": kcas, "pdot_max": L["p"], "qdot_max": L["q"]}
        for s in settings:
            for g in gs:
                for e in enemies:
                    for kind in ("P", "A"):
                        jobs.append(dict(base, setting=s, geom=g["id"], enemy=e, kind=kind,
                                         bank0=g["bank_deg"], switch_t=1.0,
                                         flow_intent=_flow_intent(kind, e),
                                         dur=DUR_GUIDED if kind == "P" else DUR_OPEN, _geom=g))
            # 충실도 축 B: 청군이 적을 보지 않으므로 기하 대신 뱅크 크기로 반복을 만든다 (A26-2(a)).
            #   적 위치는 flow 판정에만 쓰이며, 기준 기하 G1 위치를 공통으로 쓴다.
            for bmag in B_BANKS:
                for e in ("E2", "E3"):
                    kind = f"B_{bmag:g}"
                    jobs.append(dict(base, setting=s, geom=geoms[0]["id"], enemy=e, kind=kind,
                                     bank0=geoms[0]["bank_deg"], switch_t=3.0,
                                     flow_intent=_flow_intent(kind, e), dur=DUR_OPEN, _geom=geoms[0]))
            if pilot:
                continue
            for bank in (45.0, 70.0):
                jobs.append(dict(base, setting=s, geom="-", enemy="none", kind=f"C_{bank:g}",
                                 bank0=bank, switch_t=1.0, flow_intent="na", dur=DUR_OPEN, _geom=None))
            if s in ("S2", "S3", "S5"):
                for g in geoms[:2]:
                    for e in ("E2", "E3"):
                        jobs.append(dict(base, setting=s, geom=g["id"], enemy=e, kind="D",
                                         bank0=80.0, switch_t=1.0, flow_intent=_flow_intent("D", e),
                                         dur=DUR_OPEN, _geom=g))
    return jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--geom", default=None, help="geometries.json 경로")
    ap.add_argument("--analyze", default=None)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    if args.analyze:
        from l3_indi.rq3_analysis import analyze
        analyze(args.analyze, label=args.label or "RQ3")
        return 0
    geoms = json.load(open(args.geom, encoding="utf-8"))
    from l3_indi.runner import run_experiment
    jobs = build_jobs(geoms, args.pilot)
    name = "rq3_pilot" if args.pilot else "rq3"
    out = run_experiment(name, jobs, job_fn, os.path.join(REPO, "results", "paper"))
    print("->", out, len(jobs), "runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
