"""ChampionPilot — core-live FullUnifiedPolicy 를 core2 5계층 엔진 위에서 구동하는 측정용 파일럿.

Pilot 을 상속해 L1(tactic_step)만 교체한다. tactic_step(foe) 는 self.state()(me)와 foe 두
KinState 를 받으므로, 여기서 core-live obs 를 재구성해 챔프 결정기를 돌리고, 방출된 Tactic 을
core2 TacticCommand(7-field)로 매핑한다. L2/L3/L4(guidance/control/physics)는 Pilot 그대로 상속.

틱레이트: match L1 = 20Hz(l1_div=6). core-live 챔프 = 10Hz. 재스케일 위험을 피하려 챔프 결정기는
**네이티브 10Hz** 로 구동한다(매 2번째 tactic_step 에서만 decide, 사이엔 직전 _cmd 유지) →
정수-틱 의미론(hist[-10]·run+=0.1·LAMBDA per-tick) 완전 보존.

★ 손실 번역층(TACTIC_MAP): core-live 전술은 자체 가이던스에서 (psi*,h*,v*) setpoint 로 실현되고,
core2 는 BFMGuidance 가 (pursuit,g_burst,aim_above,lead_time,lag_dist,mode)를 다르게 실현한다.
아래 매핑은 교리 의도(nose-on gun WEZ dwell 목적)에 맞춘 최선의 근사이며, 이 갭의 비용은
gate-2 측정(확정 규칙 300s)이 수치로 드러낸다. GAP-3(SMART_DIVE 540kt sprint knob 부재)는 champion_core 참조.
"""
from __future__ import annotations

from aircombat.engine.pilot import Pilot
from aircombat.tactics.context import TacticCommand

from . import champion_core as C

T = C.Tactic

# ── core-live guidance.py 수직채널 상수(전술별 고도 설정점 h_star) ──────────────
# core2 BFMGuidance 는 적-상대 조준(aim[2] -= aim_above_ft)만 가능하고 절대/자기-상대
# 고도 설정점이 없다. core-live guidance 는 전술마다 (psi*, h*, v*) 설정점을 내며 그 h*
# 다수가 **적과 무관**(CLIMB=절대10000, SMART_DIVE 하한, 수평전술=자기고도 유지)하다.
# 이 갭이 gate-2 손실의 구조적 원인(수평전술이 저고도 적을 따라 강하 → 덱-침범).
# 충실 포트: 전술별 h_star 를 obs 로 계산해 aim_above_ft = h_star - 적_alt 로 넘긴다.
# (core2 compute() 233행: L1 명시 aim_above_ft 는 mode 무관 항상 우선 → stable/cz 도 존중.)
HARD_DECK_FT    = 1000.0     # tactic.py — 미만 즉시 패배
SD_FLOOR_FT     = 3500.0     # _smart_dive: h*=max(적_alt, 3500) — 적 deck 미추종(에너지 유지)
ENERGY_FLOOR_FT = 5000.0     # _vertical_pursuit: h*=max(적_alt, 5000) (=HARD_DECK+4000)
LAG_BELOW_FT    = 500.0      # _lag_pursuit: h*=적_alt - 500
GUN_VERT_K      = 1.0        # _gun_track: h*=max(1000, 적_alt - K·(자기-적)) 관통 dive-aim
CLIMB_TARGET_FT = 10000.0    # _climb(ADAPTIVE off): h*=10000 절대(현방위 줌-클라임)

# ⚠️ 반증(2026 gate-2): hold-ego-altitude 를 수평 전술(PURE/LEAD_PURSUIT/LEAD_TURN/HEADON)에
# 적용하니 22승→14승 광역 회귀. 이유 = core2 는 **단일 조준점**이 비행경로(고도)와 건-조준(기수)을
# 겸한다. core-live 는 h_star(비행경로=자기고도)와 track/pipper(건-조준=적 기수정렬)를 **분리**하고,
# 승리는 후자(적 조준 강하)로 현금화한다. aim_above=0(적 조준) 은 그 승리 건-다이브를 실현하는
# 채널이었고, 이를 hold-ego 로 덮으면 현금화가 사라진다. → 수직채널 systematic 포트 철회.
# 결론: core2 고정 가이던스에 **고도유지⊕건조준 분리 채널이 없다**(구조적 표현갭). SMART_DIVE 하한만 유지.
def _hstar(t, ego_alt_ft, enm_alt_ft):
    """core-live guidance 전술별 고도 설정점 h_star [ft]. None = 정적 aim_above fallback.
    현재 SMART_DIVE 만 활성(하한 3500) — 22-0-10 최선상태. 나머지 hold-ego/dive 는 반증(위 주석)."""
    if t is T.SMART_DIVE:       return max(enm_alt_ft, SD_FLOOR_FT)
    return None

# ── Tactic → (pursuit, g_burst, lead_time_s, lag_dist_ft, mode) ──────────────────
# 수직채널(aim_above_ft)은 _hstar 로 동적계산. 여기 aim_above_ft 는 _hstar=None 전술의 fallback.
# stable=포인팅 추적(기수정렬), control_zone=1500ft WEZ 체류+lag편향.
TACTIC_MAP: dict = {
    # 공격/추격
    T.GUN_TRACK:        dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,   lead_time_s=0.5, mode="stable"),
    T.PURE_PURSUIT:     dict(pursuit="pure", g_burst=0.0, aim_above_ft=0.0,   mode="control_zone"),
    T.LEAD_PURSUIT:     dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,   lead_time_s=1.0),
    # LEAD_TURN: g_burst=0 으로 core2 교리 G-조절(에너지 백오프 포함)에 위임 — 반사적 max-G 는
    # bfm_guidance._regulate_g 조기반환으로 에너지 백오프를 우회해 고고도 수직줌→실속(gate-2 A류 2패).
    # core-live LEAD_TURN 도 비행층이 G 를 기하·에너지로 조절(반사적 max-G 아님)이라 이쪽이 더 충실.
    T.LEAD_TURN:        dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,   lead_time_s=1.5),
    T.LAG_PURSUIT:      dict(pursuit="lag",  g_burst=0.0, aim_above_ft=0.0,   lag_dist_ft=1500.0, mode="control_zone"),
    # HEADON: core-live guidance._dispatch 는 `LEAD_TURN | HEADON → _lead_turn` 로 **동일 실현**.
    # 따라서 포트도 LEAD_TURN 과 틱-동일 매핑이어야 충실(반사적 max-G 아님·코너속도 G-조절).
    # 종전 (g_burst=0.8, lead1.0) 은 종말 머지서 코너캡 과회전 → 기수이탈(ata 14→23.5), textbook_headon SD 2패.
    T.HEADON:           dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,   lead_time_s=1.5),
    T.SMART_DIVE:       dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,    lead_time_s=1.5),
    # 중립 선회
    T.ONE_CIRCLE:       dict(pursuit="lead", g_burst=0.8,  aim_above_ft=0.0),
    T.TWO_CIRCLE:       dict(pursuit="lag",  g_burst=0.8,  aim_above_ft=0.0,   lag_dist_ft=2000.0),
    T.ADAPTIVE:         dict(pursuit="pure", g_burst=0.0, aim_above_ft=0.0,   mode="control_zone"),
    T.ETM_TRACK:        dict(pursuit="lead", g_burst=0.0, aim_above_ft=0.0,   lead_time_s=2.0, mode="stable"),
    # 수직
    T.CLIMB:            dict(pursuit="pure", g_burst=0.0, aim_above_ft=5000.0),
    T.VERTICAL_PURSUIT: dict(pursuit="lead", g_burst=0.8,  aim_above_ft=2000.0, lead_time_s=1.0),
    # 방어
    T.BREAK_TURN:       dict(pursuit="lag",  g_burst=0.8,  aim_above_ft=0.0,   lag_dist_ft=1000.0),
}


def tactic_to_command(t, ego_alt_ft=None, enm_alt_ft=None) -> TacticCommand:
    spec = TACTIC_MAP.get(t)
    if spec is None:   # 미매핑 방어(정상 도달 불가) — pure 추격 기본
        spec = dict(pursuit="pure", g_burst=0.0)
    aim_above = spec.get("aim_above_ft")
    # 수직채널 충실 포트: 전술별 h_star → aim_above = h_star - 적_alt (obs 있을 때만).
    if ego_alt_ft is not None and enm_alt_ft is not None:
        h_star = _hstar(t, float(ego_alt_ft), float(enm_alt_ft))
        if h_star is not None:
            aim_above = h_star - float(enm_alt_ft)
    return TacticCommand(
        pursuit=spec["pursuit"], g_burst=spec["g_burst"], name=t.name,
        aim_above_ft=aim_above,
        lead_time_s=spec.get("lead_time_s"),
        lag_dist_ft=spec.get("lag_dist_ft"),
        mode=spec.get("mode"))


class ChampionPilot(Pilot):
    """FullUnifiedPolicy 구동 파일럿. 챔프는 10Hz(매 2번째 L1 tick)."""

    def __init__(self, plant, clf, l1_ratio: int = 2, **kw):
        super().__init__(plant, **kw)
        self.champion = C.FullUnifiedPolicy(clf)
        self.l1_ratio = int(l1_ratio)   # match L1(20Hz) 대비 챔프 tick 분주(2 → 10Hz)
        self._l1_count = 0
        self.last_mode = "core"
        self.last_tactic = None

    def tactic_step(self, foe) -> None:
        if self._l1_count % self.l1_ratio == 0:      # 10Hz 결정
            o = C.reconstruct_obs(self.state(), foe)
            mode, tactic = self.champion.decide(o)
            self.last_mode, self.last_tactic = mode, tactic
            self._cmd = tactic_to_command(tactic, ego_alt_ft=o.ego_alt_ft, enm_alt_ft=o.enm_alt_ft)
        self._l1_count += 1
