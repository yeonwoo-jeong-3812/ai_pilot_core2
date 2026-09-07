"""1v1 매치 엔진 — 다중레이트 스케줄러 + WEZ 데미지 + judge + ACMI 로깅.

주기(config/sim.yaml 로 조정): L3·L4 120Hz(매 틱), L2 60Hz(÷2), L1 20Hz(÷6).
두 전투원은 동일 인터페이스(state/tactic_step/guidance_step/control_step/step_physics)
라 lockstep 으로 대칭 처리한다 — Pilot(JSBSim) vs ScriptedOpponent(운동학), 또는
향후 Pilot vs Pilot(self-play).

결정론: 난수 없음, 스크립트 적기, JSBSim 결정론 스텝.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import numpy as np

from ..geometry.combat_geometry import CombatGeometry
from ..geometry.wez import WeaponEngagementZone, HealthGauge
from ..debrief.acmi import (ACMIWriter, ACMIObject, combat_attrs, flight_attrs,
                            control_attrs, GunVisualizer)
from ..debrief.replay_debrief import auto_debrief
from .state import KinState, ned_to_lonlat, FT_TO_M, FT_S_TO_KT

HARD_DECK_FT = 1000.0
OVERTIME_S = 120.0       # 오버타임 길이 (RULEBOOK 「오버타임」) — 현장 단판만 적용
STALL_KTS = 100.0        # 이 속도 미만 체류가
STALL_LIMIT_S = 10.0     # 누적 10초면 실속 패 (비행 안전 위반)
HIT_REARM_S = 1.0        # 피격 북마크: 직전 데미지와 이 간격 이상 벌어지면 새 버스트로 간주(1개 찍음)
HIT_FLASH_S = 1.0        # 피격 후 이 시간 동안 기체색 Orange (Tacview 육안 확인용)
# over-G·스핀 위반 판정은 두지 않는다 — L3 리미터(코너 플래토 ∩ 9G)가 구조적으로 방지.


@dataclass
class MatchResult:
    winner: str          # "blue" | "red" | "draw"
    condition: str       # "hard_deck" | "stall" | "health_zero" | "disqualified"
                         # | "wall_clock" | "timeout" | "no_contact" | "overtime"
    time_s: float
    hp_blue: float
    hp_red: float
    # 오버타임 판정 근거 — 참가자에게 "왜 졌는지" 설명하는 유일한 수단이라 결과에 싣는다.
    overtime: bool = False            # OT 구간에 진입했는가
    wez_time: dict | None = None      # 측별 누적 조준 시간 [s] (타이브레이크 ①)
    ata_mean: dict | None = None      # 측별 평균 ATA [deg] (타이브레이크 ②)


def _wez_damage(shooter: KinState, target: KinState, dt: float,
                overtime: bool = False) -> tuple[float, float]:
    """shooter 기수 기준 (WEZ 데미지 HP, ATA deg). geometry 는 meters.

    ATA 를 함께 돌려주는 이유: OT 타이브레이크 ②(평균 ATA)가 매 틱 필요한데,
    여기서 이미 만든 geometry 를 버리면 같은 계산을 한 번 더 하게 된다.
    """
    geom = CombatGeometry(shooter.pos_ned * FT_TO_M, target.pos_ned * FT_TO_M,
                          shooter.vel_ned * FT_TO_M, target.vel_ned * FT_TO_M,
                          shooter.phi, shooter.theta, shooter.psi,
                          target.theta, target.psi)
    return (WeaponEngagementZone.calculate_damage(geom, dt, overtime), geom.ata_deg())


class Match:
    def __init__(self, blue, red, duration_s: float = 300.0,
                 dt_phys: float = 1.0 / 120.0, l15_div: int = 2, l1_div: int = 6,
                 log_hz: float = 120.0, acmi_path: str | None = None,
                 wall_limit_s: float = 120.0, progress: bool = False,
                 live=None, acmi_comments: str | None = None,
                 overtime_s: float = 0.0):
        self.blue = blue
        self.red = red
        self.duration_s = float(duration_s)
        # 오버타임 길이 [s]. 0 = 비활성(훈련센터·예선 풀리그 전부). 현장 단판만 켠다 —
        # no_contact 쌍방 패는 "도주 페이오프 0"이라는 설계 의도인데, 리그에서 OT 를
        # 주면 그게 두 번째 기회가 된다.
        self.overtime_s = float(overtime_s)
        self.overtime = False            # 현재 OT 구간인가 (관측 in_overtime 과 동일)
        self.dt = float(dt_phys)
        self.l15_div = l15_div
        self.l1_div = l1_div
        self.log_every = max(1, round(1.0 / (log_hz * self.dt))) if log_hz > 0 else 0
        self.acmi_path = acmi_path
        self.acmi_comments = acmi_comments        # ACMI 헤더 Comments (매치 자기 식별)
        self.wall_limit_s = float(wall_limit_s)   # JSBSim hang 안전장치 → 무승부
        self.progress = progress                  # 터미널 \r 프로그레스 (stderr)
        self.live = live                          # TacviewRealtimeServer (읽기전용 중계, D5)
        self.hp = {"blue": HealthGauge(), "red": HealthGauge()}
        self._stall = {"blue": 0.0, "red": 0.0}   # <100kts 누적 체류 [s]
        # OT 타이브레이크 재료 (전 구간 누적 — 정규+OT).
        self._wez_time = {"blue": 0.0, "red": 0.0}   # 상대를 WEZ 안에 둔 누적 시간 [s]
        self._ata_sum = {"blue": 0.0, "red": 0.0}    # ATA 적산 [deg·tick]
        self._ata_n = 0
        self._last_hit_t = {"blue": -1e18, "red": -1e18}   # 사수별 직전 데미지 시각(피격 북마크 히스테리시스)
        self._hit_at = {"blue": -1e18, "red": -1e18}       # 표적별 직전 피격 시각 (색 플래시)
        self._shown_color = {}                             # ACMI 에 마지막으로 쓴 색 (변화시만 재선언)
        # 관찰층 시각화 상태 (기총빔·이벤트로그) — 결정 경로 무영향.
        self._guns = {100: GunVisualizer(100, "800000FF"),   # 반투명 파랑
                      200: GunVisualizer(200, "80FF0000")}   # 반투명 빨강
        self._prev_tac = {100: None, 200: None}
        self._prev_wez = {100: False, 200: False}

    def run(self) -> MatchResult:
        self.blue.setup()
        self.red.setup()
        writer = ACMIWriter(self.acmi_path, comments=self.acmi_comments) \
            if self.acmi_path else None
        n_reg = int(self.duration_s / self.dt)          # 정규 교전 틱 수
        n = n_reg + int(self.overtime_s / self.dt)     # + 오버타임 (비활성이면 동일)
        result = None
        wall0 = time.monotonic()
        try:
            for k in range(n):
                t = k * self.dt
                bs = self.blue.state(); rs = self.red.state()

                # 정규 시간 만료 — 승자가 있으면 여기서 끝. 미결정(무접촉·HP 동률)이면
                # 오버타임으로 넘어간다. OT 비활성이면 n == n_reg 라 이 분기는 없다.
                if k == n_reg:
                    result = self._regulation_expiry(t)
                    if result is not None:
                        if writer:
                            writer.event(t, f"{result.winner.upper()} WINS ({result.condition})")
                        break
                    self._begin_overtime(writer, t)

                if k % self.l1_div == 0:
                    if time.monotonic() - wall0 > self.wall_limit_s:
                        result = self._result("draw", "wall_clock", t)
                    else:
                        result = self._l1_tick(t, bs, rs)
                    if result is not None:
                        if writer:
                            writer.event(t, f"{result.winner.upper()} WINS ({result.condition})")
                        break
                if k % self.l15_div == 0:
                    self.blue.guidance_step(rs); self.red.guidance_step(bs)
                self.blue.control_step(rs); self.red.control_step(bs)
                self.blue.step_physics(); self.red.step_physics()

                # WEZ 데미지(양방향) — OT 구간에서는 완화 WEZ(6,000ft/45°)
                dmg_to_red, ata_blue = _wez_damage(bs, rs, self.dt, self.overtime)
                dmg_to_blue, ata_red = _wez_damage(rs, bs, self.dt, self.overtime)
                # 타이브레이크 재료. 데미지>0 ⟺ WEZ 안이므로 별도 판정이 필요 없다.
                self._ata_sum["blue"] += ata_blue
                self._ata_sum["red"] += ata_red
                self._ata_n += 1
                if dmg_to_red > 0:
                    self._wez_time["blue"] += self.dt
                if dmg_to_blue > 0:
                    self._wez_time["red"] += self.dt
                if dmg_to_red > 0:
                    self.hp["red"].take_damage(dmg_to_red, k); self.red.health = self.hp["red"].current_health
                if dmg_to_blue > 0:
                    self.hp["blue"].take_damage(dmg_to_blue, k); self.blue.health = self.hp["blue"].current_health
                if writer:   # 피격 버스트 시작마다 Tacview Bookmark (타임라인·이벤트로그에 시점 표시)
                    self._hit_bookmark(writer, t, "blue", "red", dmg_to_red)
                    self._hit_bookmark(writer, t, "red", "blue", dmg_to_blue)

                # 실속 누적 (비행 안전 위반 판정 입력)
                for side, st in (("blue", bs), ("red", rs)):
                    if st.kcas < STALL_KTS:
                        self._stall[side] += self.dt

                if writer and self.log_every and k % self.log_every == 0:
                    self._log_frame(writer, t, bs, rs, k, n)
                if self.progress and k % 60 == 0:   # 120Hz → 0.5s 간격 갱신
                    self._print_progress(t, k, n)

                result = self._judge(t)
                if result is not None:
                    if writer:
                        # 최종 프레임: 종료 tick 의 데미지 반영 상태(HP 0.0 등)를 기록.
                        # 정규 로그는 log_every 간격 + 데미지 전 스냅샷이라 최종값이 빠진다.
                        self._log_frame(writer, t, self.blue.state(), self.red.state(), k, n)
                        writer.event(t, f"{result.winner.upper()} WINS ({result.condition})")
                    break
            if result is None:
                result = self._expiry_result(n * self.dt)
                if writer:
                    writer.event(n * self.dt,
                                 f"{result.winner.upper()} WINS ({result.condition})")
        finally:
            if self.progress:
                print(file=sys.stderr)   # \r 줄 마감
            if writer:
                writer.close()
        # 교전(ACMI 생성)마다 무조건 디브리프 plot 산출 (관찰 전용·완전 가드,
        # 매치 결과 불변; env CORE2_AUTO_DEBRIEF=0 으로 비활성). 파일 close 후 호출.
        if self.acmi_path:
            auto_debrief(self.acmi_path)
        return result

    def _print_progress(self, t: float, k: int, n: int) -> None:
        width = 30
        fill = int(width * (k + 1) / n)
        bar = "#" * fill + "-" * (width - fill)
        print(f"\r  [{bar}] {t:6.1f}/{self.duration_s:.0f}s"
              f"  HP blue {self.hp['blue'].current_health:5.1f}"
              f"  red {self.hp['red'].current_health:5.1f}",
              end="", file=sys.stderr, flush=True)

    def _log_frame(self, writer: ACMIWriter, t: float, bs: KinState, rs: KinState,
                   k: int, n: int) -> None:
        # 관찰층 시각화 상태 (기총빔·이벤트로그) — lazy 초기화, 결정 경로 무영향(D5).
        if not hasattr(self, "_guns"):
            self._guns = {100: GunVisualizer(100, "800000FF"),   # 반투명 파랑
                          200: GunVisualizer(200, "80FF0000")}   # 반투명 빨강
            self._prev_tac = {100: None, 200: None}
            self._prev_wez = {100: False, 200: False}
        objs = []
        vis = []   # (oid, label, in_wez, tactic, lon, lat, alt_m, hdg, pitch)
        for oid, comb, st, foe, coal, cs in (
                (100, self.blue, bs, rs, "Allies", "blue_1"),
                (200, self.red, rs, bs, "Enemies", "red_1")):
            lon, lat, alt_m = ned_to_lonlat(st.pos_ned)
            # 에이전트 라벨(정책명)은 CallSign, Name 은 항상 기체 모델("F-16") — Tacview 는
            # Name 으로 3D 모델 DB 를 매칭하므로 파일럿 라벨을 넣으면 제네릭 심볼이 된다.
            # (comb.name 을 라벨로 덮는 호출부가 많아 관찰층에서 기체명으로 고정; 라벨은
            #  agent_name > comb.name(비기본) > blue_1/red_1 순으로 CallSign 에 보존.)
            label = getattr(comb, "agent_name", None) \
                or (comb.name if comb.name != "F-16" else None) or cs
            obj = ACMIObject(id=oid, lon=lon, lat=lat, alt_m=alt_m,
                             roll_deg=np.degrees(st.phi), pitch_deg=np.degrees(st.theta),
                             yaw_deg=np.degrees(st.psi) % 360.0,
                             name="F-16", color=comb.color, coalition=coal, callsign=label)
            geom = CombatGeometry(st.pos_ned, foe.pos_ned, st.vel_ned, foe.vel_ned,
                                  st.phi, st.theta, st.psi, foe.theta, foe.psi)
            wez_geom = CombatGeometry(st.pos_ned * FT_TO_M, foe.pos_ned * FT_TO_M,
                                      st.vel_ned * FT_TO_M, foe.vel_ned * FT_TO_M,
                                      st.phi, st.theta, st.psi, foe.theta, foe.psi)
            rng_ft = float(np.linalg.norm(foe.pos_ned - st.pos_ned))
            cmd = getattr(comb, "_cmd", None)          # L1 명령 (scripted 는 없음)
            tactic = getattr(cmd, "name", getattr(comb, "maneuver", None))
            gc = getattr(comb, "_gc", None)
            g_tgt = getattr(gc, "g_target", None)
            plant = getattr(comb, "plant", None)       # scripted 상대는 없음 → Nz 생략
            nz = plant["accelerations/Nz"] if plant is not None else None
            audit = getattr(gc, "audit", None) or {}   # L2 감사 → ACMI (요요 육안 확인)
            flags = getattr(comb, "last_flags", None) or {}   # L3 리미터 포화
            limited = "".join(ax for ax, key in (("P", "p_limited"), ("Q", "q_limited"),
                                                 ("R", "r_limited")) if flags.get(key)) or "-"

            in_wez = WeaponEngagementZone.is_in_wez(wez_geom, self.overtime)
            attrs = flight_attrs(np.degrees(st.psi) % 360.0, st.kcas)
            attrs.update(combat_attrs(
                rng_ft, geom.ata_deg(), geom.aa_deg(), geom.hca_deg(), geom.rolloff_deg(),
                geom.closure_rate() * FT_S_TO_KT, st.health,
                in_wez, tactic=tactic, g_target=g_tgt,
                g_mode=audit.get("g_mode"), power_mode=audit.get("power_mode"),
                aim_above=audit.get("aim_above_ft"),
                pursuit=getattr(cmd, "pursuit", None), g_burst=audit.get("g_burst"),
                dphi_deg=audit.get("dphi_deg"), g_avail=audit.get("g_avail"),
                limited=(limited if flags else None),
                lead_time=audit.get("lead_time_s"), lag_dist=audit.get("lag_dist_ft"),
                mode=audit.get("mode"), nz=nz))
            tel = comb.telemetry()
            if tel is not None:
                attrs.update(control_attrs(tel.throttle, tel.ail_cmd, tel.elev_cmd,
                                           tel.rud_cmd, tel.ail_pos, tel.elev_pos, tel.rud_pos))
            # AOA/Beta (core-live replay 규약 이식) — plant 있는 파일럿만, 완전 가드.
            pl = getattr(comb, "plant", None)
            if pl is not None:
                try:
                    attrs["AOA"] = f"{pl['aero/alpha-deg']:.2f}"
                    attrs["Beta"] = f"{pl['aero/beta-deg']:.2f}"
                except Exception:
                    pass
            attrs["StepsElapsed"] = f"{k + 1}/{n}"
            # 피격 플래시: 피격 후 HIT_FLASH_S 동안 Orange, 격추(HP 0)는 Grey 고정.
            # Color 는 변할 때만 재선언 (첫 선언은 frame() 의 정적 선언이 담당).
            side = "blue" if oid == 100 else "red"
            color = ("Grey" if self.hp[side].current_health <= 0.0
                     else "Orange" if t - self._hit_at[side] <= HIT_FLASH_S
                     else comb.color)
            if self._shown_color.get(side, comb.color) != color:
                attrs["Color"] = color
            self._shown_color[side] = color
            obj.attrs = attrs
            objs.append(obj)
            vis.append((oid, label, attrs["InWEZ"] == "True", tactic, lon, lat,
                        alt_m, np.degrees(st.psi) % 360.0, np.degrees(st.theta)))
        writer.frame(t, objs)
        if self.live is not None:                 # 실시간 중계 (파일과 동일 프레임)
            self.live.send_frame(t, objs)
        # ── Tacview Event Log + 기총빔 (core-live replay.py 이식, 관찰 전용) ──
        for oid, label, wez, tac, lon, lat, alt_m, hdg, pitch in vis:
            if tac is not None and tac != self._prev_tac[oid]:
                writer.message(oid, f"[{label}] {tac}")
                self._prev_tac[oid] = tac
            if wez and not self._prev_wez[oid]:
                writer.message(oid, f"[{label}] GUN WEZ — firing")
            self._prev_wez[oid] = wez
            self._guns[oid].step(writer._f, wez, lon, lat, alt_m, hdg, pitch)

    def _display_name(self, side: str) -> str:
        comb = self.blue if side == "blue" else self.red
        return getattr(comb, "agent_name", None) or side.capitalize()

    def _hit_bookmark(self, writer, t: float, shooter: str, target: str, dmg: float) -> None:
        """데미지 버스트 시작 시 Bookmark 이벤트 1개 — 연속 피격은 HIT_REARM_S 히스테리시스로 1개만.
        타임라인·이벤트로그에 "누가 언제 맞았나"를 표시(사수→표적, 표적 잔여 HP)."""
        if dmg <= 0:
            return
        self._hit_at[target] = t
        if t - self._last_hit_t[shooter] > HIT_REARM_S:   # 직전 버스트와 떨어짐 = 새 버스트
            writer.event(t, f"HIT {self._display_name(shooter)}→{self._display_name(target)}"
                            f"  HP {self.hp[target].current_health:.0f}")
        self._last_hit_t[shooter] = t

    def _result(self, winner: str, condition: str, t: float) -> MatchResult:
        return MatchResult(winner, condition, t, self.hp["blue"].current_health,
                           self.hp["red"].current_health,
                           overtime=self.overtime,
                           wez_time=dict(self._wez_time),
                           ata_mean={sd: self._ata_mean(sd) for sd in ("blue", "red")})

    def _l1_tick(self, t: float, bs: KinState, rs: KinState):
        """L1 tick. 참가자 트리(policy) 예외는 엔진 크래시가 아니라
        해당 측 DISQUALIFY 판정으로 격리한다."""
        for comb, foe, side in ((self.blue, rs, "blue"), (self.red, bs, "red")):
            try:
                comb.tactic_step(foe)
            except Exception:
                return self._result("red" if side == "blue" else "blue",
                                    "disqualified", t)
        return None

    def _judge(self, t: float):
        """판정 우선순위: hard_deck > stall(안전 위반) > health_zero.
        (disqualified/wall_clock 은 L1 tick 에서, timeout 은 루프 종료에서.)"""
        def reason(side: str, comb) -> str | None:
            if -comb.state().pos_ned[2] < HARD_DECK_FT:
                return "hard_deck"
            if self._stall[side] >= STALL_LIMIT_S:
                return "stall"
            if self.hp[side].current_health <= 0.0:
                return "health_zero"
            return None

        rb, rr = reason("blue", self.blue), reason("red", self.red)
        if rb is None and rr is None:
            return None
        winner = "draw" if (rb and rr) else ("red" if rb else "blue")
        cond = next(c for c in ("hard_deck", "stall", "health_zero") if c in (rb, rr))
        return self._result(winner, cond, t)

    def _leader(self) -> str:
        hb, hr = self.hp["blue"].current_health, self.hp["red"].current_health
        if abs(hb - hr) < 1e-6:
            return "draw"
        return "blue" if hb > hr else "red"

    # ── 만료 판정 (정규 / 오버타임) ──────────────────────────────────
    def _engaged(self) -> bool:
        """피해 교환이 있었는가 — 무접촉(쌍방 패) 판정 기준(RULEBOOK §5-6).

        무접촉 타임아웃 = 쌍방 패(0점). 도주가 무승부 1점을 벌어 격추패보다 이득이
        되는 구멍을 막는다. 이격 자체는 정당한 BFM 이므로 처벌하지 않는다 — 익스텐드
        후 재교전해서 한 발이라도 맞히면 교전으로 잡힌다.
        판정 기준은 **피해 교환**이다(2026-08-01). 구 기준(사거리 진입 이력)은
        3,000ft 를 한 번 스치면 영구 성립하는 래치라, 그 뒤 300초를 도망쳐도 timeout
        무승부 1점이 들어왔다 — 도주 페이오프가 래치로 되살아났었다.
        """
        return any(g.current_health < g.max_health for g in self.hp.values())

    def _ata_mean(self, side: str) -> float:
        """전 구간 평균 ATA [deg] — 낮을수록 기수를 적에게 두었다는 뜻."""
        return self._ata_sum[side] / self._ata_n if self._ata_n else 180.0

    def _regulation_expiry(self, t: float) -> MatchResult | None:
        """정규 300초 만료 판정 (OT 활성일 때만 호출).

        승자가 정해지면 MatchResult, **미결정이면 None** → 오버타임 진입.
        미결정 = 무접촉(양측 무피해) 또는 HP 완전 동률. 현행 엔진 실측으로는
        전자가 13.7%, 후자가 0.1% 다 — 현장 단판에서 위너가 안 나오는 사고의
        실체는 무접촉이다.
        """
        if not self._engaged():
            return None
        winner = self._leader()
        return None if winner == "draw" else self._result(winner, "timeout", t)

    def _begin_overtime(self, writer, t: float) -> None:
        """OT 진입 — WEZ 완화 + 트리 관측(in_overtime) 전환."""
        self.overtime = True
        self.blue.overtime = True     # scripted 상대도 속성만 받고 무시한다
        self.red.overtime = True
        if writer:
            writer.event(t, "OVERTIME")

    def _expiry_result(self, t: float) -> MatchResult:
        """루프 소진 결과. OT 미진입이면 룰북 §5-6/7, 진입했으면 오버타임 판정."""
        if not self.overtime:
            engaged = self._engaged()
            return self._result(self._leader() if engaged else "draw",
                                "timeout" if engaged else "no_contact", t)
        winner = self._leader()
        if winner == "draw":
            winner = self._tiebreak()
        return self._result(winner, "overtime", t)

    def _tiebreak(self) -> str:
        """OT 만료 HP 동률의 최종 판정 (RULEBOOK 「오버타임」).

        ① 누적 조준 시간 — 상대를 WEZ 안에 둔 시간이 긴 쪽. 복싱 판정의 유효타·
           공격성 관례. HP 동률이면 서로 준 피해가 같다는 뜻이라, 같은 피해를 더 긴
           조준으로 만든 쪽이 교전을 지배했다고 본다.
        ② 평균 ATA — ①의 연속 일반화("누가 더 기수를 적에게 두었나"). 무접촉 OT 는
           ①이 0=0 이라 여기서 갈린다. **거리는 쌍의 속성이라 양측이 정의상 같아
           판별에 못 쓴다** — 평균 거리 안이 기각된 이유다.
        둘 다 동률이면 draw — 동일 트리 제출 수준에서만 도달하고, 그때의 시드 승계는
        엔진이 아니라 운영 규칙이 정한다.
        """
        wb, wr = self._wez_time["blue"], self._wez_time["red"]
        if wb != wr:
            return "blue" if wb > wr else "red"
        ab, ar = self._ata_mean("blue"), self._ata_mean("red")
        if ab != ar:
            return "blue" if ab < ar else "red"
        return "draw"
