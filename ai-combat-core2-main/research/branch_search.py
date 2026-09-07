"""루프21 — 반사실 분기 탐색(counterfactual branch search). 수학적 전승 공략 1단계.

원리: 벤치마크는 RNG 없는 완전 결정론 + 상대 고정 정책 ⇒ 각 경기 = 알려진 동역학의
단일-에이전트 최적제어. 패배 경기의 치명 교환 직전 윈도우에서 (개입시각 t0, 대체행동 a,
지속 d) 격자를 전수 시뮬레이션해 **승리 궤적의 존재 증명서**를 구성한다(존재 시 구성적,
부재 시 탐색실패 증거 — no-impossibility 원칙의 제약봉투 탐색).

2단계(별도): 발견된 승리 개입의 발화점 obs 를 84경기 승리-obs 구름과 분리하는
박스를 계산(무간섭 트리거 합성) → v20 에 그래프트 → 전수 재검증.

usage: BS_CASE="E1_AdaptiveAce_11/blue" BS_WIN="24,34" python -m research.branch_search
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.scenarios import initial_conditions
from aircombat.tactics.context import TacticCommand

from research import champion_core as C
from research.champion_pilot import tactic_to_command
from research.run_champion_match import MeasMatch
from research.proto_ledger_gate import (LedgerPilot, REFUSE_CMDS, refuse_cmd,
                                            LeadCapGuidance)

T = C.Tactic

# 개입 후보 — 거부 실현 4 + 대표 전술 4 (TacticCommand 로 통일)
ACTIONS: dict[str, TacticCommand] = {
    "climb": REFUSE_CMDS["climb"],
    "dive": REFUSE_CMDS["dive"],
    "break": REFUSE_CMDS["break"],
    "extend": REFUSE_CMDS["extend"],
    "gun": tactic_to_command(T.GUN_TRACK),
    "lag": tactic_to_command(T.LAG_PURSUIT),
    "two_circle": tactic_to_command(T.TWO_CIRCLE),
    "level": tactic_to_command(T.LEVEL_FLIGHT),
    # 신룰(기수-WEZ) 추가: 기수-온 사격 — lead 오프셋 제거로 tier 계단 최상단 점유.
    # 전역 파이퍼 창(LG_PIPPER)은 상충 레버로 반증(65-19, blue 5판 회귀) —
    # 언제 쓸지는 롤아웃→obs-박스 귀납이 상대-조건부로 결정한다.
    "gun_pure": TacticCommand("pure", False, "gun_pure", mode="stable"),
    # 루프35 ②층 — 에너지-관리 실현(두 홀드아웃 패배의 서명 "리드 후 장기전
    # 에너지 붕괴" 처방). unload=얕은 언로드(고도→속도 환전, dive -15000 보다
    # 완만·회복 여지), e_extend=함수형: 에너지 열세면 언로드-이탈, 아니면 상승-이탈.
    "unload": TacticCommand("pure", False, "unload", aim_above_ft=-8000.0),
}


def _es_rel(o):
    return ((o.ego_alt_ft + (o.ego_vc_kts * 1.68781) ** 2 / 64.348)
            - (o.enm_alt_ft + (o.enm_vc_kts * 1.68781) ** 2 / 64.348))


def e_extend(o):
    """함수형 액션(콜러블 — 매 결정틱 o 로 재평가): 에너지-조건부 이탈.
    열세(es_rel<-500)면 언로드-이탈(속도 재건), 아니면 완만 상승-이탈(고도 은행)."""
    up = -2500.0 if _es_rel(o) < -500.0 else 1500.0
    return TacticCommand("lag", False, "e_extend", lag_dist_ft=6000.0,
                         aim_above_ft=up)


ACTIONS["e_extend"] = e_extend


def resolve_act(a, o):
    """정적 명령 or 콜러블(함수형 액션) 해석 — 전 실행 경로 공용."""
    return a(o) if callable(a) else a


class ForcedPilot(LedgerPilot):
    """LedgerPilot(v20) + 창구간 [t0, t0+dur) 강제 개입. 그 외 틱은 v20 그대로
    (ledger·정책 내부상태는 계속 갱신 — 개입 종료 후 일관 복귀)."""

    def __init__(self, *a, force=None, **kw):   # force = (t0, dur, cmd)
        super().__init__(*a, **kw)
        self.force = force
        self.forced_ticks = 0

    def tactic_step(self, foe) -> None:
        super().tactic_step(foe)
        if self.force is None:
            return
        t0, dur, cmd = self.force
        t = self.ledger.t                        # 20Hz 부기 시계 [s]
        if t0 <= t < t0 + dur:
            if callable(cmd):                    # 함수형 액션: 관측으로 매 틱 재평가
                o = C.reconstruct_obs(self.state(), foe)
                self._cmd = cmd(o)
            else:
                self._cmd = cmd
            self.last_mode = "forced"
            self.forced_ticks += 1


def force_opponent(pilot, force):
    """레드팀 모드(BS_TARGET=opp, 구 red_search 흡수): **상대** 명령을 창구간
    [t0,t0+dur) 강제(20Hz 틱 시계). 자기측 강제는 ForcedPilot."""
    if force is None:
        return pilot
    orig = pilot.tactic_step
    n = [0]
    t0, dur, cmd = force

    def step(foe):
        orig(foe)
        t = n[0] * 0.05
        n[0] += 1
        if t0 <= t < t0 + dur:
            pilot._cmd = cmd
    pilot.tactic_step = step
    return pilot


def run_red(stem, champ_side, clf, force):
    """상대측 강제 롤아웃 — 챔프 승리 여부 반환 (개입-폐쇄 강건성 프로브)."""
    _seed = os.environ.get("LG_IC_SEED")
    # LG_SCENARIO: 되감기는 반례가 난 **그 초기조건**을 재현해야 한다 — 데몬이
    # IC 격자 위에서 돌면 국면이 headon 이 아닐 수 있다.
    ic = initial_conditions(os.environ.get("LG_SCENARIO", "headon"),
                            seed=int(_seed) if _seed else None)
    # 경로-슬롯: stem 에 폴더가 있으면 저장소-상대 경로(커스텀 모듈 동반
    # 트리를 복사 없이 로스터에 편입 — run_match.run_roster 와 동일 규약).
    pol, doc = load_policy(stem + ".yaml" if "/" in stem
                           else f"roster/{stem}.yaml")
    from research.proto_ledger_gate import make_pilot_lg, make_pilot
    from research.run_champion_match import MeasMatch
    if champ_side == "blue":
        blue = make_pilot_lg("Blue", ic["blue"], clf)
        red = force_opponent(make_pilot("Red", ic["red"], pol, doc, name=stem), force)
    else:
        blue = force_opponent(make_pilot("Blue", ic["blue"], pol, doc, name=stem), force)
        red = make_pilot_lg("Red", ic["red"], clf)
    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=None, csv_path=None,
                  log_hz=30.0, wall_limit_s=3600.0)
    res = m.run()
    hp_c = res.hp_blue if champ_side == "blue" else res.hp_red
    hp_o = res.hp_red if champ_side == "blue" else res.hp_blue
    return (res.winner == champ_side), hp_c - hp_o, res.condition, res.time_s


def run_forced(stem, side, clf, force, acmi=None):
    _seed = os.environ.get("LG_IC_SEED")   # 루프30: IC 봉투 케이스(슬롯×시드) 수색용
    # LG_SCENARIO: 되감기는 반례가 난 **그 초기조건**을 재현해야 한다 — 데몬이
    # IC 격자 위에서 돌면 국면이 headon 이 아닐 수 있다.
    ic = initial_conditions(os.environ.get("LG_SCENARIO", "headon"),
                            seed=int(_seed) if _seed else None)
    # 경로-슬롯: stem 에 폴더가 있으면 저장소-상대 경로(커스텀 모듈 동반
    # 트리를 복사 없이 로스터에 편입 — run_match.run_roster 와 동일 규약).
    pol, doc = load_policy(stem + ".yaml" if "/" in stem
                           else f"roster/{stem}.yaml")
    from aircombat.fdm.plant import F16Plant
    from aircombat.guidance.doctrine import Doctrine
    plant = F16Plant(dt=1.0 / 120.0)
    key = "blue" if side == "blue" else "red"
    plant.set_ic(alt_ft=ic[key]["alt"], vc_kts=ic[key]["kcas"], psi_deg=ic[key]["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    champ = ForcedPilot(plant, clf, off_mode="exact", color=key.capitalize(),
                        init_pos_ned=tuple(ic[key]["pos"]),
                        guidance=LeadCapGuidance(doctrine=Doctrine()),
                        name="LedgerGate", force=force)
    if side == "blue":
        blue, red = champ, make_pilot("Red", ic["red"], pol, doc, name=stem)
    else:
        blue, red = make_pilot("Blue", ic["blue"], pol, doc, name=stem), champ
    m = MeasMatch(blue, red, duration_s=300.0, acmi_path=acmi, csv_path=None,
                  log_hz=30.0, wall_limit_s=3600.0)
    res = m.run()
    hp_c = res.hp_blue if side == "blue" else res.hp_red
    hp_o = res.hp_red if side == "blue" else res.hp_blue
    return (res.winner == side), hp_c - hp_o, res.condition, res.time_s, champ.forced_ticks


def main():
    case = os.environ["BS_CASE"]                    # "stem/side"
    w0, w1 = (float(x) for x in os.environ["BS_WIN"].split(","))
    step = float(os.environ.get("BS_STEP", 2.0))
    durs = [float(x) for x in os.environ.get("BS_DURS", "3,6,10").split(",")]
    acts = os.environ.get("BS_ACTS")
    acts = list(ACTIONS) if not acts else acts.split(",")
    stem, side = case.split("/")
    clf = C.load_clf()
    red_mode = os.environ.get("BS_TARGET", "self") == "opp"   # 구 red_search 흡수

    if red_mode:
        # 레드팀: 상대에게 강제 개입을 쥐여주고 챔프가 그래도 이기는지 수색.
        # "★뚫림" = 챔프 패·무 = 실존 취약점(P3 개입-폐쇄 CEGIS 의 반례).
        cw, d, cond, tt = run_red(stem, side, clf, None)
        print(f"=== 레드팀 {case}  창[{w0:.0f},{w1:.0f}]s step{step:g} durs{durs} ===")
        print(f"  기준: 챔프 {'승' if cw else '패·무'} Δ{d:+.1f} {cond}@{tt:.0f}s")
        vulns = []
        t0 = w0
        while t0 <= w1:
            for a in acts:
                for dur in durs:
                    cw, dhp, cond, tt = run_red(stem, side, clf,
                                                (t0, dur, ACTIONS[a]))
                    tag = "  승" if cw else "★뚫림"
                    print(f"  t0={t0:5.1f} {a:<10} d={dur:4.1f} → {tag} "
                          f"Δ{dhp:+7.1f} {cond}@{tt:3.0f}s", flush=True)
                    if not cw:
                        vulns.append((t0, a, dur, dhp))
            t0 += step
        print(f"\n  뚫림 {len(vulns)}개: {vulns if vulns else '없음(강건성 증명)'}")
        return

    # 기준(무개입) 확인
    win, d, cond, tt, _ = run_forced(stem, side, clf, None)
    # 수확 조건 메타데이터(루프36): 재사용 시 조건 불일치를 데몬이 검출하도록
    # 첫 줄에 기계 판독 가능한 서명을 남긴다(구 파일은 서명 없음 = 불일치 처리).
    print(f"#HARVEST acts={','.join(sorted(acts))} durs={','.join(str(d) for d in sorted(durs))}"
          f" win={w0:.0f},{w1:.0f} draw_ok={os.environ.get('BS_DRAW_OK','1')}")
    print(f"=== 분기탐색 {case}  창[{w0:.0f},{w1:.0f}]s step{step:g} durs{durs} ===")
    print(f"  기준: {'승' if win else '패'} Δ{d:+.1f} {cond}@{tt:.0f}s")
    wins = []
    t0 = w0
    while t0 <= w1:
        for a in acts:
            for dur in durs:
                win, dhp, cond, tt, ft = run_forced(stem, side, clf,
                                                    (t0, dur, ACTIONS[a]))
                tag = "★승" if win else ("★무" if dhp >= 0.0 else "  패")
                print(f"  t0={t0:5.1f} {a:<10} d={dur:4.1f} → {tag} Δ{dhp:+7.1f} "
                      f"{cond}@{tt:3.0f}s ticks{ft}", flush=True)
                if win:
                    wins.append((t0, a, dur, dhp))
        t0 += step
    print(f"\n  승리 개입 {len(wins)}개: {wins if wins else '없음(탐색실패 증거)'}")


if __name__ == "__main__":
    raise SystemExit(main())
