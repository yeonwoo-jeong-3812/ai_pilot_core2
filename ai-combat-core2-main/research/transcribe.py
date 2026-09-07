"""완전 직역(형식명세) — champion(FullUnifiedPolicy) 결정로직을 **명시적 불리언 primitive**로
전사한 TranscribedPolicy. joblib clf.predict 대신 tree_ 를 명시 순회하고, 소프트블렌드 argmax
대신 off 우선순위 사다리를 쓴다. 목적: core2 YAML DSL(중첩 selector/condition + latch node)로
기계번역 가능한 형태임을 순수 파이썬에서 먼저 증명(골든 트레이스와 틱-동일).

구성상 틱-동일 보장 부분(동일 float 비교의 미러):
  · clf 트리 순회: node 마다 x[feat] <= thr (sklearn 과 동일)
  · override(w_circ/w_ext), deck, deck_suppress, hard-deck, latch(run·c) 점화식
유일 근사:
  · off 소프트-argmax → 우선순위 사다리(GUN>LAG>HEADON>SMART_DIVE). 실현 manifold(18446틱)에서
    argmax 와 일치함을 검증(넉나이프-에지 밴드는 robustness 주석). σ 게이트 부호점 = 사다리 임계.
"""
from __future__ import annotations

import math
import os

from research import champion_core as C

T = C.Tactic
_KT2FPS = 1.68781


# ── clf 트리 명시 순회 (YAML 중첩 selector/condition 의 파이썬 등가) ──────────────
def tree_leaf_class(clf, x) -> str:
    t = clf.tree_
    node = 0
    while t.children_left[node] != t.children_right[node]:
        f = t.feature[node]
        node = t.children_left[node] if x[f] <= t.threshold[node] else t.children_right[node]
    return str(clf.classes_[t.value[node][0].argmax()])


def base_tactic_bool(o, clf, dive_run):
    """champion_core.base_tactic 축자 미러 — clf.predict 만 명시 순회로 대체."""
    cls = tree_leaf_class(clf, C.featurize_s(o, dive_run))
    b = T[cls]
    hca, ata, clos = C._hca(o), o.ata_deg, o.closure_kts
    w_circ = C._sig((hca - 90.0) / 30.0)
    w_ext = C._sig((-clos - 25.0) / 30.0) * C._sig((ata - 30.0) / 20.0)
    if w_circ > 0.6 and w_circ >= w_ext:
        return (T.GUN_TRACK if ata < 30 else T.LEAD_TURN), (b, w_circ, w_ext)
    if w_ext > 0.6:
        return (T.GUN_TRACK if ata < 30 else T.LEAD_TURN), (b, w_circ, w_ext)
    return b, (b, w_circ, w_ext)


# ── off 선택 ────────────────────────────────────────────────────────────────────
# 정확직역 = 4개 off 점수의 수치 argmax (챔프 소프트-argmax 축자; harvest off_top==base 0불일치).
#   off = {GUN:4·σ·σ, LAG:2·σ·σ·σ·σ, HEADON:1.5·σ·σ, SMART_DIVE:1.0}, 가중치 4>2>1.5>1(우선순위).
# 하드-사다리(부호점 임계)는 σ-전이 밴드(폭~0.03°)에서 바닥(1.0) 교차와 어긋남 → 6틱 넉나이프-에지.
def off_argmax(o):
    off = C.s_off(o)                       # {Tactic: score}
    return max(off, key=off.get)           # 수치 argmax; 삽입순 GUN,LAG,HEADON,SMART_DIVE 로 타이브레이크


def off_ladder(o):
    """설명용 하드-사다리(부호점 임계). off_argmax 와 실현 manifold서 6틱만 상이(σ-전이 밴드)."""
    d, ata, aa, clos = o.distance_ft, o.ata_deg, o.aa_deg, o.closure_kts
    if d < C.WEZ and ata < 20.0:
        return T.GUN_TRACK
    if clos > C.OS_CLOS and d < C.OS_DIST and ata < 30.0 and aa < 60.0:
        return T.LAG_PURSUIT
    if clos > C.RECV_CLOS and aa > C.RECV_AA:
        return T.HEADON
    return T.SMART_DIVE



BASE_FN_GUN_ATA = 20.0      # f_gun 경계 [deg] — 루프32 실측 채택(트리 재현 96.8%)


def base_fn_tactic(o, kind: str):
    """루프32 명시 기저함수 — 트리 리프-클래스의 재유도(128-0-0 폐루프 확정).
    f_gun: ata<BASE_FN_GUN_ATA → GUN_TRACK / 그 외 f_lead: LEAD_TURN.
    (gun20v 변형의 f_vert 는 anchor_ace 역효과로 기각 — 루프32 실측.)"""
    if kind == "gun20v" and o.distance_ft > 6500.0 and 40.0 < o.ata_deg < 85.0:
        return T.VERTICAL_PURSUIT
    return T.GUN_TRACK if o.ata_deg < BASE_FN_GUN_ATA else T.LEAD_TURN


class TranscribedPolicy:
    """FullUnifiedPolicy 의 명시-불리언 직역. decide(o) -> (mode, tactic). 상태 자기보유."""

    def __init__(self, clf, decay=C.LAMBDA, thr=C.THETA, off_mode="exact",
                 deck_guard_ft=0.0, deck_sink_fps=0.0, **kw):
        self.clf, self.decay, self.thr = clf, decay, thr
        self.off_mode = off_mode          # "exact"=수치 argmax(틱-동일) | "ladder"=설명용 하드사다리
        # 루프32 기저-재유도 실험: LG_BASEFN 지정 시 트리 리프-클래스 대신 명시
        # 기저함수 사용(σ-override·off·게이트 등 나머지 기제는 불변).
        #   gun20  = GUN if ata<20 else LEAD (2함수)
        #   gun20v = + (rng>6500 & 40<ata<85) → VERTICAL_PURSUIT (3함수)
        # 미지정 = 정본 트리(비트-동일 보존).
        self.base_fn = kw.get("base_fn") or os.environ.get("LG_BASEFN") or None
        # L1 교정: 예측형 덱-가드. ego_alt<deck_guard_ft 이고 강하율(dalt)< -deck_sink_fps 면 CLIMB 강제.
        # 기본 0 = 비활성(틱-동일 보존). 하드덱 1300ft 는 375kcas 관성서 늦음 → 예측형 상위 가드.
        self.deck_guard_ft = float(deck_guard_ft)
        self.deck_sink_fps = float(deck_sink_fps)
        # L1 교정(이른 개입): empty-dive 에너지-보존 게이트. base==SMART_DIVE 인데 적과
        # 멀고(d>preserve_dist) 강하게 분리(closure<-preserve_clos) 면 = 낭비 강하 → CLIMB.
        # 정점(sink~0)서 발화해 관성 이전에 개입(반응형 덱-가드가 375kcas 관성에 늦는 문제 우회).
        # 기본 0 = 비활성(틱-동일 보존).
        self.preserve_dist = float(kw.get("preserve_dist", 0.0))
        self.preserve_clos = float(kw.get("preserve_clos", 0.0))
        # inner latch
        self.run = 0.0
        self.c = 0.0
        # outer(empty-dive) state — 이 스코프에선 불활성이나 충실 포함
        self.hist: list[tuple[float, float]] = []
        self.orun = 0.0
        self.armed = False
        self.kill = False

    def decide(self, o):
        # ── inner latch 점화식 (D2CostUnifiedPolicy.sel 전반부) ──
        climb = o.enm_vc_kts * _KT2FPS * math.sin(math.radians(o.enm_theta_deg))
        if climb < -C.DIVE_FPS:
            self.run += 0.1
        elif self.c <= self.thr:
            self.run = 0.0
        fire = (self.run >= C.DIVE_HOLD and o.aa_deg > C.AA_EXTEND)
        self.c = 1.0 if fire else self.decay * self.c

        # ── base 선택 ──
        if o.ego_alt_ft < C.HARD_DECK:
            base = T.CLIMB
        elif self.c >= self.thr:          # gw = sig((c-thr)/.05) >= 0.5  ⟺  c >= thr  → off 경로
            base = off_argmax(o) if self.off_mode == "exact" else off_ladder(o)
        else:                             # 트리 경로
            if self.base_fn:
                base = base_fn_tactic(o, self.base_fn)
                # σ-override(w_circ/w_ext)는 기저 기제의 일부 — 트리 대체와 무관하게 유지
                hca, ata, clos = C._hca(o), o.ata_deg, o.closure_kts
                w_circ = C._sig((hca - 90.0) / 30.0)
                w_ext = C._sig((-clos - 25.0) / 30.0) * C._sig((ata - 30.0) / 20.0)
                if (w_circ > 0.6 and w_circ >= w_ext) or w_ext > 0.6:
                    base = T.GUN_TRACK if ata < 30 else T.LEAD_TURN
            else:
                base, _ = base_tactic_bool(o, self.clf, min(self.run, C.DIVE_HOLD))

        # ── L1 예측형 덱-가드 (기본 비활성) ──
        a, d, a2 = o.ego_alt_ft, o.distance_ft, o.enm_alt_ft
        preva = self.hist[-1][0] if self.hist else a
        dalt = (a - preva) / 0.1
        deck_guard = (self.deck_guard_ft > 0.0 and a < self.deck_guard_ft
                      and dalt < -self.deck_sink_fps and base != T.CLIMB)
        preserve = (self.preserve_dist > 0.0 and base == T.SMART_DIVE
                    and d > self.preserve_dist and o.closure_kts < -self.preserve_clos)

        # ── outer(empty-dive) 상태 갱신 (FullUnifiedPolicy.decide) — 충실 재현 ──
        dop = (len(self.hist) >= 10 and d > self.hist[-10][1])
        perch = a - a2
        pred = (dalt < -30.0 and o.aa_deg < 35.0 and dop and o.ata_deg < 90.0 and perch > 150.0)
        self.hist.append((a, d))
        self.orun = self.orun + 0.1 if pred else 0.0
        if not self.armed and self.orun >= 2.0 and climb < -C.DIVE_FPS:
            self.armed = True

        # ── 최종 dispatch ──
        if preserve:
            return "preserve", T.CLIMB
        if deck_guard:
            return "deck_guard", T.CLIMB
        if not self.armed:
            if base == T.HEADON and a < 4500.0 and d < 7000.0:
                return "deck_suppress", T.PURE_PURSUIT
            return "core", base
        # armed 분기(이 스코프 불활성) — 충실 포함
        if a < 1300.0:
            return "empty_dive", T.CLIMB
        if not self.kill and (d < 3500.0 or (o.aa_deg > 150.0 and d < 4500.0)):
            self.kill = True
        if self.kill and d > 12000.0:
            self.kill = False
        if not self.kill:
            return "empty_dive", T.BREAK_TURN
        if d < 3000.0 and o.ata_deg < 20.0:
            return "empty_dive", T.GUN_TRACK
        if o.aa_deg < 90.0 and d > 2000.0:
            return "empty_dive", T.SMART_DIVE
        return "empty_dive", T.LEAD_TURN
