"""Pilot — 한 기체의 5계층 제어 체인 조립 (L1→L2→shim→limiter→L3→L4).

다중레이트 스케줄러(match)가 위상에 맞춰 호출한다:
  tactic_step   (L1  20Hz) : BT → (pursuit, g_burst)
  guidance_step (L2 60Hz): BFMGuidance → GuidanceCommand
  control_step  (L3  120Hz): shim+limiter+INDI → 조종면, 위치 적분
  step_physics  (L4  120Hz): JSBSim 1스텝

상태(_cmd, _gc, _pos, health)를 보유하며 상대 관측은 KinState 로 주입받는다.
"""
from __future__ import annotations

import numpy as np

from ..fdm.plant import F16Plant
from ..control.indi import (INDIRateController, INDIConfig, SensorConfig, RateSensor,
                             identify_G0)
from ..control.attitude import QuaternionAttitudeShim, euler_to_quat, quat_mul
from ..guidance.bfm_guidance import BFMGuidance, AircraftKinematics
from ..geometry.combat_geometry import CombatGeometry
from ..tactics.policy import TacticPolicy
from ..tactics.context import TacticContext, TacticCommand
from .state import KinState, ControlTelemetry, G_FT_S2


class Pilot:
    def __init__(self, plant: F16Plant, color: str = "Blue",
                 init_pos_ned=(0.0, 0.0, -15000.0), dt_phys: float = 1.0 / 120.0,
                 policy: TacticPolicy | None = None,
                 guidance: BFMGuidance | None = None, name: str = "F-16",
                 indi_cfg: INDIConfig | None = None,
                 sensor_cfg: SensorConfig | None = None):
        self.plant = plant
        self.color = color
        self.name = name              # ACMI Name (기체/팀) — F16Plant 모델
        self.agent_name: str | None = None   # ACMI CallSign (표시용 에이전트명) — factory 가 설정
        self.dt_phys = float(dt_phys)
        self.guid = guidance or BFMGuidance()
        self.limiter = self.guid.limiter   # 단일 진실: 가이던스(교리)가 만든 리미터 공유
        self.indi_cfg = indi_cfg or INDIConfig()
        # 측정 모델 — 측별 잡음열이 달라야 하므로 color 로 salt (결정론 유지).
        self.sensor = RateSensor(sensor_cfg, salt=0 if color == "Blue" else 1)
        self.shim = QuaternionAttitudeShim(k_att=self.indi_cfg.k_att, k_yaw_damp=1.5,
                                           rate_limit_dps=(180.0, 60.0, 30.0))
        self.policy = policy or TacticPolicy(dt=1.0 / 20.0)
        self.indi: INDIRateController | None = None
        self._pos = np.array(init_pos_ned, float)
        self._cmd = TacticCommand("lead", "default")
        self._gc = None
        self.health = 100.0
        self.overtime = False         # Match 가 OT 진입 시 세운다 (L1 관측 in_overtime)
        self.last_flags: dict = {}
        self._prev_psi: dict[str, float] = {}   # 1/2-circle flow 판별용 20Hz 헤딩 이력

    # ── setup: 트림 후 G0 식별 + INDI reset ──
    def setup(self) -> "Pilot":
        G0, qbar_ref = identify_G0(self.plant.fdm)
        c = self.indi_cfg
        self.indi = INDIRateController(self.dt_phys, G0, qbar_ref,
                                       k_rate=(c.k_p, c.k_q, c.k_r), filt_hz=c.filt_hz,
                                       k_ff=c.k_ff, lam=c.lam)
        self.indi.reset(u0=[self.plant["fcs/aileron-cmd-norm"],
                            self.plant["fcs/elevator-cmd-norm"],
                            self.plant["fcs/rudder-cmd-norm"]])
        return self

    # ── 관측 ──
    def state(self) -> KinState:
        p = self.plant
        return KinState(
            pos_ned=self._pos.copy(),
            vel_ned=np.array([p["velocities/v-north-fps"], p["velocities/v-east-fps"],
                              p["velocities/v-down-fps"]]),
            phi=p["attitude/phi-rad"], theta=p["attitude/theta-rad"],
            psi=p["attitude/psi-rad"], v_fps=p["velocities/vt-fps"],
            kcas=p["velocities/vc-kts"], alt_ft=p["position/h-sl-ft"],
            health=self.health)

    def _turn_dir(self, key: str, psi: float,
                  dt: float = 1.0 / 20.0, min_dps: float = 3.0) -> int:
        """수평 선회방향 (+1 우/-1 좌/0 직선) — 20Hz 헤딩 차분. flow 판별용."""
        prev = self._prev_psi.get(key)
        self._prev_psi[key] = psi
        if prev is None:
            return 0
        rate_dps = np.degrees((psi - prev + np.pi) % (2 * np.pi) - np.pi) / dt
        return 1 if rate_dps > min_dps else (-1 if rate_dps < -min_dps else 0)

    def _context(self, me: KinState, foe: KinState) -> TacticContext:
        geom = CombatGeometry(me.pos_ned, foe.pos_ned, me.vel_ned, foe.vel_ned,
                              me.phi, me.theta, me.psi, foe.theta, foe.psi)
        los = foe.pos_ned - me.pos_ned
        # 확장 관측 — V1/core-live compute_obs 및 기수각 공식과 **연산 순서까지 동일**
        # (커스텀 노드로 이식된 정책의 결정 동치를 위해 math 연산·항 순서를 그대로 복제).
        import math as _m
        d_n, d_e, d_d = float(los[0]), float(los[1]), float(los[2])
        dist = _m.sqrt(d_n**2 + d_e**2 + d_d**2)
        e_vn, e_ve, e_vd = (float(me.vel_ned[0]), float(me.vel_ned[1]),
                            float(me.vel_ned[2]))
        o_vn, o_ve, o_vd = (float(foe.vel_ned[0]), float(foe.vel_ned[1]),
                            float(foe.vel_ned[2]))
        ego_sp = _m.sqrt(e_vn**2 + e_ve**2 + e_vd**2) + 1e-9
        enm_sp = _m.sqrt(o_vn**2 + o_ve**2 + o_vd**2) + 1e-9
        proj_e = (d_n*e_vn + d_e*e_ve + d_d*e_vd) / (dist*ego_sp + 1e-9)
        proj_o = (d_n*o_vn + d_e*o_ve + d_d*o_vd) / (dist*enm_sp + 1e-9)
        vel_ata = _m.degrees(_m.acos(max(-1.0, min(1.0, proj_e))))
        vel_aa = _m.degrees(_m.acos(max(-1.0, min(1.0, proj_o))))
        rel_vn, rel_ve, rel_vd = o_vn - e_vn, o_ve - e_ve, o_vd - e_vd
        closure_fps_ex = -(rel_vn*d_n + rel_ve*d_e + rel_vd*d_d) / (dist + 1e-9)
        # 기수각 — 원본 _nose_angles 와 동일 연산(np.linalg.norm·np.dot·math.acos)
        d_norm = float(np.linalg.norm(los))
        if d_norm < 1e-6:
            nose_ata_x = nose_eata_x = 0.0
        else:
            def _nose(th, ps):
                return np.array([_m.cos(th) * _m.cos(ps),
                                 _m.cos(th) * _m.sin(ps), -_m.sin(th)])
            nose_ata_x = _m.degrees(_m.acos(max(-1.0, min(1.0,
                float(np.dot(_nose(me.theta, me.psi), los)) / d_norm))))
            nose_eata_x = _m.degrees(_m.acos(max(-1.0, min(1.0,
                float(np.dot(_nose(foe.theta, foe.psi), -los)) / d_norm))))
        return TacticContext(
            ata_deg=geom.ata_deg(), aspect_deg=geom.aa_deg(),
            range_ft=float(np.linalg.norm(los)), closure_fps=geom.closure_rate(),
            kcas=me.kcas, energy_diff_ft=me.specific_energy_ft() - foe.specific_energy_ft(),
            alt_gap_ft=me.pos_ned[2] - foe.pos_ned[2], alt_ft=me.alt_ft,
            vs_fps=-float(me.vel_ned[2]),   # vel_ned[2]=v-down → 부호 반전(+상승)
            my_health=me.health,
            fighting_kts_lo=self.guid.doc.fighting_kts_lo,
            fighting_kts_hi=self.guid.doc.fighting_kts_hi,
            hca_deg=geom.hca_deg(),
            my_turn_dir=self._turn_dir("me", me.psi),
            foe_turn_dir=self._turn_dir("foe", foe.psi),
            enm_alt_ft=foe.alt_ft, enm_kcas=foe.kcas,
            enm_theta_deg=float(np.degrees(foe.theta)),
            ego_psi_deg=float(np.degrees(me.psi)) % 360.0,
            enm_psi_deg=float(np.degrees(foe.psi)) % 360.0,
            vel_ata_deg=vel_ata, vel_aa_deg=vel_aa,
            closure_kts=float(closure_fps_ex) * (3600.0 * 0.3048 / 1852.0),
            dist_x_ft=dist, nose_ata_x_deg=nose_ata_x,
            nose_eata_x_deg=nose_eata_x,
            overtime=self.overtime)

    # ── L1 (20Hz) ──
    def tactic_step(self, foe: KinState) -> None:
        ctx = self._context(self.state(), foe)
        self._cmd = self.policy.tick(ctx)
        self.last_ctx = ctx

    # ── L2 (60Hz) ──
    def guidance_step(self, foe: KinState) -> None:
        me = self.state()
        self._gc = self.guid.compute(
            AircraftKinematics(me.pos_ned, me.vel_ned, me.phi, me.theta, me.psi,
                               me.v_fps, me.kcas, q=self.plant["velocities/q-rad_sec"]),
            foe.pos_ned, foe.vel_ned,
            pursuit=self._cmd.pursuit, g_burst=self._cmd.g_burst,
            aim_above_ft=self._cmd.aim_above_ft,
            lead_time_s=self._cmd.lead_time_s,
            lag_dist_ft=self._cmd.lag_dist_ft,
            mode=self._cmd.mode,
            cz_range_ft=self._cmd.cz_range_ft,
            g_full_ata_deg=self._cmd.g_full_ata_deg,
            track_rng_ft=self._cmd.track_rng_ft,
            track_ata_deg=self._cmd.track_ata_deg,
            foe_theta=foe.theta, foe_psi=foe.psi)

    # ── L3 (120Hz): 위치 적분 + shim + limiter + INDI → 조종면 ──
    def control_step(self, foe: KinState) -> None:
        p = self.plant
        phi = p["attitude/phi-rad"]; theta = p["attitude/theta-rad"]; psi = p["attitude/psi-rad"]
        pqr = np.array([p["velocities/p-rad_sec"], p["velocities/q-rad_sec"],
                        p["velocities/r-rad_sec"]])
        v_ned = np.array([p["velocities/v-north-fps"], p["velocities/v-east-fps"],
                          p["velocities/v-down-fps"]])
        self._pos = self._pos + v_ned * self.dt_phys      # 위치 적분
        if self._gc is None:
            self.guidance_step(foe)
        gc = self._gc

        q_cur = euler_to_quat(phi, theta, psi)
        q_des = quat_mul(q_cur, euler_to_quat(gc.dphi_cmd, 0.0, 0.0))
        omega_sp = self.shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
        omega_sp[1] = gc.q_cmd
        # 중력의 양력방향 성분 cosφ·cosθ — G↔pitch-rate 환산에 반드시 들어간다.
        omega_sp, self.last_flags = self.limiter.limit_omega_sp(
            omega_sp, p["velocities/vt-fps"], p["velocities/vc-kts"],
            g_lift=float(np.cos(phi) * np.cos(theta)), nz=p["accelerations/Nz"],
            q_meas=float(pqr[1]))

        pqr_m, acc_m = self.sensor(pqr, [
            p["accelerations/pdot-rad_sec2"], p["accelerations/qdot-rad_sec2"],
            p["accelerations/rdot-rad_sec2"]])
        u = self.indi.update(pqr_m, omega_sp, p["aero/qbar-psf"], ang_accel=acc_m)
        p.set_input([gc.thrust_cmd, u[1], u[0], u[2]])    # [thr, elev, ail, rud]

    def step_physics(self) -> None:
        self.plant.step(1)

    # ── 조종 텔레메트리 (ACMI Control Position 애드온용) ──
    def telemetry(self) -> ControlTelemetry:
        p = self.plant
        return ControlTelemetry(
            throttle=p["fcs/throttle-cmd-norm[0]"],
            ail_cmd=p["fcs/aileron-cmd-norm"], elev_cmd=p["fcs/elevator-cmd-norm"],
            rud_cmd=p["fcs/rudder-cmd-norm"],
            ail_pos=p["fcs/left-aileron-pos-norm"], elev_pos=p["fcs/elevator-pos-norm"],
            rud_pos=p["fcs/rudder-pos-norm"])
