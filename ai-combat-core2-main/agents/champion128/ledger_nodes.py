"""128승 조종사 — 함수-구간 3층 BT (공정2: 문장이 YAML 가지로 보이는 판).

원본: research/proto_ledger_gate.LedgerPilot (파이썬 파일럿).
구성(champion128.yaml 의 selector 순서가 곧 실행 의미론):
  ①층 `ledger_book`   — 상황 함수 계산(20Hz 부기·10Hz 결정틱), 기저 판단 선계산
  ②층 `sentence` × N  — 함수값 구간(박스) 문장. YAML 에 구간 숫자가 그대로 보인다
  ③층 `base_pilot`    — 구간 밖 일반해(전사 기저 + 점수-장부 게이트)

동치 조건(원본 _surgical 스캔과 판단이 같으려면):
  · 결정 주기: BT 20Hz tick, 결정은 10Hz(2틱 1결정) — ledger_book 이 홀수 틱에서
    직전 명령을 재생하고 SUCCESS 로 트리를 끝낸다(문장·기저는 결정틱만 tick).
  · 기저 decide/gate 는 문장 활성 중에도 매 결정틱 실행(내부 래치 갱신) —
    ledger_book 이 선계산해 공유 상태에 둔다.
  · 문장 스캔 의미론 = selector 순서: 앞순위 문장이 먼저 물어봐지므로
    "앞순위 휴면 문장이 뒷순위 활성 문장을 선점"하는 원본 동작이 재현된다.
    각 문장은 1회성(만료 후 재발화 금지).
  · 관측: TacticContext 확장 필드로 원본 Obs 재구성(compute_obs 축자 동일).
"""
from __future__ import annotations

import json
import math
import os

from aircombat.tactics.custom import custom_node
from aircombat.tactics.node import Node, Status

from research import champion_core as C
from research.transcribe import TranscribedPolicy
from research.champion_pilot import tactic_to_command
from research.proto_ledger_gate import LedgerGate, refuse_cmd
from research.branch_search import ACTIONS, resolve_act

_DIR = os.path.dirname(os.path.abspath(__file__))


class _SnapTree:
    """base_tree.json 명시 순회 — sklearn tree_ 인터페이스 셔임(비트-동일 비교).

    transcribe.tree_leaf_class 가 쓰는 children_left/right·feature·threshold·value
    배열만 노출한다. joblib/sklearn 이 런타임에 필요 없어진다(공정3 스냅)."""

    class _T:
        pass

    def __init__(self, path: str):
        import numpy as np
        s = json.load(open(path))
        t = self._T()
        t.children_left = np.array(s["left"])
        t.children_right = np.array(s["right"])
        t.feature = np.array(s["feature"])
        t.threshold = np.array(s["threshold"], dtype=float)
        # tree_leaf_class 는 value[n][0].argmax() 만 쓴다 → 리프 클래스 one-hot 복원
        v = np.zeros((len(s["leaf_class"]), 1, len(s["classes"])))
        for n, c in enumerate(s["leaf_class"]):
            if c >= 0:
                v[n, 0, c] = 1.0
        t.value = v
        self.tree_ = t
        self.classes_ = s["classes"]


# YAML 에 표시되는 상수의 정본 값 — base_branch/ledger_book 이 일치를 단언한다
# (표시-실행 드리프트 검출: 어느 쪽이 바뀌면 로드 시점에 즉시 실패).
def _canon_consts():
    from research.transcribe import BASE_FN_GUN_ATA
    G = LedgerGate
    return dict(
        gun_ata=BASE_FN_GUN_ATA,
        hard_deck=C.HARD_DECK, theta=C.THETA, decay=C.LAMBDA,
        dive_fps=C.DIVE_FPS, dive_hold=C.DIVE_HOLD, aa_extend=C.AA_EXTEND,
        suppress_alt=4500.0, suppress_rng=7000.0,
        gate_hot=G.HOT, gate_rng=G.RNG, gate_edge=G.EDGE,
        lead_near=G.LEAD_NEAR, lead_hi=G.LEAD_HI, lead_floor=G.LEAD_FLOOR,
        hurt_max=G.HURT_MAX, cooldown_s=G.COOLDOWN_S, abort_off=G.ABORT_OFF,
        clear_hot=G.CLEAR_HOT, clear_rng=G.CLEAR_RNG,
        pursue_win_s=G.PURSUE_WIN_S, pursue_max=G.PURSUE_MAX,
        pursue_min_s=G.PURSUE_MIN_S, dom=G.DOM, threat_hold_s=G.THREAT_HOLD_S)


def _assert_consts(shown: dict) -> None:
    canon = _canon_consts()
    for k, v in shown.items():
        assert k in canon, f"미지 상수 표시: {k}"
        assert float(v) == float(canon[k]), \
            f"상수 드리프트: {k} 표시 {v} ≠ 정본 {canon[k]}"


class _Shared:
    """한 조종사(한 트리)의 공유 상태 — ctx 에 붙어 판마다 격리된다."""

    def __init__(self, refuse: str, clf=None, base_fn: str = ""):
        if base_fn:                       # 루프32 기저함수 — 트리 경로 미사용(joblib 불요)
            self.champion = TranscribedPolicy(None, off_mode="exact", base_fn=base_fn)
        else:
            self.champion = TranscribedPolicy(clf if clf is not None else C.load_clf(),
                                              off_mode="exact")
        self.ledger = LedgerGate()
        self.refuse = refuse
        self._prev_alt = None
        self._n = 0                 # 20Hz tick 카운터 (2틱=1결정, 원본 l1_ratio=2)
        self._cmd = None            # 직전 확정 명령 (홀수 틱 재생용)
        self.feats = None           # 이번 결정틱의 상황 함수값
        self.base_mode = None       # 기저 판단(문장 미발화 시 적용)
        self.base_cmd = None

    def log(self, mode, cmd, o, ata_n, eata_n):
        if os.environ.get("C128_LOG"):            # 동치 진단용 결정 로그
            with open(os.environ["C128_LOG"], "a") as f:
                f.write(f"{self.ledger.t:.2f}|{mode}|{cmd}"
                        f"|{o.distance_ft!r}|{o.ata_deg!r}|{o.aa_deg!r}"
                        f"|{o.closure_kts!r}|{o.ego_alt_ft!r}|{o.ego_vc_kts!r}"
                        f"|{o.enm_alt_ft!r}|{o.enm_vc_kts!r}|{o.enm_theta_deg!r}"
                        f"|{ata_n!r}|{eata_n!r}\n")

    def apply(self, ctx, mode, cmd):
        """명령 확정 — 결정틱에 문장/기저 중 한 노드만 부른다."""
        self._cmd = cmd
        ctx.trace.append(("ledger_champion", mode))
        self.log(mode, cmd, self._o, self._ata_n, self._eata_n)
        _set(ctx, cmd)


def _set(ctx, c):
    ctx.set_command(c.pursuit, c.name, g_burst=c.g_burst,
                    aim_above_ft=c.aim_above_ft, lead_time_s=c.lead_time_s,
                    lag_dist_ft=c.lag_dist_ft, mode=c.mode,
                    cz_range_ft=c.cz_range_ft)


def _obs(ctx):
    return C.Obs(ego_alt_ft=ctx.alt_ft, enm_alt_ft=ctx.enm_alt_ft,
                 ego_vc_kts=ctx.kcas, enm_vc_kts=ctx.enm_kcas,
                 distance_ft=ctx.dist_x_ft,
                 ata_deg=ctx.vel_ata_deg, aa_deg=ctx.vel_aa_deg,
                 closure_kts=ctx.closure_kts,
                 enm_theta_deg=ctx.enm_theta_deg,
                 ego_psi_deg=ctx.ego_psi_deg, enm_psi_deg=ctx.enm_psi_deg,
                 alt_gap_ft=ctx.alt_ft - ctx.enm_alt_ft)


# 같은 트리의 문장/기저 가지가 공유 상태를 찾는 방법: 트리는 YAML 순서대로
# 빌드되므로(ledger_book 이 먼저), 빌드 시점의 "마지막 book" 에 결속한다.
# ctx 는 틱마다 새로 만들어져(엔진 규약) 상태를 붙일 수 없다.
_CURRENT_BOOK: "LedgerBook | None" = None


@custom_node("ledger_book")
class LedgerBook(Node):
    """①층 — 관측→상황 함수 계산·장부(20Hz)·기저 선계산(10Hz).

    결정틱: FAILURE 반환(아래 문장/기저 가지로 통과).
    비결정틱: 직전 명령 재생 후 SUCCESS(트리 종료 — 원본 분주 재현)."""

    def __init__(self, *, refuse: str = "auto", snap: str = "", base_fn: str = "",
                 **consts):
        global _CURRENT_BOOK
        self.refuse = refuse
        self.base_fn = base_fn            # 루프32: 기저함수(트리 대체) — "" = 트리
        # snap: base_tree.json 경로(모듈 기준) — 지정 시 joblib 대신 스냅 순회
        self.clf = _SnapTree(os.path.join(_DIR, snap)) if snap else None
        _assert_consts(consts)               # YAML 표시 상수 = 정본 값 단언
        self.st: _Shared | None = None
        _CURRENT_BOOK = self

    def _feats(self, st, ctx, o, ata_n, eata_n):
        dalt = 0.0 if st._prev_alt is None else (o.ego_alt_ft - st._prev_alt) / 0.1
        st._prev_alt = o.ego_alt_ft
        f = dict(
            rng=o.distance_ft, ata=ata_n, eata=eata_n,
            kcas=o.ego_vc_kts, alt=o.ego_alt_ft, agap=o.alt_gap_ft,
            hp_lead=ctx.my_health - max(0.0, 100.0 - st.ledger.foe_dmg),
            clos=o.closure_kts, pursue=st.ledger.pursue_ratio(),
            hotrun=st.ledger.hot_run,
            eclimb=o.enm_vc_kts * 1.68781 * math.sin(math.radians(o.enm_theta_deg)),
            dalt=dalt,
            es_rel=(o.ego_alt_ft + (o.ego_vc_kts * 1.68781) ** 2 / 64.348)
                  - (o.enm_alt_ft + (o.enm_vc_kts * 1.68781) ** 2 / 64.348),
            t=st.ledger.t, fdmg=st.ledger.foe_dmg)
        f["race"] = eata_n - ata_n
        f["vdiff"] = o.ego_vc_kts - o.enm_vc_kts
        f["armed"] = 1.0 if st.ledger.armed else 0.0
        return f

    def tick(self, ctx) -> Status:
        st = self.st
        if st is None:
            st = self.st = _Shared(self.refuse, clf=self.clf, base_fn=self.base_fn)
        o = _obs(ctx)
        ata_n, eata_n = ctx.nose_ata_x_deg, ctx.nose_eata_x_deg
        st.ledger.book(o, 0.05, ata_n, eata_n)            # 20Hz 부기
        decision = st._n % 2 == 0
        st._n += 1
        st._o, st._ata_n, st._eata_n = o, ata_n, eata_n
        if not decision:                                  # 홀수 틱 — 직전 명령 재생
            _set(ctx, st._cmd)
            return Status.SUCCESS
        # 결정틱 — 기저 판단 선계산(문장 활성 중에도 래치 갱신 필수)
        mode, tac = st.champion.decide(o)
        # 판독 세분화(③층 가지 표시용) — decide 내부 우선순위의 사후 재구성:
        # core 는 hard_deck → 다이브-커밋(c≥θ) → 트리 순으로 정해졌다(transcribe 미러).
        if mode == "core":
            if o.ego_alt_ft < C.HARD_DECK:
                mode = "hard_deck"
            elif st.champion.c >= st.champion.thr:
                mode = "dive_response"
            elif st.champion.base_fn:
                mode = "f_gun" if tac == C.Tactic.GUN_TRACK else "f_lead"
            else:
                mode = "core_tree"
        diver = (getattr(st.champion, "run", 0.0) > 0.5
                 or getattr(st.champion, "armed", False))
        st.feats = self._feats(st, ctx, o, ata_n, eata_n)
        if st.ledger.gate(o, ctx.my_health, diver=diver, ata=ata_n, eata=eata_n):
            mode, cmd = "refuse", refuse_cmd(st.refuse, o, flip=st.ledger.flip)
        else:
            cmd = tactic_to_command(tac, ego_alt_ft=o.ego_alt_ft,
                                    enm_alt_ft=o.enm_alt_ft)
        st.base_mode, st.base_cmd = mode, cmd
        return Status.FAILURE                             # 문장 가지로 통과


@custom_node("sentence")
class Sentence(Node):
    """②층 — 함수-구간 문장. 구간(box) 동시 성립 시 1회 발화, dur 동안 유지."""

    def __init__(self, *, act: str, dur: float, box: dict, label: str = ""):
        assert act in ACTIONS, f"미지 행동: {act}"
        assert _CURRENT_BOOK is not None, "sentence 는 ledger_book 뒤에 와야 한다"
        self._book = _CURRENT_BOOK
        self.act, self.dur = act, float(dur)
        self.box = {k: (float(v[0]), float(v[1])) for k, v in box.items()}
        self.label = label
        self.until = None            # 발화 종료시각 (None=미발화)
        self.done = False            # 1회성 소진

    def tick(self, ctx) -> Status:
        st = self._book.st
        t = st.ledger.t
        if not st.ledger.armed and self.until is None:
            return Status.FAILURE        # armed-가드(루프34): 접근 단계 오발화 차단
        if self.until is not None:
            if t < self.until:                            # 발화 유지
                st.apply(ctx, "surgical", resolve_act(ACTIONS[self.act], st._o))
                return Status.SUCCESS
            self.until, self.done = None, True            # 만료·소진
            return Status.FAILURE
        if self.done:
            return Status.FAILURE
        f = st.feats
        if all(lo <= f[k] <= hi for k, (lo, hi) in self.box.items()):
            self.until = t + self.dur                     # 1회 발화
            st.apply(ctx, "surgical", resolve_act(ACTIONS[self.act], st._o))
            return Status.SUCCESS
        return Status.FAILURE


@custom_node("base_branch")
class BaseBranch(Node):
    """③층 — 기저 판독 가지(공정3): ledger_book 이 정한 경로(mode) 중 자기
    담당(when)이면 그 명령을 적용한다. YAML 에 조건 상수가 표시되며, 표시값은
    정본과 일치가 단언된다(드리프트 검출)."""

    def __init__(self, *, when, label: str = "", **consts):
        assert _CURRENT_BOOK is not None, "base_branch 는 ledger_book 뒤에 와야 한다"
        self._book = _CURRENT_BOOK
        self.when = tuple(when) if isinstance(when, (list, tuple)) else (when,)
        self.label = label
        _assert_consts(consts)

    def tick(self, ctx) -> Status:
        st = self._book.st
        if st.base_mode in self.when:
            st.apply(ctx, st.base_mode, st.base_cmd)
            return Status.SUCCESS
        return Status.FAILURE


@custom_node("base_pilot")
class BasePilot(Node):
    """③층 최후 폴백 — 어떤 판독 가지도 담당하지 않은 경로를 그대로 적용
    (preserve/deck_guard 등 비활성 경로 안전망)."""

    def __init__(self):
        assert _CURRENT_BOOK is not None, "base_pilot 은 ledger_book 뒤에 와야 한다"
        self._book = _CURRENT_BOOK

    def tick(self, ctx) -> Status:
        st = self._book.st
        st.apply(ctx, st.base_mode, st.base_cmd)
        return Status.SUCCESS


@custom_node("ledger_champion")
class LedgerChampion(Node):
    """[구판 호환] 단일-노드 실행기 — 동치 검증(A/B)용으로 유지."""

    def __init__(self, *, rules: str = "rules.json", refuse: str = "auto"):
        self.book = LedgerBook(refuse=refuse)
        raw = json.load(open(os.path.join(_DIR, rules)))
        self.sentences = [Sentence(act=r["act"], dur=r["dur"], box=r["box"])
                          for r in raw]
        self.base = BasePilot()

    def tick(self, ctx) -> Status:
        if self.book.tick(ctx) is Status.SUCCESS:
            return Status.SUCCESS
        for s in self.sentences:
            if s.tick(ctx) is Status.SUCCESS:
                return Status.SUCCESS
        return self.base.tick(ctx)
