"""L3 INDI 실험 하네스 — 배치된 Pilot 을 그대로 쓰고 L2 출력만 합성 기동으로 바꾼다.

원칙 (docs/PREREGISTRATION.md §1, §2)
------------------------------------
* 제어 루프를 다시 구현하지 않는다. `factory.make_pilot` → `Pilot.setup()` 으로 조립하고
  매 틱 `Pilot.control_step` → `Pilot.step_physics` 를 호출한다. 틱 순서와 L2 영차 유지(60 Hz)는
  `aircombat/engine/match.py` 의 루프와 같다.
* 원본 파일은 수정하지 않는다. 연구 인자와 교란은 전부 **바깥에서** 넣는다.
    - k_rate / filt_hz : setup 이 식별한 G0·qbar_ref·트림 조종면으로 `INDIRateController` 재생성
    - G0 오차          : 재생성 시 제어기에 넘기는 G0 만 변형 (플랜트는 참 그대로)
    - 센서 잡음 / 지연 : `pilot.plant` 를 `PlantProxy` 로 교체 — 제어기가 읽는 값과 쓰는 입력만 바뀐다
    - 지령 기록        : `pilot.limiter.limit_omega_sp` 를 인스턴스 수준에서 감싸 통과값을 기록
* 지표용 로그는 **항상 참 플랜트**에서 읽는다 (잡음·지연 없음).
* G0 식별은 잡음·지연을 붙이기 **전에**, 참 플랜트에서 끝난다.
"""
from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
os.environ.setdefault("AICOMBAT_ALLOW_CUSTOM", "1")

from aircombat.control.indi import INDIRateController          # noqa: E402
from aircombat.control.limiter import G_FT_S2                  # noqa: E402
from aircombat.engine.factory import make_pilot, load_policy   # noqa: E402
from aircombat.guidance.bfm_guidance import GuidanceCommand     # noqa: E402
from aircombat.guidance.doctrine import Doctrine                # noqa: E402

DT = 1.0 / 120.0
L15_DIV = 2                          # match.py Match(l15_div=2) — L2 는 2틱마다
DEPLOYED_K_RATE = (9.0, 9.0, 6.0)    # pilot.py:53
DEPLOYED_FILT_HZ = 25.0              # pilot.py:53

GYRO_PROPS = ("velocities/p-rad_sec", "velocities/q-rad_sec", "velocities/r-rad_sec")
ACC_PROPS = ("accelerations/pdot-rad_sec2", "accelerations/qdot-rad_sec2",
             "accelerations/rdot-rad_sec2")


# ======================================================================================
# 설정
# ======================================================================================
@dataclass(frozen=True)
class Condition:
    alt_ft: float
    kcas: float
    psi_deg: float = 0.0
    fbw_override: int = 0            # 0 = FLCS on (기준), 1 = FLCS 우회 (대조)

    def ic(self) -> dict:
        return {"pos": (0.0, 0.0, -self.alt_ft), "psi": self.psi_deg,
                "kcas": self.kcas, "alt": self.alt_ft}


@dataclass(frozen=True)
class Params:
    k_scale: tuple = (1.0, 1.0, 1.0)          # (p, q, r) 축별 배율, 기준 k_rate 에 곱함
    filt_hz: float = DEPLOYED_FILT_HZ

    @property
    def k_rate(self) -> tuple:
        return tuple(float(b * s) for b, s in zip(DEPLOYED_K_RATE, self.k_scale))


@dataclass(frozen=True)
class Uncertainty:
    g0_row_scale: tuple = (1.0, 1.0, 1.0)     # λ = G_model/G_true, 행(p,q,r) 단위
    g0_offdiag_scale: float = 1.0             # 비대각 원소 배율
    gyro_sigma_dps: float = 0.0               # 120 Hz 샘플당 자이로 백색잡음 σ [deg/s]
    input_delay_ms: float = 0.0               # 조종면 명령 전달 지연
    seed: int = 0

    @property
    def is_null(self) -> bool:
        return (self.g0_row_scale == (1.0, 1.0, 1.0) and self.g0_offdiag_scale == 1.0
                and self.gyro_sigma_dps == 0.0 and self.input_delay_ms == 0.0)


def config_hash(*objs) -> str:
    payload = json.dumps([dataclasses.asdict(o) if dataclasses.is_dataclass(o) else o
                          for o in objs], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ======================================================================================
# 플랜트 프록시 — 제어기 쪽 센서 잡음과 입력 지연
# ======================================================================================
class PlantProxy:
    """`Pilot` 이 보는 플랜트. 참 플랜트(`true`)는 그대로 두고 읽기/쓰기만 가공한다.

    잡음: 물리 스텝마다 축별 백색잡음 n_k ~ N(0, σ) 을 새로 뽑아 고정(latch)한다.
          자이로 = 참 + n_k,  각가속도 = 참 + (n_k − n_{k−1})/Δt  (같은 잡음 자이로의 1차 차분과 일치)
    지연: set_input 을 FIFO 로 N 틱 늦춰 참 플랜트에 적용. N = round(delay/Δt).
    """

    def __init__(self, true_plant, dt: float, gyro_sigma_dps: float = 0.0,
                 input_delay_ms: float = 0.0, seed: int = 0):
        self.true = true_plant
        self.fdm = true_plant.fdm
        self.dt = dt
        self.sigma = np.deg2rad(float(gyro_sigma_dps))
        self.rng = np.random.default_rng(seed)
        z = self.rng.normal(0.0, self.sigma, 3) if self.sigma > 0 else np.zeros(3)
        self.n = z.copy()
        self.n_prev = z.copy()
        self.delay_steps = int(round(float(input_delay_ms) / 1000.0 / dt))
        u0 = list(true_plant.get_input())
        self.fifo = collections.deque([u0] * self.delay_steps)

    def __getitem__(self, prop):
        v = self.true[prop]
        if self.sigma > 0:
            if prop in GYRO_PROPS:
                return v + self.n[GYRO_PROPS.index(prop)]
            if prop in ACC_PROPS:
                i = ACC_PROPS.index(prop)
                return v + (self.n[i] - self.n_prev[i]) / self.dt
        return v

    def __setitem__(self, prop, val):
        self.true[prop] = val

    def set_input(self, u):
        if self.delay_steps == 0:
            return self.true.set_input(u)
        self.fifo.append(list(u))
        return self.true.set_input(self.fifo.popleft())

    def step(self, n: int = 1):
        for _ in range(n):
            self.true.step(1)
            if self.sigma > 0:
                self.n_prev = self.n
                self.n = self.rng.normal(0.0, self.sigma, 3)
        return self

    def __getattr__(self, name):          # get_input, get_state 등 나머지는 참 플랜트로
        return getattr(self.true, name)


# ======================================================================================
# 조립
# ======================================================================================
@dataclass
class Rig:
    pilot: object
    plant: object                     # 참 플랜트 (지표용)
    G0_true: np.ndarray
    G0_model: np.ndarray
    qbar_ref: float
    cond: Condition
    params: Params
    unc: Uncertainty
    sp_log: list = field(default_factory=list)


def transform_g0(G0: np.ndarray, unc: Uncertainty) -> np.ndarray:
    M = np.array(G0, float, copy=True)
    off = ~np.eye(3, dtype=bool)
    M[off] *= unc.g0_offdiag_scale
    return np.diag(np.asarray(unc.g0_row_scale, float)) @ M


def build(cond: Condition, params: Params = Params(), unc: Uncertainty = Uncertainty(),
          policy_yaml: str | None = None, rebuild_indi: bool = True,
          wrap_limiter: bool = True, use_proxy: bool = True) -> Rig:
    """배치 경로로 Pilot 을 조립하고 연구 인자·교란을 입힌다.

    rebuild_indi / wrap_limiter / use_proxy 는 게이트 G2 에서 "하네스 가공이 기준값에서
    아무것도 바꾸지 않음" 을 증명하려고 끌 수 있게 둔 스위치다. 실험에서는 항상 True.
    """
    if policy_yaml:
        policy, doctrine = load_policy(policy_yaml)
    else:
        policy, doctrine = None, Doctrine()
    pilot = make_pilot("Blue", cond.ic(), policy, doctrine)
    true_plant = pilot.plant
    if cond.fbw_override:
        # make_pilot 은 FLCS on 상태로 트림한다. 우회 조건은 스위치를 켠 뒤 다시 트림해야
        # 트림 조종면이 우회 플랜트 기준이 된다. (FLCS on 기준 경로는 건드리지 않는다.)
        true_plant["fcs/fbw-override"] = 1
        true_plant.trim()
    pilot.setup()                                        # 배치 경로: 참 플랜트에서 G0 식별

    G0_true = np.array(pilot.indi.G0, copy=True)
    qbar_ref = float(pilot.indi.qbar_ref)
    G0_model = transform_g0(G0_true, unc)

    if rebuild_indi:
        indi = INDIRateController(pilot.dt_phys, G0_model, qbar_ref,
                                  k_rate=params.k_rate, filt_hz=params.filt_hz)
        indi.reset(u0=[true_plant["fcs/aileron-cmd-norm"],      # Pilot.setup 과 같은 u0
                       true_plant["fcs/elevator-cmd-norm"],
                       true_plant["fcs/rudder-cmd-norm"]])
        pilot.indi = indi

    rig = Rig(pilot=pilot, plant=true_plant, G0_true=G0_true, G0_model=G0_model,
              qbar_ref=qbar_ref, cond=cond, params=params, unc=unc)

    if wrap_limiter:
        lim = pilot.limiter
        orig = lim.limit_omega_sp

        def recorded(omega_sp, v_fps, kcas, g_lift=0.0, _orig=orig, _log=rig.sp_log):
            out, flags = _orig(omega_sp, v_fps, kcas, g_lift=g_lift)
            _log.append((np.array(out, float), bool(flags["p_limited"]),
                         bool(flags["q_limited"]), bool(flags["r_limited"])))
            return out, flags

        lim.limit_omega_sp = recorded

    if use_proxy:
        pilot.plant = PlantProxy(true_plant, pilot.dt_phys, unc.gyro_sigma_dps,
                                 unc.input_delay_ms, unc.seed)
    return rig


# ======================================================================================
# 실행
# ======================================================================================
TRUTH_COLS = (
    "t", "p", "q", "r", "sp_p", "sp_q", "sp_r", "p_lim", "q_lim", "r_lim",
    "u_ail", "u_ele", "u_rud",                      # INDI 가 낸 명령
    "cmd_ail", "cmd_ele", "cmd_rud",                # 참 플랜트에 실제 걸린 명령 (지연 후)
    "pos_ail", "pos_ele", "pos_rud_deg",             # 실제 타면
    "phi", "theta", "psi", "alpha", "beta", "nz", "vt", "kcas", "qbar", "alt",
    "gc_dphi", "gc_q", "gc_thrust", "gc_g",
)


def state_view(plant) -> dict:
    """합성 기동이 명령을 만들 때 쓰는 참 상태 (L2 도 참 상태를 본다)."""
    return {"phi": plant["attitude/phi-rad"], "theta": plant["attitude/theta-rad"],
            "psi": plant["attitude/psi-rad"], "vt": plant["velocities/vt-fps"],
            "kcas": plant["velocities/vc-kts"], "nz": plant["accelerations/Nz"],
            "q": plant["velocities/q-rad_sec"]}


def run(rig: Rig, maneuver, n_steps: int | None = None) -> dict:
    """틱 루프. 반환: {열이름: np.ndarray} + 메타.

    maneuver 는 `.duration_s` 와 `.command(t, k, state) -> GuidanceCommand` 를 가진다.
    `.per_tick = True` 이면 영차 유지 없이 매 틱 명령을 받는다(기록 재생용).
    """
    pilot, plant = rig.pilot, rig.plant
    n = n_steps if n_steps is not None else int(round(maneuver.duration_s / DT))
    per_tick = getattr(maneuver, "per_tick", False)
    out = np.full((n, len(TRUTH_COLS)), np.nan)
    rig.sp_log.clear()
    have_sp = True

    for k in range(n):
        t = k * DT
        if per_tick or k % L15_DIV == 0:
            pilot._gc = maneuver.command(t, k, state_view(plant))
        gc = pilot._gc
        pilot.control_step(None)
        pilot.step_physics()

        if rig.sp_log:
            sp, pl, ql, rl = rig.sp_log[-1]
        else:
            have_sp = False
            sp, pl, ql, rl = (np.full(3, np.nan), False, False, False)
        u = pilot.indi.u_prev
        out[k] = (
            t, plant["velocities/p-rad_sec"], plant["velocities/q-rad_sec"],
            plant["velocities/r-rad_sec"], sp[0], sp[1], sp[2], pl, ql, rl,
            u[0], u[1], u[2],
            plant["fcs/aileron-cmd-norm"], plant["fcs/elevator-cmd-norm"],
            plant["fcs/rudder-cmd-norm"],
            plant["fcs/left-aileron-pos-norm"], plant["fcs/elevator-pos-norm"],
            plant["fcs/rudder-pos-deg"],
            plant["attitude/phi-rad"], plant["attitude/theta-rad"], plant["attitude/psi-rad"],
            plant["aero/alpha-rad"], plant["aero/beta-rad"], plant["accelerations/Nz"],
            plant["velocities/vt-fps"], plant["velocities/vc-kts"], plant["aero/qbar-psf"],
            plant["position/h-sl-ft"],
            gc.dphi_cmd, gc.q_cmd, gc.thrust_cmd, gc.g_target,
        )
    ts = {c: out[:, i] for i, c in enumerate(TRUTH_COLS)}
    ts["_meta"] = {"have_sp": have_sp, "n_steps": n,
                   "G0_true": rig.G0_true.tolist(), "G0_model": rig.G0_model.tolist(),
                   "qbar_ref": rig.qbar_ref,
                   "cond": dataclasses.asdict(rig.cond), "params": dataclasses.asdict(rig.params),
                   "unc": dataclasses.asdict(rig.unc)}
    return ts


def gcmd(dphi: float, nz_target: float, st: dict, thrust: float = 1.0) -> GuidanceCommand:
    """bfm_guidance.py:339, 366 과 같은 식으로 합성 L2 명령을 만든다."""
    g_lift = float(np.cos(st["phi"]) * np.cos(st["theta"]))
    q_cmd = (nz_target - g_lift) * G_FT_S2 / max(st["vt"], 1.0)
    return GuidanceCommand(dphi_cmd=float(dphi), q_cmd=float(q_cmd),
                           thrust_cmd=float(thrust), g_target=float(nz_target))
