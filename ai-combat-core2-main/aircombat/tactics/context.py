"""L1 전술 컨텍스트 — BT tick 에 주입하는 관측 + 출력 명령.

py_trees 의 전역 blackboard 대신 명시적 context 객체를 tick 마다 넘긴다.
관측은 geometry/L2 가 계산한 값을 담고, Action 노드가 출력(pursuit/g_burst +
조준점 기하 오버라이드)을 여기 쓴다. trace 는 어느 조건이 참이었는지 기록해
전술 선택을 감사가능하게 한다.

시간(t_s/dt_s)은 TacticPolicy 가 tick 마다 자체 누적해 주입한다 — Commit/Cooldown
데코레이터의 결정론 시계(매치 시간 주입 불필요).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TacticContext:
    # ── 관측 (읽기전용; geometry/L2 산출) ──
    # 부호 규약: 두 계열이 기준이 다르다(의도). ①적 상대위치(alt_gap_ft=적−아군, +적이 위)
    # → "적 어디 있나"(foe_above/foe_below 가 부호 그대로 읽힘). ②내 우위 margin
    # (energy_diff_ft=아군−적, +내가 우세) → "내가 유리한가"(energy_advantage). 조건 가독성 최적화.
    ata_deg: float          # 내 기수→적 (0=조준)
    aspect_deg: float       # 적 기준 내 위치 (180=적이 날 정면조준=위협)
    range_ft: float
    closure_fps: float      # +접근 / -이탈
    kcas: float
    energy_diff_ft: float   # 아군-적 비에너지 (+우세) — margin 계열
    alt_gap_ft: float       # 적 고도 - 내 고도 (+적이 위) — 적 상대위치 계열
    alt_ft: float = 15000.0  # 내 절대고도 (MSL ft) — 하드덱 회피 판단
    vs_fps: float = 0.0     # 내 수직속도 [fps] (+상승/−강하) — 하드덱 예측 회복 판단
    my_health: float = 100.0
    # 적 HP 는 관측에 포함하지 않는다 — 룰북 정보 정책(적 상태는 교전 기하로만 추정)
    # 파이팅 속도 대역 — pilot 이 per-pilot Doctrine 에서 주입. doctrine 개방 시
    # L1 조건(below/above_fighting_speed 기본값)과 L2 조절이 같은 대역을 보게 하는 운반로.
    fighting_kts_lo: float = 325.0
    fighting_kts_hi: float = 375.0
    hca_deg: float = 0.0    # 종축 교차각(BEM Angle-Off, 0=동방향·180=헤드온) — 헤드온 판별
    # 수평 선회방향 (+1 우선회 / -1 좌선회 / 0 직선·미상) — pilot 이 20Hz 헤딩 미분으로 산출.
    # 1/2-circle flow 판별용: 반대 방향 = 1-circle, 같은 방향 = 2-circle (BEM 4.4.4)
    my_turn_dir: int = 0
    foe_turn_dir: int = 0
    # ── 확장 관측 (2026-07-18) — 상태-보유 커스텀 노드용 상대 정보.
    #    기존 조건들은 사용하지 않음(순수 추가). 전 참가자 동일 계층에서 채워짐.
    enm_alt_ft: float = 0.0        # 적 고도
    enm_kcas: float = 0.0          # 적 지시대기속도
    enm_theta_deg: float = 0.0     # 적 피치각
    ego_psi_deg: float = 0.0       # 내 방위각 [0,360)
    enm_psi_deg: float = 0.0       # 적 방위각 [0,360)
    vel_ata_deg: float = 0.0       # 속도벡터-기준 ATA (기수-기준은 ata_deg)
    vel_aa_deg: float = 0.0        # 속도벡터-기준 AA
    closure_kts: float = 0.0       # LOS 접근율 [kt] (+접근)
    dist_x_ft: float = 0.0         # 거리 — compute_obs 연산 순서 그대로 (동치용)
    nose_ata_x_deg: float = 0.0    # 내 기수-ATA — _nose_angles 연산 그대로
    nose_eata_x_deg: float = 0.0   # 적 기수-ATA — _nose_angles 연산 그대로
    # ── 국면 (Match 가 Pilot 을 통해 주입) ──
    # 오버타임 여부. 트리는 경과 시간을 볼 수 없으므로(CONDITIONS 에 시간 조건이 없다)
    # OT 전용 전술로 분기하려면 이 관측이 필요하다 — 없으면 참가자는 연습해 본 적 없는
    # 규칙(완화 WEZ)으로 결승을 치르게 된다. 조건 어휘는 in_overtime.
    overtime: bool = False

    # ── 시간 (TacticPolicy 가 주입; Commit/Cooldown 시계) ──
    t_s: float = 0.0
    dt_s: float = 1.0 / 20.0

    # ── 출력 (Action 노드가 기록) ──
    _pursuit: str = "lead"
    _tactic_name: str = "default"
    _aim_above_ft: float | None = None   # 조준점 수직 오프셋 [ft] (+위/-아래, None=교리 자동)
    _lead_time_s: float | None = None    # lead 예측시간 오버라이드 (None=가이던스 기본)
    _lag_dist_ft: float | None = None    # lag 후방거리 오버라이드 (None=가이던스 기본)
    _mode: str | None = None             # L2 가이드 모드 (stable|control_zone, None=기본 조절)
    _cz_range_ft: float | None = None    # control_zone 목표거리 오버라이드 (None=가이던스 기본)
    _g_burst: float | None = None        # 지속↔순간 봉투 보간 0~1 = 천장 (None=가이던스 기본 0)
    _g_full_ata_deg: float | None = None  # 명목 G 포화 ATA (None=가이던스 기본)
    _track_rng_ft: float | None = None   # 건 추적 하한 G 창 사거리 (None=가이던스 기본)
    _track_ata_deg: float | None = None  # 동 ATA 게이트 (None=가이던스 기본)
    trace: list = field(default_factory=list)

    def set_command(self, pursuit: str, name: str,
                    aim_above_ft: float | None = None,
                    lead_time_s: float | None = None,
                    lag_dist_ft: float | None = None,
                    mode: str | None = None,
                    cz_range_ft: float | None = None,
                    g_burst: float | None = None,
                    g_full_ata_deg: float | None = None,
                    track_rng_ft: float | None = None,
                    track_ata_deg: float | None = None) -> None:
        self._pursuit = pursuit
        self._tactic_name = name
        self._aim_above_ft = aim_above_ft
        self._lead_time_s = lead_time_s
        self._lag_dist_ft = lag_dist_ft
        self._mode = mode
        self._cz_range_ft = cz_range_ft
        self._g_burst = g_burst
        self._g_full_ata_deg = g_full_ata_deg
        self._track_rng_ft = track_rng_ft
        self._track_ata_deg = track_ata_deg


@dataclass(frozen=True)
class TacticCommand:
    pursuit: str        # "lead" | "pure" | "lag"
    name: str
    aim_above_ft: float | None = None
    lead_time_s: float | None = None
    lag_dist_ft: float | None = None
    mode: str | None = None
    cz_range_ft: float | None = None
    g_burst: float | None = None
    g_full_ata_deg: float | None = None
    track_rng_ft: float | None = None
    track_ata_deg: float | None = None
