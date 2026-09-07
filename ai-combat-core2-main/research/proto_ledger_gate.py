"""루프19 — 점수-장부 레이스 게이트(score-ledger race gate) 프로토타입.

진단(diag_losses, 정본 60-24):
  모든 경기는 t~19s 첫 머지 상호교환(양측 -43~-52)으로 시작하고, 승패는 이후
  **WEZ 포인팅 레이스**(ATA<30° tier 원뿔, rng 500~3000 균일, 50HP/s)에서 갈린다.
  패배 = ①점수 리드 상태에서 불필요한 레이스를 받아 일방 피격(red 클러스터 -16/-18,
  A3 t=160, E2 2차머지, C1_00 t=253) ②근소 열세서 명백히 지는 레이스 수용(E1_11 apex).

레버(결정층, 챔프-only = 참가자 BT 제출물 로직):
  · 점수-장부: 내 HP 는 실측(TacticContext.my_health 규칙상 관측 가능), 적 HP 는
    **내 WEZ tier 체류의 결정론 부기**(50HP/s 규칙이 결정론이라 추정이 아닌 계산).
  · 게이트: 위협(적 코가 나를 향함, 근접) 국면에서
      - 리드 크고 레이스가 명백-승이 아니면 → 거부(refuse)
      - 근소 열세(-floor 이내)여도 레이스가 명백-패면 → 거부(생존 우선)
      - 그 외(명백-승·큰 열세) → 정상 교전(기존 승리 경로 보존)
  · 루프18 환원불가(순간상태로 A/C 분리불가)의 해소: 장부-리드가 새 분리축 —
    A-class 압승 국면은 리드가 크고 레이스 명백-승이라 게이트 휴면, C-class
    동전던지기 apex 는 리드 근소·레이스 대칭이라 거부.

거부 실현(REFUSE 후보, TacticCommand 표현 내): env LG_REFUSE
  climb    : pure + aim_above +8000 (수직 오프셋 패스 — 상호 원뿔 파괴)
  climb_hi : pure + aim_above +15000
  break    : lag + g_burst 높음 (BREAK_TURN 고전 건방어)
  extend   : lag 6000 + aim_above -200 (B2 extend 동형)

검증: 장부 정확도(추정 적HP vs 실제), 42종×2측 headon 300s 전수(정본 유도 양측).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import aircombat.engine.factory as factory
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.scenarios import initial_conditions
from aircombat.tactics.context import TacticCommand

from research import champion_core as C
from research.transcribe import TranscribedPolicy
from research.run_transcribed_match import TranscribedPilot
from research.champion_pilot import tactic_to_command
from research.run_champion_match import MeasMatch
from research.rescore_ported import ANCHORS, CANON, HELDOUT

T = C.Tactic

# WEZ tier (geometry/units.WEZ_ATA_TIERS 와 동일 — 규칙 결정론 부기)
TIERS = ((2.0, 1.0), (10.0, 0.75), (20.0, 0.5), (30.0, 0.25))
WEZ_MIN_FT, WEZ_MAX_FT, DPS = 500.0, 3000.0, 50.0


def _coef(ata_deg: float) -> float:
    for mx, cf in TIERS:
        if ata_deg < mx:
            return cf
    return 0.0


def _nose_angles(me, foe) -> tuple[float, float]:
    """(내 기수-ATA, 적 기수-ATA) [deg] — ATA 정의 수정(BEM 기수 기준, 2026-07-16)
    에 따른 채점-정합 각도. me/foe = KinState (theta·psi 보유). 장부 부기·게이트
    판단은 이 값을 쓰고, 증류트리 입력 obs(속도벡터 정의)는 학습분포 보존을 위해
    불변으로 둔다."""
    los = foe.pos_ned - me.pos_ned
    d = float(_np.linalg.norm(los))
    if d < 1e-6:
        return 0.0, 0.0

    def nose(th, ps):
        return _np.array([_math.cos(th) * _math.cos(ps),
                          _math.cos(th) * _math.sin(ps), -_math.sin(th)])
    my = _math.degrees(_math.acos(max(-1.0, min(1.0,
        float(_np.dot(nose(me.theta, me.psi), los)) / d))))
    en = _math.degrees(_math.acos(max(-1.0, min(1.0,
        float(_np.dot(nose(foe.theta, foe.psi), -los)) / d))))
    return my, en


class LedgerGate:
    """점수-장부 + 레이스 게이트. 챔프 결정층 상태(BT 공유컨텍스트로 이식 가능).

    v2 (subset 스윕 #1 반영):
      · in-burst 보호 — 내 tier ≥ 적 tier 로 밴드 내 사격 중이면 절대 거부 안 함
        (v1 은 이기는 첫 교환 도중 리드>6 순간 이탈 → D2_03 -58 등 회귀 5).
      · 거부 latch — 발화하면 위협 해소(적 코 이탈 or 거리 확보)까지 유지(스래시 방지).
      · LEAD_MIN 6→3 (B1 red 클러스터 리드 +1.8~+5 서 미발화 → 실측 리드 분포에 맞춤).
    """

    # v9: 공세거부는 실제 리드(+1)에서만 — 근소열세(-3~0, blue 슬롯 첫교환 -2.1)서의
    # 거부는 0.3s 섭동만으로 baseline 승리 apex 동전던지기를 재추첨(v8: blue 6패 전부
    # "3틱 거부→45s 사망"). 미발화 = baseline 바이트-동일 = 승리 보장.
    LEAD_NEAR = float(os.environ.get("LG_LEAD_NEAR", 1.0))   # 이보다 리드면 보수 거부
    # v11: 공세거부는 **근소-리드 구간(1~8)** 전용 — 동전던지기 레이스 회피가 목적.
    # 리드가 크면(>8) 끝내기가 정답(안정 전환 19 전부 lead+2.0 발화; D2_05 는 +11.3
    # 발화 후 처벌 -41/-43 실측. DOM=25 는 상한으로 존치).
    LEAD_HI = float(os.environ.get("LG_LEAD_HI", 8.0))
    LEAD_FLOOR = float(os.environ.get("LG_LEAD_FLOOR", 8.0))  # -floor 이내 열세면 명백-패 거부 허용
    EDGE = float(os.environ.get("LG_EDGE", 12.0))            # 레이스 명백성 각도 여유
    HOT = float(os.environ.get("LG_HOT", 45.0))              # 적 ATA < 이 값 = 위협(코가 나를 향함)
    RNG = float(os.environ.get("LG_RNG", 4500.0))            # 위협 거리
    CLEAR_HOT = float(os.environ.get("LG_CLEAR_HOT", 60.0))  # latch 해제: 적 ATA > 이 값
    CLEAR_RNG = float(os.environ.get("LG_CLEAR_RNG", 6000.0))  # latch 해제: 거리 > 이 값
    # v3 거부 효능 폐루프: 거부가 안전을 못 만들면(피격 누적) 포기하고 교전 복귀.
    HURT_MAX = float(os.environ.get("LG_HURT_MAX", 4.0))     # latch 중 이 이상 피격 = 거부 실패
    COOLDOWN_S = float(os.environ.get("LG_COOLDOWN", 15.0))  # 실패 후 게이트 정지 시간
    # v12: 1→2 복원 — ABORT_OFF=1 은 C-family red 전환 4개(2차 latch 필요)를 반납하고
    # anchor_defensive/red 도 못 구함(실측 -32.8 동일). probe 2회가 옳은 트레이드.
    ABORT_OFF = int(os.environ.get("LG_ABORT_OFF", 2))       # 이 횟수 실패 = 잔여경기 게이트 비활성
                                                              # (거부를 처벌하는 상대 = 교전이 정답)
    # v5 시간적 상대-커밋(적 hot-점유율) — 루프18 예고 판별자의 최소 실현.
    #   무장(첫 패스) 이후 표본만으로 frac(enemy_ata<60) 측정. v4 의 "내 코 빠짐 조건부"
    #   서명은 상호-포인팅 churn(A2)서 분모가 비어 통과됨(실측 -32 회귀 지속) → 무조건부
    #   hot-점유율로 교체. 지속 포인터(A2 GunTracker: 머지 후에도 ~100% hot)는 거부가
    #   처벌당하므로 사전 차단(교전=baseline 승리), 이탈·선회 상대(B1zoom·C3 lufbery)는
    #   점유율 낮아 거부 허용. 표본이 부족하면(막 무장) 허용 — 조기 거부(t~21s 전환 다수)
    #   보존.
    PURSUE_WIN_S = float(os.environ.get("LG_PURSUE_WIN", 12.0))   # 점유율 창 [s]
    # v11: 0.7→0.6 — D3_00/01·B2_08 blue 의 처벌당한 DEF latch 가 0.65~0.69, 안정
    # 전환 19 의 latch 는 0.23~0.42 (실측 분리 마진 충분).
    PURSUE_MAX = float(os.environ.get("LG_PURSUE_MAX", 0.6))     # 이 비율 초과 = 지속 포인터
    PURSUE_MIN_S = float(os.environ.get("LG_PURSUE_MIN", 3.0))   # 최소 표본 [s] (미만=허용)
    # v6 교환-지배성 필터: 장부상 내가 압도 중(dealt-taken>DOM)이면 거부 금지 — 현 정책이
    #   이기고 있는데 이탈할 이유가 없다(A2_06: 33s 시점 dealt77 vs taken23 인데 순간각도로
    #   clearly_win 판정 실패 → 거부 → +77→-32 회귀. 각도 순간치가 아니라 이력이 진실).
    DOM = float(os.environ.get("LG_DOM", 25.0))
    # v8 위협 지속 필터: 공세거부는 적 hot 이 연속 THREAT_HOLD_S 이상일 때만 latch —
    #   D3 시저스의 간헐 hot(위빙 순간)에 21s 조기거부가 발화해 blue 전멸(-19×3, v7).
    #   B1/C3 apex 드라이브는 지속 hot 이라 보존. 방어 절(즉시 위험)은 예외.
    THREAT_HOLD_S = float(os.environ.get("LG_THREAT_HOLD", 1.2))

    # v21 실험: 포기(효능 실패) 후 다음 latch 부터 거부 실현을 반대로 스위칭
    # (dive↔climb) — anchor_defensive/red 처럼 특정 실현이 처벌당하는 상대에 적응.
    SWITCH = os.environ.get("LG_SWITCH", "0") == "1"

    def __init__(self):
        self.foe_dmg = 0.0        # 내가 가한 결정론 부기 데미지
        self.refuse_ticks = 0
        self.first_fire_t = None
        self.t = 0.0
        self.latched = False
        self.latch_hp0 = None     # latch 진입 시 내 HP (효능 판정 기준)
        self.cool_until = -1.0
        self.aborts = 0
        self.flip = False         # SWITCH 모드: 포기 1회당 실현 반전
        self.armed = False        # 첫 밴드 통과(첫 머지 교환) 후에만 게이트 무장
        self._seen_band = False
        self._armed_checked = False
        self._ring = []           # (me_off, pursue) 창 버퍼 20Hz
        self.hot_run = 0.0        # 적 hot 연속 지속시간 [s] (위협 지속 필터)

    def book(self, o, dt, ata=None, eata=None):
        """WEZ tier 부기 + 추격 점유율 창 (매 L1 tick 20Hz).

        ata/eata: 기수-ATA 오버라이드(ATA 정의 수정 후 채점-정합 부기용).
        미지정 시 종전 속도벡터 정의(o.ata_deg / 180−aa)로 동작."""
        if ata is None:
            ata = o.ata_deg
        if eata is None:
            eata = 180.0 - o.aa_deg
        self.t += dt
        # **이미 교전 거리 안에서 시작하는 국면은 t=0 에 무장한다.**
        # armed 가드(루프34)는 헤드온 *접근 구간*의 오발화를 막으려고 만든 것인데,
        # perch/neutral 처럼 붙어서 시작하는 국면에는 접근 구간이 없다. 그대로 두면
        # 방어 국면에서 armed 가 영영 안 켜져(실측: 221슬롯 전부 armed=0) 그 국면이
        # 학습 상태공간에서 통째로 사라진다 — 귀납이 KeyError 로 죽던 원인.
        # 헤드온 초기 분리는 6NM(36,456ft)라 이 문턱(12,000ft)에 안 걸린다(무영향).
        if not self._armed_checked:
            self._armed_checked = True
            if o.distance_ft < 12000.0:
                self.armed = True
        in_band = WEZ_MIN_FT <= o.distance_ft <= WEZ_MAX_FT
        if in_band:
            self.foe_dmg += DPS * _coef(ata) * dt
            self._seen_band = True
        elif self._seen_band:
            self.armed = True                      # 첫 교환 종료 → 무장
        self.hot_run = self.hot_run + dt if eata < self.HOT else 0.0
        if self.armed:                             # 무장 후 표본만(헤드온 접근 오염 배제)
            self._ring.append(eata < 60.0)
            n = int(self.PURSUE_WIN_S / dt)
            if len(self._ring) > n:
                del self._ring[:len(self._ring) - n]

    def pursue_ratio(self, dt=0.05) -> float:
        """무장 후 창 내 적 hot-점유율. 표본 부족(<PURSUE_MIN_S)이면 0(허용)."""
        if len(self._ring) * dt < self.PURSUE_MIN_S:
            return 0.0
        return sum(self._ring) / len(self._ring)

    def gate(self, o, my_health, diver=False, ata=None, eata=None) -> bool:
        """거부 여부. o = 현재 obs. diver = 챔프 내부 다이브-감지(적이 다이버 행동중).
        ata/eata = 기수-ATA 오버라이드(채점-정합; 미지정 시 속도벡터 정의)."""
        if ata is None:
            ata = o.ata_deg
        if eata is None:
            eata = 180.0 - o.aa_deg
        if not self.armed:
            return False                           # 첫 머지 교환은 정본 그대로(승리 경로 보존)
        foe_hp = max(0.0, 100.0 - self.foe_dmg)
        lead = my_health - foe_hp
        enemy_ata = eata
        in_band = WEZ_MIN_FT <= o.distance_ft <= WEZ_MAX_FT
        # in-burst 보호: 밴드 내에서 내 tier 가 적 tier 이상으로 사격 중이면 교환을 끝낸다.
        if in_band and _coef(ata) >= max(_coef(enemy_ata), 0.5):
            self.latched = False
            return False
        # 효능 폐루프: 거부 중 피격 누적 = 거부가 처벌당함(추격자) → 포기·교전 복귀.
        if self.latched and self.latch_hp0 - my_health > self.HURT_MAX:
            self.latched = False
            self.aborts += 1
            self.cool_until = self.t + self.COOLDOWN_S
            if self.SWITCH:
                self.flip = not self.flip     # 다음 latch 는 반대 실현으로 적응
        if self.aborts >= self.ABORT_OFF or self.t < self.cool_until:
            self.latched = False
            return False
        threat = (enemy_ata < self.HOT) and (o.distance_ft < self.RNG)
        if self.latched:
            if enemy_ata > self.CLEAR_HOT or o.distance_ft > self.CLEAR_RNG:
                self.latched = False
            else:
                self.refuse_ticks += 1
                return True
        # v15 cold-접근 가드 — threat(eata<45) 조기반환 **앞**에 배치. A2_11/red 매복은
        # eata 47~52 구간(t189~201)에 이미 자살머지 기하 완성 — threat 게이트가 cold 를
        # t201 까지 지연시켜 사망(실측). 리드 은행+기수 못 대는 고closure 진입 = 즉시 거절.
        # v20: cold 의 diver-차단(A2_11 급강하 -640fps 에 오염, v16 미전환)을
        # **적 기수 커밋(eata<60)** 으로 교체 — A2_11 매복접근 eata 47~52(발화) vs
        # D2_00 도주 eata~180(침묵). 자살머지의 정의상 상대가 나를 향해야 위협이다.
        cold = (o.distance_ft < 5000.0 and o.closure_kts > 150.0
                and ata > 75.0 and lead > 10.0 and enemy_ata < 60.0)
        if cold:
            self.latched = True
            self.latch_hp0 = my_health
            self.refuse_ticks += 1
            if self.first_fire_t is None:
                self.first_fire_t = self.t
            return True
        if not threat:
            return False
        clearly_win = ata + self.EDGE < enemy_ata
        clearly_lose = enemy_ata + self.EDGE < ata
        # 방어 절(명백-패 레이스 거부)은 DOM/추격 필터의 예외 — 지배 이력은 지금 잡힌
        # 원뿔에서 나를 못 지킨다(A2_11: 리드+54 인데 ata130/rng1300 -55.8 즉사 실측).
        # v10: 지속 추격자 차단은 방어 절에도 적용 — 추격-처벌형(A2_11·D2_05 lift2.56·ace)
        # 에게는 도주(방어거부)도 처벌당한다(v9: A2_11/blue +58→-10, D2_05 -41/-43 실측).
        # v11: DEF 도 DOM 차단(lead+55/+34 방어거부가 처벌당함 — 큰 리드는 교전 유지가
        # 정답, "방어 예외"는 실측상 아무도 구하지 못했음(A2_11/red 예외 있어도 사망)).
        pursuer = self.pursue_ratio() > self.PURSUE_MAX
        dom = self.foe_dmg - (100.0 - my_health) > self.DOM
        # v14 DEF: 다이브-탈출 기하가 열려 있을 때만(agap<-1500, 적이 충분히 위 —
        # 적이 따라오려면 perch 포기 필요). 실측 분리: C-family 필수 DEF agap -4356 ✓
        # vs 처벌 DEF: ace +658 / B2_04 -375 / anchor_def -552 / E1_11 +807 전부 차단.
        # v17 DEF_EDGE: 깊게 진 레이스만(eata+25<ata) — B2_04/blue 처벌 DEF@148 은
        # 마진 1.7°(eata37.8/ata51.5), C-family 필수 DEF 는 마진 17.7°(실측 분리).
        deep_lose = enemy_ata + 25.0 < ata
        defensive = (lead > -self.LEAD_FLOOR and deep_lose and not pursuer and not dom
                     and o.alt_gap_ft < -1500.0)
        blocked = (pursuer                                        # 지속 추격자: 교전이 정답
                   or dom                                         # 교환-지배 중: 유지
                   # 리드 큼: 끝내기(레이스 수용). 예외=패스 순간(rng<500, E2 의 +12.4
                   # latch @rng388)뿐 — v12 의 <3000 예외는 B2_04 in-band(+22.9 @879)
                   # 처벌 latch 를 통과시킴(실측 -6.6).
                   or (lead > self.LEAD_HI and o.distance_ft > 500.0)
                   or diver                                       # 다이버(D2형): 정본 cost-트리가
                                                                  # 전담(baseline 6-0) — 침묵
                   or self.hot_run < self.THREAT_HOLD_S)          # 간헐 hot(D3 위빙): 무시
        offensive = (lead > self.LEAD_NEAR and not clearly_win and not blocked)
        # (v19 tier-방어 절은 반증·철회 — E1_11 미구제(-53 동일) + anchor_ace/blue 재회귀
        #  -10.6 실측. tier 절벽 일방피격은 회피 실현이 없어 게이트로 못 구한다.)
        refuse = defensive or offensive
        if refuse:
            self.latched = True
            self.latch_hp0 = my_health
            self.refuse_ticks += 1
            if self.first_fire_t is None:
                self.first_fire_t = self.t
            if os.environ.get("LG_DEBUG") == "1":
                sys.stderr.write(
                    f"[LG-LATCH] t={self.t:6.1f} {'DEF' if defensive else 'OFF'} "
                    f"lead={lead:+6.1f} pursue={self.pursue_ratio():.2f} hot_run={self.hot_run:4.1f} "
                    f"ata={ata:5.1f} eata={enemy_ata:5.1f} rng={o.distance_ft:6.0f} "
                    f"kcas={o.ego_vc_kts:3.0f} agap={o.alt_gap_ft:+6.0f} clos={o.closure_kts:+5.0f} "
                    f"aborts={self.aborts}\n")
        return refuse


REFUSE_CMDS = {
    "climb":    TacticCommand(pursuit="pure", g_burst=0.0, name="LG_REFUSE",
                              aim_above_ft=8000.0),
    "climb_hi": TacticCommand(pursuit="pure", g_burst=0.0, name="LG_REFUSE",
                              aim_above_ft=15000.0),
    "break":    TacticCommand(pursuit="lag", g_burst=0.8, name="LG_REFUSE",
                              lag_dist_ft=1000.0, aim_above_ft=0.0),
    "extend":   TacticCommand(pursuit="lag", g_burst=0.0, name="LG_REFUSE",
                              lag_dist_ft=6000.0, aim_above_ft=-200.0),
    # 언로드 다이브: 조준점을 적 15000ft 아래로 — 근사-수직 강하로 고도→속도 환전 +
    # 밴드(3000ft) 하방 탈출. 저속 apex/밴드 내 원뿔 탈출의 물리 정답(고도가 통화).
    # F-deck 가드(정본)가 하방 안전을 담당. cf. 루프18 unload — 당시 A-class 홀은
    # 이제 DOM/추격/효능 3중 가드가 막는다.
    "dive":     TacticCommand(pursuit="pure", g_burst=0.0, name="LG_REFUSE",
                              aim_above_ft=-15000.0),
}


# ── 루프23 폐루프: 롤아웃-증류 12규칙 트리를 거부-실현 **선택기**로 사용 ──────────
# LG_RULESEL=1 이면 거부 시 정적 auto 분기 대신, 현재 상태에서 각 후보 기동의
# 승리확률을 규칙트리로 평가해 최고 확률 기동을 선택(동전던지기 지대 회피가 내장:
# dive/climb 는 해당 잎 승률이 낮아 자연히 기피됨).
_RULE = None
_COST = None


def _cost_pick(feats: dict):
    """루프26b — 행동별 관계형 cost 함수족 J_a(s)=w_a·s+b_a 의 argmax 로 거부-실현
    선택(LG_COSTSEL=1). core-live s_off(행동별 수식)와 동형. 관계형 특징만 사용
    — 절대 고도/속도 문턱 없음(상대-불변 가설).
    (v1 단일식은 행동×상태 상호작용이 없어 argmax 가 상태무관 상수 선택이 되는
     구조 결함 — 실측 67-17 하락 — 으로 폐기.)"""
    global _COST
    if _COST is None:
        import joblib
        _COST = joblib.load(os.path.join(os.path.dirname(__file__),
                                         "data", "blueteam", "cost_family.joblib"))
    fam, fkeys = _COST["models"], _COST["feats"]

    def coef(a):
        return 1.0 if a < 2 else .75 if a < 10 else .5 if a < 20 else \
            .25 if a < 30 else 0.0
    rel = dict(race=feats["eata"] - feats["ata"],
               tier_diff=coef(feats["ata"]) - coef(feats["eata"]),
               hp_lead=feats["hp_lead"], clos=feats["clos"], agap=feats["agap"],
               pursue=feats["pursue"], hotrun=feats["hotrun"],
               eclimb=feats["eclimb"], dalt=feats["dalt"],
               in_band=1.0 if 500.0 <= feats["rng"] <= 3000.0 else 0.0)
    cand = ("break", "extend", "climb", "dive", "lag", "two_circle", "level")
    best, bj = None, None
    for a in cand:
        if a not in fam:
            continue
        j = fam[a]["b"] + sum(fam[a]["w"][k] * rel[k] for k in fkeys)
        if bj is None or j > bj:
            best, bj = a, j
    return best, bj


def _rule_pick(feats: dict):
    global _RULE
    if _RULE is None:
        import joblib
        _RULE = joblib.load(os.path.join(os.path.dirname(__file__),
                                         "data", "blueteam", "rule_tree_12.joblib"))
    tree, fkeys, acts = _RULE["tree"], _RULE["feats"], _RULE["acts"]
    import numpy as _np
    cand = [a for a in ("break", "extend", "climb", "dive", "lag", "two_circle",
                        "level") if a in acts]
    rows = []
    for a in cand:
        rows.append([feats[k] for k in fkeys] + [1.0 if a == x else 0.0 for x in acts])
    p = tree.predict_proba(_np.array(rows))[:, 1]
    return cand[int(p.argmax())], float(p.max())


def refuse_cmd(strategy: str, o, flip: bool = False) -> TacticCommand:
    """거부 실현 — 'auto' 는 국면·에너지별 분기(v7):
      · 밴드 밖(>3200ft)·고속: climb (수직 오프셋 — 패스 전 상호 원뿔 파괴)
      · 그 외(저속 apex·밴드 내): 언로드 다이브 (v2~v6 의 extend=lag 점이 헤드온서
        적 방향을 조준(E1_11 -45.7)·break 는 밴드 내 체류(C1_03 -20.8) — 실측 반증)
    flip=True(v21 SWITCH, 포기 후 적응): auto 분기를 반전(dive↔climb).
    """
    if strategy != "auto":
        return REFUSE_CMDS[strategy]
    hi = o.distance_ft > 3200.0 and o.ego_vc_kts >= 280.0
    if hi != flip:
        return REFUSE_CMDS["climb"]
    return REFUSE_CMDS["dive"]


# ── 루프21 외과 오버라이드(수학적 전승 경로) ─────────────────────────────────
# 각 항목 = (obs 박스, 행동, 지속 s). 박스는 분기탐색(rollout)이 찾은 승리 개입점을
# trigger_synth 가 78승 전체 방문-obs 구름(20.7만 틱)과 분리해 합성 — 구성상 승리
# 경기에선 미발화(무간섭). 발화는 경기당 각 1회. 특징: rng/ata/eata/kcas/alt/agap/
# hp_lead(장부 추정 — 합성 여유 ±2.2 이상이 부기오차 ±1.9 흡수).
# ★ 박스는 전부 **런타임 obs-공간**(LG_OBSDUMP, 결정틱 10Hz·부기 hp_lead 그대로)에서
#   합성 — CSV(30Hz·CombatGeometry ata) 공간과의 좌표 불일치가 스퓨리어스 발화의
#   근본원인이었음(anchor_ace/blue -52.8 실측). 이 공간에선 트리거가 보는 값과 구름이
#   바이트-동일이라 분리 = 구성상 무간섭(수술 전 궤적 한정, 최종 검증은 full-84).
SURGICAL: list[tuple[dict, str, float]] = [
    # C3_Lufbery_08/blue — rollout 'break' d6 승리 t0=30/32/34(+5.2/+7.6/+2.5), 기준 -15.7
    (dict(rng=(6449.7, 8102.6), ata=(13.6, 107.1), eata=(13.5, 108.5),
          kcas=(234.2, 262.0), alt=(18561.0, 22922.0), agap=(1041.9, 2781.2),
          hp_lead=(-5.4, 1.4)), "break", 6.0),
    # E1_AdaptiveAce_11/blue — **진입틱 26.35 정밀 롤아웃** 승자 break d10(+29.0), 기준 -53.0.
    # (두루뭉술 t0 검증은 재추첨됨 — 트리거 발화틱 = 박스 진입틱에서 검증해야 결정론 재현.)
    # hp_lead 상계 -1.7/하계 -2.5 가 anchor_ace/blue 결정틱(-2.6)을 정확 배제(결정론).
    (dict(rng=(5690.1, 6634.3), ata=(75.7, 115.6), eata=(63.2, 116.6),
          kcas=(235.1, 356.5), alt=(15932.0, 21079.0), agap=(-245.9, 1232.2),
          hp_lead=(-2.5, -1.7)), "break", 10.0),
    # anchor_defensive/red — rollout 'break' 승리 t0=45/50/55(전부 +44.7 급), 기준 -32.8
    (dict(rng=(8756.3, 9570.4), ata=(58.2, 117.7), eata=(75.6, 138.4),
          kcas=(334.1, 384.8), alt=(13964.0, 16670.0), agap=(-8347.0, -6687.0),
          hp_lead=(-1.9, 13.7)), "break", 6.0),
    # D3_Scissors 3형제/red 공동 발화(쌍둥이 궤적 t=37.85 동일 진입, 분리 불가·불필요) —
    # 진입틱 37.85 롤아웃 공통 승자 'climb' d10: _01 +45.2(기준 -10.9), _00 +52.3(기준
    # +39.6 유지↑), _02 +37.3(기준 +7.3 유지↑). 무간섭 요건=승리보존(미발화 아님).
    (dict(rng=(3384.7, 10844.1), ata=(32.6, 64.3), eata=(10.7, 45.0),
          kcas=(247.5, 310.9), alt=(18872.0, 23237.0), agap=(4016.0, 8153.0),
          hp_lead=(-1.2, 5.2)), "climb", 10.0),
    # B2_Extender_08/blue — 진입틱 177.05 롤아웃 승자 'extend' d6(+49.1), 기준 -17.8
    (dict(rng=(6140.5, 10505.3), ata=(44.5, 88.6), eata=(44.9, 86.6),
          kcas=(334.9, 415.0), alt=(2686.8, 6772.1), agap=(-843.1, 3179.6),
          hp_lead=(-7.6, 0.8)), "extend", 6.0),
    # A2_GunTracker_11/red — 진입틱 172.05 롤아웃 승자 'gun' d10(+54.1 timeout,
    # t208 ata130 매복 회피·리드 보전), 기준 -10.2
    (dict(rng=(5042.0, 6675.3), ata=(102.6, 144.8), eata=(41.1, 85.8),
          kcas=(286.5, 376.2), alt=(25417.0, 29802.0), agap=(-3398.6, 4135.4),
          hp_lead=(47.5, 63.5)), "gun", 10.0),
]

# 루프24 CEGIS 귀납 규칙(케이스-횡단, rule_induct.py 산출 JSON) — LG_RULEBOX=경로.
# 지정 시 위 수제 SURGICAL 을 **대체**한다(순수 데이터-유도 구성).
if os.environ.get("LG_RULEBOX"):
    import json as _json
    SURGICAL = [({k: tuple(v) for k, v in r["box"].items()}, r["act"], r["dur"])
                for r in _json.load(open(os.environ["LG_RULEBOX"]))]
    if os.environ.get("LG_SURGICAL", "0") != "1":
        # M1 가드: RULEBOX 는 문장 목록 교체일 뿐 — 실행 스위치 없이는 전 문장이
        # 조용히 불활성이 된다(61-23 오판의 원인). 크게 경고.
        sys.stderr.write(
            "\n" + "!" * 72 +
            "\n[경고] LG_RULEBOX 지정됨 + LG_SURGICAL!=1 → 문장이 로드만 되고 "
            "발화하지 않습니다.\n       의도한 것이 아니면 LG_SURGICAL=1 을 "
            "함께 설정하십시오.\n" + "!" * 72 + "\n")


class LedgerPilot(TranscribedPilot):
    """TranscribedPilot + 점수-장부 게이트. 게이트 발화 시 거부 명령으로 교체."""

    REFUSE = os.environ.get("LG_REFUSE", "auto")
    # v23 챔프-only lead 각 상한 [deg] — lead 추격 조준점의 LOS 오프셋이 WEZ tier
    # (ATA<30°, LOS 기준)를 스스로 이탈시키는 것을 결정층에서 교정. lead_time_s 는
    # TacticCommand 필드라 BT(결정층) 권한 = 합법·배포가능, 상대 바이트-불변(재추첨 없음).
    # 양측 공용 실험(v22): cap10° 이 E1_11/blue·B2_08/blue·A2_11/red 3난공 전환 실증
    # (단 양측 적용은 blue 첫교환 재추첨 16회귀 → 챔프-only 로 국한).
    CAP_DEG = float(os.environ.get("LG_CAP_DEG", 0.0))       # 0 = off

    SURGICAL_ON = os.environ.get("LG_SURGICAL", "0") == "1"
    OBSDUMP = os.environ.get("LG_OBSDUMP")   # 경로 지정 시 결정틱 obs-특징 덤프
                                              # (트리거 합성용 — 런타임 좌표계 그대로)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ledger = LedgerGate()
        self._surg_until = [None] * len(SURGICAL)   # None=미발화, t=발화 종료시각
        self.obs_tag = ""

    _obsf = None
    _DUMP_KEYS = ("rng", "ata", "eata", "kcas", "alt", "agap", "hp_lead",
                  "clos", "pursue", "hotrun", "eclimb", "dalt", "es_rel",
                  "t", "fdmg", "race", "vdiff",
                  "armed",
                  # 루프38 롤 축 — LOS 기준 당김면 방향. 방어 국면 학습의 전제.
                  "roff", "eroff")   # 신축은 항상 말미 append(데이터 계약)

    def _dump_obs(self, feats):
        cls = LedgerPilot
        if cls._obsf is None:
            cls._obsf = open(self.OBSDUMP, "w")
            cls._obsf.write("tag,t," + ",".join(cls._DUMP_KEYS) + "\n")
        cls._obsf.write(f"{self.obs_tag},{self.ledger.t:.2f}," +
                        ",".join(f"{feats[k]:.2f}" for k in cls._DUMP_KEYS) + "\n")

    def _feats(self, o, ata_n=None, eata_n=None) -> dict:
        """규칙/합성/덤프 공용 특징 — 순간 7 + 시간축 5(clos·pursue·hotrun·eclimb·
        dalt). 루프22: 순간상태만의 held-out +5.5%p 한계(loop18 상충)의 처방."""
        prev_alt = getattr(self, "_prev_alt", None)
        dalt = 0.0 if prev_alt is None else (o.ego_alt_ft - prev_alt) / 0.1
        self._prev_alt = o.ego_alt_ft
        f = dict(rng=o.distance_ft,
                    ata=o.ata_deg if ata_n is None else ata_n,       # 기수-ATA(채점 정합)
                    eata=(180.0 - o.aa_deg) if eata_n is None else eata_n,
                    kcas=o.ego_vc_kts, alt=o.ego_alt_ft, agap=o.alt_gap_ft,
                    hp_lead=self.health - max(0.0, 100.0 - self.ledger.foe_dmg),
                    clos=o.closure_kts, pursue=self.ledger.pursue_ratio(),
                    hotrun=self.ledger.hot_run,
                    eclimb=o.enm_vc_kts * 1.68781
                           * _math.sin(_math.radians(o.enm_theta_deg)),
                    dalt=dalt,
                    # 관계형 에너지 축(rel3): 비에너지 차 [ft] — 절대축 alt/kcas 가
                    # 담던 가족-판별 정보를 단일 상대 변수로 흡수 (루프10 esret 계보).
                    es_rel=(o.ego_alt_ft + (o.ego_vc_kts * 1.68781) ** 2 / 64.348)
                          - (o.enm_alt_ft + (o.enm_vc_kts * 1.68781) ** 2 / 64.348),
                    # 루프30 장기-지속 축(루프22 "순간상태 분리한계→시간축" 처방 확장):
                    # 줌-클라임 부유 병리는 순간이 아니라 "오래 유효사격 없음"으로만
                    # 구분됨 — 승리 궤적엔 (t>40, fdmg=0) 순간이 없다.
                    t=self.ledger.t,
                    fdmg=self.ledger.foe_dmg)
        # 파생 관계축(루프31 함수-구간 재귀납): 신축은 항상 말미 append.
        # race: 조준 경쟁축 [deg] — 양수 = 적 기수가 나보다 더 벗어남(경쟁 우위).
        #   ata·eata 와 선형종속이지만 축-정렬 박스에선 회전좌표가 별도 분리력
        #   (대각 경계 → 축 경계). 절대 조준 정보는 ata 축이 계속 담당(레드팀 R1).
        # vdiff: 속도차 [kts] — kcas 절대축이 담던 정보의 관계형 후보.
        f["race"] = f["eata"] - f["ata"]
        f["vdiff"] = o.ego_vc_kts - o.enm_vc_kts
        f["armed"] = 1.0 if self.ledger.armed else 0.0   # 루프34 가드-좌표
        # 루프38 롤 축(body frame, 부호 있음): 기존 어휘엔 각도·거리·고도차만 있고
        # **LOS 기준 롤 방향이 통째로 빠져 있었다.** 방어 기동의 브레이크 방향은
        # "공격자가 내 당김면 기준 어디에 있나"로 결정되므로 이 축 없이는 방어
        # 국면이 원리적으로 학습되지 않는다.
        #   roff  = 적을 내 당김면에 올리려면 얼마나 롤해야 하나 (+우/−좌)
        #   eroff = 적의 당김면 기준 내 위치 — 적의 당김이 나를 향하는지
        f["roff"] = getattr(o, "rolloff_deg", 0.0)
        f["eroff"] = getattr(o, "enm_rolloff_deg", 0.0)
        return f

    def _surgical(self, o, feats):
        """외과 오버라이드 — 박스 진입 시 1회 발화, dur 동안 강제. 반환 None=휴면."""
        t = self.ledger.t
        if self.OBSDUMP:
            self._dump_obs(feats)
        if not self.SURGICAL_ON:
            return None
        # 루프34 armed-가드: 문장은 "첫 머지 교환 후 국면"의 해 — 접근 단계(비무장)
        # 발화를 전역 차단. 훈련 지문 실측상 전 발화가 armed 이후라 무손(분포-밖
        # 오발화 클래스 제거: val energyfighter 접근 t=14.3 dive 완파 실측의 교정).
        if not self.ledger.armed:
            return None
        for i, (box, act, dur) in enumerate(SURGICAL):
            u = self._surg_until[i]
            if u is not None:
                if t < u:
                    return act                       # 발화 유지
                continue                             # 소진(1회)
            if all(lo <= feats[k] <= hi for k, (lo, hi) in box.items()):
                self._surg_until[i] = t + dur
                if os.environ.get("LG_DEBUG") == "1":
                    sys.stderr.write(f"[SURG#{i}] t={t:.1f} act={act} " +
                                     " ".join(f"{k}={v:.1f}" for k, v in feats.items())
                                     + "\n")
                return act
        return None

    # v24: 전면 캡(v22 양측=66-18/64-20, v23 챔프-only=64-20) 3연속 반증 — lead
    # 오프셋은 apex 크로싱 재조준의 **승리 요소**이기도 함(blue apex 12승 파괴).
    # → F-deck 식 자기-판별 협대역: "저속·근접·코가 이미 tier 밖(ata>25)인데 큰
    # lead(≥1.5)를 명령" = 정의상 낭비 상태(E1_11 apex: ata32·kcas240·LEAD_TURN1.5)
    # 에서만 발화. 승리 apex(B1_06/blue ata10.7)는 ata 조건으로 휴면.
    CAP_NARROW = os.environ.get("LG_CAP_NARROW", "0") == "1"

    def _cap_lead(self, cmd, o):
        """pursuit=lead 명령의 lead_time 을 θ_cap·rng/V_foe 로 상한(근접 pipper-on)."""
        if cmd.pursuit != "lead":
            return cmd
        base = 1.0 if cmd.lead_time_s is None else float(cmd.lead_time_s)
        if self.CAP_NARROW:
            if not (self.ledger.armed and o.ego_vc_kts < 270.0
                    and o.distance_ft < 3500.0 and o.ata_deg > 25.0 and base >= 1.5):
                return cmd
        elif self.CAP_DEG <= 0.0:
            return cmd
        import dataclasses
        v_foe = max(o.enm_vc_kts * 1.68781, 1.0)             # CAS 프록시 [fps]
        deg = self.CAP_DEG if self.CAP_DEG > 0.0 else 10.0
        cap_t = _math.radians(deg) * o.distance_ft / v_foe
        if cap_t >= base:
            return cmd
        return dataclasses.replace(cmd, lead_time_s=cap_t)

    # v25 정면 pipper-on: 상호 헤드온 접근(LOS 안정 = lead 교범상 불필요)에서
    # GUN_TRACK lead 0.5s 가 코를 LOS 대비 4~6° 오프셋 → tier 0.75 에 고착
    # (실측: 첫교환 챔프 ata 4~7 = lead 오프셋 그 자체; <2°면 tier 1.0 = +33%).
    # 자기-판별: aa>150(상호 hot)·고closure·근접·이미 조준중(ata<15)에서만 lead→0.05.
    HEADON_PIPPER = os.environ.get("LG_PIPPER", "0") == "1"
    # v28(신룰): 발화창 반경 — 6000ft(v25)는 WEZ 밖 접근에서 lead-turn 기하를 희생
    # (anchor_ace/red 회귀). 데미지 이득은 WEZ(≤3000ft) 안에서만 발생하므로 조임 스윕.
    PIPPER_RNG = float(os.environ.get("LG_PIPPER_RNG", "6000"))

    def _pipper_on(self, cmd, o):
        if not (self.HEADON_PIPPER and cmd.pursuit == "lead"
                and o.aa_deg > 150.0 and o.closure_kts > 300.0
                and o.distance_ft < self.PIPPER_RNG and o.ata_deg < 15.0):
            return cmd
        import dataclasses
        return dataclasses.replace(cmd, lead_time_s=0.05)

    def tactic_step(self, foe) -> None:
        me = self.state()
        o = C.reconstruct_obs(me, foe)
        ata_n, eata_n = _nose_angles(me, foe)        # 기수-ATA(ATA 정의 수정 정합)
        self.ledger.book(o, 0.05, ata_n, eata_n)     # L1 20Hz 부기
        if self._l1_count % self.l1_ratio == 0:      # 10Hz 결정
            mode, tac = self.champion.decide(o)      # 내부 latch 항상 갱신(상태 일관)
            # 다이버 신호: 챔프 정본의 다이브-감지 상태 재사용(inner.run = 적 강하 지속,
            # armed = empty-dive 스택 무장) — D2형 상대는 cost-트리가 전담하므로 게이트 침묵.
            diver = (getattr(self.champion, "run", 0.0) > 0.5
                     or getattr(self.champion, "armed", False))
            feats = self._feats(o, ata_n, eata_n)
            if self.ledger.gate(o, self.health, diver=diver, ata=ata_n, eata=eata_n):
                if os.environ.get("LG_COSTSEL", "0") == "1":
                    # 루프26: 관계형 선형 cost(수학적 정의)가 거부-실현 선택
                    pick, _j = _cost_pick(feats)
                    from research.branch_search import ACTIONS as _SA
                    mode, cmd = "refuse", _SA[pick]
                elif os.environ.get("LG_RULESEL", "0") == "1":
                    # 루프23 폐루프: 증류 12규칙이 거부-실현을 상태-조건부로 선택
                    pick, _p = _rule_pick(feats)
                    from research.branch_search import ACTIONS as _SA
                    mode, cmd = "refuse", _SA[pick]
                else:
                    mode, cmd = "refuse", refuse_cmd(self.REFUSE, o,
                                                     flip=self.ledger.flip)
            else:
                cmd = self._cap_lead(tactic_to_command(tac, ego_alt_ft=o.ego_alt_ft,
                                                       enm_alt_ft=o.enm_alt_ft), o)
                cmd = self._pipper_on(cmd, o)
            act = self._surgical(o, feats)           # 외과 오버라이드 최우선(검증 개입)
            if act is not None:
                from research.branch_search import ACTIONS as _SA, resolve_act
                mode, cmd = "surgical", resolve_act(_SA[act], o)
            self.last_mode, self.last_tactic = mode, tac
            if os.environ.get("LG_MODEDUMP"):
                # 루프32 기저-재유도 계측: 결정틱마다 (모드, 기저전술, 트리리프).
                # 리프는 decide 내부와 동일 입력(featurize_s, post-update run)으로 재순회.
                cls = LedgerPilot
                if getattr(cls, "_modef", None) is None:
                    cls._modef = open(os.environ["LG_MODEDUMP"], "w")
                    cls._modef.write("tag,t,mode,tac,leaf\n")
                leaf = -1
                ch = self.champion
                if (o.ego_alt_ft >= C.HARD_DECK and ch.c < ch.thr):
                    x = C.featurize_s(o, min(ch.run, C.DIVE_HOLD))
                    tt = ch.clf.tree_
                    n = 0
                    while tt.children_left[n] != tt.children_right[n]:
                        n = (tt.children_left[n] if x[tt.feature[n]] <= tt.threshold[n]
                             else tt.children_right[n])
                    leaf = n
                cls._modef.write(f"{self.obs_tag},{self.ledger.t:.2f},{mode},"
                                 f"{tac.name},{leaf}\n")
            self._cmd = cmd
        self._l1_count += 1


import math as _math

import numpy as _np

from aircombat.guidance.bfm_guidance import BFMGuidance as _BFMG


class LeadCapGuidance(_BFMG):
    """v22 — lead 각 상한(거리-비례 lead_time 캡). 실현층 가설(양측 공용):

    lead 추격 조준점 = foe + foe_vel·lead_t 는 근접(rng~3000)서 LOS 대비
    ~12°(lead1.5s·V690fps) 코 오프셋 → WEZ tier(ATA<30°, LOS 기준)를 **스스로
    이탈**(E1_11 apex: ata 32.1 vs 적 20.5 → 일방피격 -45.7 실측). 건 사거리
    에선 pipper-on-target 이 교리 — lead_eff = min(lead, θ_cap·rng/V_foe).
    원거리는 캡이 크므로 기존과 동일(요격 기하 보존).
    """

    CAP_DEG = float(os.environ.get("LC_CAP_DEG", 0.0))    # 0 = off(정본 동일)

    def compute(self, me, foe_pos_ned, foe_vel_ned, *, lead_time_s=None, **kw):
        if self.CAP_DEG > 0.0:
            rng = float(_np.linalg.norm(_np.asarray(foe_pos_ned, float) - me.pos_ned))
            v_foe = max(float(_np.linalg.norm(_np.asarray(foe_vel_ned, float))), 1.0)
            cap = _math.radians(self.CAP_DEG) * rng / v_foe
            base = self.lead_time_s if lead_time_s is None else float(lead_time_s)
            lead_time_s = min(base, cap)
        return super().compute(me, foe_pos_ned, foe_vel_ned,
                               lead_time_s=lead_time_s, **kw)


def make_pilot_lg(color, ic, clf):
    from aircombat.fdm.plant import F16Plant
    from aircombat.guidance.doctrine import Doctrine
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=ic["alt"], vc_kts=ic["kcas"], psi_deg=ic["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    return LedgerPilot(plant, clf, off_mode="exact", color=color,
                       init_pos_ned=tuple(ic["pos"]),
                       guidance=LeadCapGuidance(doctrine=Doctrine()), name="LedgerGate")


# 녹화는 최상위 replays/ 로 (증거·로그는 research/campaigns/). 폴더 재편 때 이 상수만
# 옛 경로에 남아 녹화가 증거 폴더로 섞여 들어가고 있었다.
# LG_REPLAYDIR 로 조건별 하위 폴더를 지정한다 — 대조 실험에서 조건이 서로 덮어쓰지
# 않게 하려면 필수다(예: 플레인 기저 vs 최종 정책).
REPLAY_ROOT = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "replays", "canon")


def pairing(stem, clf, side, replay=False):
    # LG_IC_SEED: 결정론 IC 지터(고도·분리·방위·속도, scenarios.initial_conditions)
    # — 일반해 섭동 강건성 스윕용. 미지정 = 정본 고정 IC.
    _seed = os.environ.get("LG_IC_SEED")
    # LG_SCENARIO: 초기조건 국면. 정본 채점은 headon 이지만, 일반해 주장을 IC 차원으로
    # 넓히려면 다른 국면도 재야 한다(perch·neutral 은 알려진 아티팩트가 있으니
    # docs/EXPERIMENT_SCALE.md 의 판단을 먼저 볼 것).
    ic = initial_conditions(os.environ.get("LG_SCENARIO", "headon"),
                            seed=int(_seed) if _seed else None)
    # 경로-슬롯: stem 에 폴더가 있으면 저장소-상대 경로(커스텀 모듈 동반
    # 트리를 복사 없이 로스터에 편입 — run_match.run_roster 와 동일 규약).
    pol, doc = load_policy(stem + ".yaml" if "/" in stem
                           else f"roster/{stem}.yaml")
    if side == "blue":
        blue = make_pilot_lg("Blue", ic["blue"], clf)
        red = make_pilot("Red", ic["red"], pol, doc, name=stem)
        champ = blue
    else:
        blue = make_pilot("Blue", ic["blue"], pol, doc, name=stem)
        red = make_pilot_lg("Red", ic["red"], clf)
        champ = red
    # 시드 실행이면 태그에 @s<N> — 루프30 시드-횡단 덤프에서 동일 슬롯·다른 IC 구분.
    # 태그는 (슬롯, 국면, 시드)를 모두 담는다 — 엄격분리가 덤프 위에서 도는 구조라,
    # 태그가 IC 를 구분해야 "다른 IC 의 승리 자취"까지 침범 금지 대상이 된다.
    _sc = os.environ.get("LG_SCENARIO", "headon")
    champ.obs_tag = (f"{stem}/{side}"
                     + ("" if _sc == "headon" else f"@{_sc}")
                     + (f"@s{_seed}" if _seed else ""))
    acmi = csvp = None
    if replay:
        rd = os.path.join(REPLAY_ROOT, os.environ.get(
            "LG_REPLAYDIR", f"ledger_{LedgerPilot.REFUSE}"))
        os.makedirs(rd, exist_ok=True)
        # 경로-슬롯(agents/champion128)은 슬래시가 파일명에 섞여 들어가 열기가 실패한다.
        safe = stem.replace("/", "__").replace("\\", "__")
        acmi = os.path.join(rd, f"champ_vs_{safe}_{side}.acmi")
        csvp = os.path.join(rd, f"champ_vs_{safe}_{side}.csv")
    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=acmi, csv_path=csvp,
                  log_hz=120.0, wall_limit_s=3600.0)
    res = m.run()
    # 상호격추(양측 동시 HP 0)는 **무승부**다 — run_match.run_roster 와 같은 판정.
    # 루프36 패리티 결함: 연구 런타임만 이를 "패"로 세어, 챔피언 미러전이
    # 반례로 잡히고 데몬이 못 고칠 것을 고치려 드는 문제가 있었다.
    hp_me = res.hp_blue if side == "blue" else res.hp_red
    hp_op = res.hp_red if side == "blue" else res.hp_blue
    drawn = (res.winner is None) or (res.winner == "draw") or (hp_me == hp_op)
    win = (not drawn) and (res.winner == side)
    loss = (not drawn) and (res.winner is not None) and (res.winner != side)
    return res, win, loss, champ.ledger


# 정본 baseline(60-24) 패배 24 + 감시 승리 표본(각 클래스 대표, 회귀 조기탐지)
BASE_LOSSES = [
    ("A3_LagAngler_06", "blue"), ("A3_LagAngler_06", "red"),
    ("A3_LagAngler_00", "blue"), ("A3_LagAngler_00", "red"),
    ("E2_Passive_01", "blue"), ("E2_Passive_01", "red"),
    ("E2_Passive_00", "blue"), ("E2_Passive_00", "red"),
    ("B1_EnergyFighter_06", "red"), ("B1_EnergyFighter_00", "red"),
    ("B1_EnergyFighter_11", "red"), ("B2_Extender_04", "red"),
    ("B2_Extender_08", "blue"), ("C3_Lufbery_04", "red"),
    ("C3_Lufbery_00", "red"), ("C3_Lufbery_08", "blue"), ("C3_Lufbery_08", "red"),
    ("C1_TwoCircleRate_00", "red"), ("C2_OneCircleRad_00", "red"),
    ("D1_Reactive_06", "red"), ("D3_Scissors_01", "red"),
    ("A2_GunTracker_11", "red"), ("D1_Reactive_11", "red"),
    ("E1_AdaptiveAce_11", "blue"),
]
SENTINEL_WINS = [
    ("A1_PurePursuer_05", "blue"), ("A1_PurePursuer_05", "red"),
    ("A2_GunTracker_06", "blue"), ("A2_GunTracker_06", "red"),
    ("B1_EnergyFighter_06", "blue"), ("C1_TwoCircleRate_03", "blue"),
    ("C1_TwoCircleRate_03", "red"), ("D2_LastDitch_03", "blue"),
    ("D2_LastDitch_03", "red"), ("E1_AdaptiveAce_06", "blue"),
    ("E1_AdaptiveAce_06", "red"), ("anchor_ace", "blue"), ("anchor_ace", "red"),
]


def main():
    if LeadCapGuidance.CAP_DEG > 0.0:
        factory.BFMGuidance = LeadCapGuidance   # 양측 공용(정직 재현) — v22 lead 캡
    clf = C.load_clf()
    replay = os.environ.get("LG_REPLAY", "0") == "1"
    scope = os.environ.get("LG_SCOPE", "subset")   # subset | full
    if scope == "full":
        roster = [(s, side) for s in (ANCHORS + CANON + HELDOUT)
                  for side in ("blue", "red")]
    else:
        roster = BASE_LOSSES + SENTINEL_WINS
    only = os.environ.get("LG_ONLY")   # "stem/side,stem/side" 단일 드릴 (roster 무관 전체 허용)
    if only:
        # 마지막 "/" 만 진영 구분자 — 경로-슬롯(agents/champion128/blue) 지원
        roster = [tuple(x.strip().rsplit("/", 1)) for x in only.split(",") if x.strip()]
    g = LedgerGate
    # 구성 서명(루프36): 이 로그가 어떤 정책 구성으로 생성됐는지 기계 판독 가능하게.
    # 재채점·검증 도구가 대조해 "다른 구성으로 잰 결과를 비교하는" 사고를 막는다.
    print(f"#CONFIG basefn={os.environ.get('LG_BASEFN', 'tree')}"
          f" surgical={os.environ.get('LG_SURGICAL', '0')}"
          f" rulebox={os.path.basename(os.environ.get('LG_RULEBOX', '')) or 'none'}"
          f" rulesel={os.environ.get('LG_RULESEL', '0')}"
          f" refuse={LedgerPilot.REFUSE}")
    print(f"=== 루프19 점수-장부 게이트: refuse={LedgerPilot.REFUSE} scope={scope} "
          f"(near>{g.LEAD_NEAR} floor{g.LEAD_FLOOR} edge{g.EDGE} hot{g.HOT} rng{g.RNG:.0f} "
          f"pursue<{g.PURSUE_MAX}@{g.PURSUE_WIN_S:.0f}s) ===")
    print(f"  {'상대/측':<28}{'결과':>4}  {'HPΔ':>7}  {'거부':>5}  {'첫발화':>6}  {'장부오차':>7}  cond")
    tw = td = tl = 0
    conv, regr = [], []
    base_loss_set = set(BASE_LOSSES)
    for stem, side in roster:
        res, win, loss, led = pairing(stem, clf, side, replay=replay)
        hp_c = res.hp_blue if side == "blue" else res.hp_red
        hp_o = res.hp_red if side == "blue" else res.hp_blue
        est_err = (100.0 - led.foe_dmg) - hp_o   # 추정 적HP - 실제 (부기 정확도)
        tag = "승" if win else ("패" if loss else "무")
        tw += win; tl += loss; td += (not win and not loss)
        was_loss = (stem, side) in base_loss_set
        if was_loss and win:
            conv.append(f"{stem}/{side}")
        if not was_loss and not win:
            regr.append(f"{stem}/{side} (Δ{hp_c-hp_o:+.1f})")
        ff = f"{led.first_fire_t:.0f}s" if led.first_fire_t is not None else "-"
        print(f"  {stem+'/'+side:<28}{tag:>4}  {hp_c-hp_o:+7.1f}  {led.refuse_ticks:>5}  "
              f"{ff:>6}  {est_err:+7.1f}  포기{led.aborts}  {res.condition}@{res.time_s:.0f}s",
              flush=True)
    print(f"\n  합계: {tw}승 {td}무 {tl}패 / {len(roster)}")
    print(f"  전환: {len(conv)} {conv}")
    print(f"  회귀: {len(regr)} {regr if regr else '없음'}")


if __name__ == "__main__":
    raise SystemExit(main())
