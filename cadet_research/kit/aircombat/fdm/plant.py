"""F-16 plant wrapper — standalone JSBSim (별도 연구 스택).

**대회 매치의 실제 플랜트다** — bridge.CompetitionMatch → factory.make_pilot 이 이걸 쓴다
(V1 시절 "매치 엔진(.pyd)과 무관" 이라 적혀 있었으나 V2 에서 사실이 아니게 됐다).
pip `jsbsim` + 로컬 F-16 XML 을 plant 로 쓴다.
인용: "runs in JSBSim, ... very accurate for modeling aerodynamics [15][16]".

상태 벡터(제어 설계용 종/횡 표준 12-state 의 부분집합):
    x = [V(fps), alpha(rad), theta(rad), q(rad/s),      # 종(longitudinal)
         beta(rad), phi(rad), p(rad/s), r(rad/s),       # 횡(lateral-directional)
         h(ft), psi(rad)]                               # 항법(guidance)
입력 u = [throttle(0..1), elevator(-1..1), aileron(-1..1), rudder(-1..1)]
    (JSBSim fcs/*-cmd-norm 경유 → 조종면. **내장 FLCS 는 trim() 에서 우회한다** —
     이 스택의 FLCS 는 L3(CombinedLimiter + INDI) 다. 아래 trim() 주석 참조.)
"""
from __future__ import annotations
import os
import numpy as np

from ..aircraft import resolve_aircraft_model

try:
    import jsbsim
except ImportError as e:  # pragma: no cover
    raise ImportError("pip install jsbsim  (standalone, 매치 .pyd 와 별개)") from e

# 로컬 JSBSim 데이터 루트 (aircraft/engine/systems 완비, F-16 native FLCS 포함).
# robust: new_match_engine 이 sdk(vendored) 안이든 core 안이든 F-16 데이터를 찾는다.
def _find_jsbsim_root():
    # aircombat/fdm/plant.py → 저장소 루트의 jsbsim_data (F-16 XML + native FLCS 번들).
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, "..", "..", "jsbsim_data"))


DEFAULT_ROOT = _find_jsbsim_root()

# 상태/입력 property 매핑 (JSBSim property tree)
STATE_PROPS = {
    "V":     "velocities/vt-fps",        # true airspeed
    "alpha": "aero/alpha-rad",
    "theta": "attitude/theta-rad",
    "q":     "velocities/q-rad_sec",
    "beta":  "aero/beta-rad",
    "phi":   "attitude/phi-rad",
    "p":     "velocities/p-rad_sec",
    "r":     "velocities/r-rad_sec",
    "h":     "position/h-sl-ft",
    "psi":   "attitude/psi-rad",
}
STATE_ORDER = ["V", "alpha", "theta", "q", "beta", "phi", "p", "r", "h", "psi"]

INPUT_PROPS = {
    "throttle": "fcs/throttle-cmd-norm[0]",
    "elevator": "fcs/elevator-cmd-norm",
    "aileron":  "fcs/aileron-cmd-norm",
    "rudder":   "fcs/rudder-cmd-norm",
}
INPUT_ORDER = ["throttle", "elevator", "aileron", "rudder"]


class F16Plant:
    """JSBSim F-16 — 제어 연구용 결정론 plant."""

    def __init__(self, root: str = DEFAULT_ROOT, model: str | None = None, dt: float | None = None):
        # f16 is the pinned upstream baseline; research and legacy models are explicit options.
        model = resolve_aircraft_model(model)
        self.fdm = jsbsim.FGFDMExec(root)
        self.fdm.set_debug_level(0)
        if not self.fdm.load_model(model):
            raise RuntimeError(f"JSBSim load_model('{model}') 실패 (root={root})")
        if dt is not None:
            self.fdm.set_dt(dt)
        self.root = root
        self.model = model
        self._trim_mode: int | None = None

    # --- 초기화 / trim -------------------------------------------------
    def set_ic(self, alt_ft: float, vc_kts: float, gamma_deg: float = 0.0,
               psi_deg: float = 0.0):
        f = self.fdm
        f["ic/h-sl-ft"] = float(alt_ft)
        f["ic/vc-kts"] = float(vc_kts)
        f["ic/gamma-deg"] = float(gamma_deg)
        f["ic/psi-true-deg"] = float(psi_deg)
        f.run_ic()
        # ★ 기어 올림. 모델 기본값 gear-cmd-norm=1(내림) 이라 CDgear=+0.027 이 항상 붙어 있었다
        #   (청정 기체 CD0 과 맞먹는 항력, 2026-09-11 교범 Table 4.9 대조에서 발견). 위치까지 0 으로
        #   놓아야 5 s 접이 kinematic 을 건너뛰고 trim 이 청정 형상으로 잡힌다. docs/5_피델리티_EM.md
        f["gear/gear-cmd-norm"] = 0.0
        f["gear/gear-pos-norm"] = 0.0
        self.start_engines()   # ★ 엔진 시동 (미시동 시 thrust=0 → 무동력 활공 버그)
        return self

    def start_engines(self):
        """엔진 시동 — 미시동 시 thrust≈0 (램항력만) → 모든 속도제어 무력화.

        ★ 반드시 호출. run_ic 후 init_running(-1)로 전 엔진 running 상태로.
        검증: 시동 전 thrust=−1383lbs(드래그), 시동 후 +17116lbs.
        """
        try:
            self.fdm.get_propulsion().init_running(-1)   # 전 엔진 시동
        except Exception:
            try:
                self.fdm["propulsion/engine[0]/set-running"] = 1
            except Exception:
                pass
        return self

    def trim(self, mode: int = 1):
        """in-air trim (mode 1) → 내장 FLCS 우회. 실패해도 예외 대신 False 반환.

        ★ fcs/fbw-override=1 (2026-09-06)
        f16.xml 의 Pitch/Roll 채널은 스틱→조종면 직결이 아니라 **자체 레이트 명령
        폐루프**다 (pitch: `pitch-rate-norm = 6.2·q` 되먹임 + g-load PID + α 게인
        스케줄). 그런데 이 스택은 그 입구(fcs/elevator-cmd-norm)에 **이미 폐루프를
        거친 INDI 출력**을 넣는다 — 레이트 루프가 직렬로 두 겹이 되고, 실기 F-16 에
        없는 구조다. 실측 결과 풀스틱(elevator 지령 포화율 100%)에서도 달성 G 가
        4.5–7.2G 에 묶였고(전 속도), 같은 조건에서 공력 자체는 9.5G 를 낼 수 있었다.
        즉 천장은 공력·구조가 아니라 내장 FLCS 였다.

        fbw-override 는 f16.xml 저자가 외부 FLCS 용으로 만들어 둔 공식 스위치다.
        스위치 **뒤**에 남는 것 — 승강타 명령 클립(−1/+0.44 = 9G/−4G 비대칭)과
        액추에이터 속도제한(0.3s 풀스트로크), 에일러론 마하 보상 — 은 실제 하드웨어에
        해당하므로 그대로 유지된다. 사라지는 것은 α 게인 스케줄·alpha-limiter-norm·
        g-load PID 뿐이고, α 보호는 control/limiter.py 의 AoA 게이트가 대신한다.

        트림 **전**에 켠다 — 트림은 최종 비행 구성으로 풀어야 한다. 뒤에 켜면 트림은
        내장 FLCS 가 물린 해를 내는데 비행은 우회 상태로 하므로 해가 어긋나, 트림
        직후 2초에 Nz 2.2G·고도 +24ft 의 기수들림이 남았다(실측). 앞에 켜면 전 속도
        (300–450KCAS)에서 Nz 0.995·고도변화 0.0ft 로 수렴한다.

        (부수 효과 하나 — f16.xml 의 g-load 되먹임은 JSBSim 1.3.1 에서 부호가 뒤집혀
        있다: 수평 1G 에서 fcs/g-load-corrected 가 0 이 아니라 −2.0 이 나온다. XML
        주석의 의도와 반대다. 우회하면 그 경로도 함께 사라진다.)
        """
        self.fdm["fcs/fbw-override"] = 1
        try:
            self.fdm["simulation/do_simple_trim"] = mode
            self._trim_mode = mode
            return True
        except Exception:
            return False

    def identify_initial_control(self):
        """Identify on a separately trimmed probe, leaving the live FDM untouched.

        This is an initial-trim probe, not a full serializer of JSBSim filter
        histories. It must only be used for Pilot.setup(), before flight.
        """
        from ..control.indi import identify_G0

        if self._trim_mode is None:
            raise RuntimeError("Control identification requires a successful initial trim")
        probe = F16Plant(root=self.root, model=self.model, dt=self.dt)
        # Match the live initial rigid-body state, fuel, gear and FBW mode.
        for prop in ("gear/gear-cmd-norm", "gear/gear-pos-norm", "fcs/fbw-override",
                     "propulsion/tank[0]/contents-lbs", "propulsion/tank[1]/contents-lbs"):
            probe[prop] = self[prop]
        probe.restore_state(self.capture_state())
        if not probe.trim(self._trim_mode):
            raise RuntimeError("Initial control-identification probe could not trim")
        return identify_G0(probe.fdm)

    # --- step / 접근 ---------------------------------------------------
    @property
    def dt(self) -> float:
        return self.fdm.get_delta_t()

    def step(self, n: int = 1):
        for _ in range(n):
            self.fdm.run()
        return self

    def get_state(self) -> np.ndarray:
        f = self.fdm
        return np.array([f[STATE_PROPS[k]] for k in STATE_ORDER], dtype=float)

    def get_state_dict(self) -> dict:
        f = self.fdm
        return {k: f[STATE_PROPS[k]] for k in STATE_ORDER}

    def set_input(self, u: np.ndarray):
        f = self.fdm
        for k, val in zip(INPUT_ORDER, u):
            f[INPUT_PROPS[k]] = float(val)
        return self

    def get_input(self) -> np.ndarray:
        f = self.fdm
        return np.array([f[INPUT_PROPS[k]] for k in INPUT_ORDER], dtype=float)

    def __getitem__(self, prop):
        return self.fdm[prop]

    def __setitem__(self, prop, val):
        self.fdm[prop] = val

    # --- state capture / restore (실엔진 rollout 용) --------------------
    #   JSBSim 은 직접 serialize 가 없어 IC 속성으로 12-DOF 상태 복원.
    #   FCS 내부 적분/조종면 위치는 재설정 → <1s transient (선택용 rollout 엔 무해).
    _CAP_PROPS = (
        "position/lat-gc-rad", "position/long-gc-rad", "position/h-sl-ft",
        "velocities/u-fps", "velocities/v-fps", "velocities/w-fps",
        "attitude/phi-rad", "attitude/theta-rad", "attitude/psi-rad",
        "velocities/p-rad_sec", "velocities/q-rad_sec", "velocities/r-rad_sec",
    )
    _CAP_TO_IC = {
        "position/lat-gc-rad":  "ic/lat-gc-rad",
        "position/long-gc-rad": "ic/long-gc-rad",
        "position/h-sl-ft":     "ic/h-sl-ft",
        "velocities/u-fps":     "ic/u-fps",
        "velocities/v-fps":     "ic/v-fps",
        "velocities/w-fps":     "ic/w-fps",
        "attitude/phi-rad":     "ic/phi-rad",
        "attitude/theta-rad":   "ic/theta-rad",
        "attitude/psi-rad":     "ic/psi-true-rad",
        "velocities/p-rad_sec": "ic/p-rad_sec",
        "velocities/q-rad_sec": "ic/q-rad_sec",
        "velocities/r-rad_sec": "ic/r-rad_sec",
    }

    def capture_state(self) -> dict:
        """현재 비행상태 스냅샷 (위치·자세·body속도·rates + 입력). restore_state 로 복원."""
        f = self.fdm
        snap = {p: f[p] for p in self._CAP_PROPS}
        snap["_u"] = self.get_input()
        return snap

    def restore_state(self, snap: dict):
        """capture_state 스냅샷으로 복원 (IC 경유 run_ic). 엔진 재시동·입력 복원."""
        f = self.fdm
        for prop, ic in self._CAP_TO_IC.items():
            f[ic] = snap[prop]
        f.run_ic()
        self.start_engines()
        self.set_input(snap["_u"])
        return self


if __name__ == "__main__":
    # first-light: load / trim / step
    p = F16Plant()
    p.set_ic(alt_ft=15000.0, vc_kts=350.0)
    print("trim:", p.trim())
    p.step(5)
    s = p.get_state_dict()
    print(f"dt={p.dt:.4f}")
    print(f"alt={s['h']:.1f}ft  V={s['V']:.1f}fps  alpha={np.degrees(s['alpha']):.2f}deg  "
          f"theta={np.degrees(s['theta']):.2f}deg")
    print(f"phi={np.degrees(s['phi']):.2f}deg  psi={np.degrees(s['psi']):.2f}deg  "
          f"q={s['q']:.4f} p={s['p']:.4f} r={s['r']:.4f}")
    print("u(trim)=", np.round(p.get_input(), 4))
