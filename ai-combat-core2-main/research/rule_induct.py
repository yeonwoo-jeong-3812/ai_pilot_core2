"""루프24 — CEGIS 3단계: 승리 증인의 케이스-횡단 규칙 귀납.

입력: dense_*.log(증인: case×t0×행동×Δ), 구성-C obs 덤프(런타임 좌표 130k 틱).
출력: 규칙 JSON [(박스, 행동, dur)] — 각 규칙은 여러 반례를 공동 피복하고,
      승리-궤적 구름과 분리(무간섭)되며, 각 피복 케이스의 **진입틱 재롤아웃**을
      통과한 것만 채택.

알고리즘(탐욕 가족-피복):
  행동별로 미피복 반례들의 증인을 모아 → 정규화 공간의 medoid 근접 증인 1개/케이스
  선택 → 경계박스+여유확장(구름 배제 유지) → 진입틱 검증(전 피복 케이스 승리) →
  실패 케이스는 이 규칙에서 제외(다음 규칙/반복으로). 전 반례 피복까지.

usage: LG_RULESEL=1 python -m research.rule_induct
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("LG_RULESEL", "1")   # 기반 구성 C 고정

from research import champion_core as C
from research.branch_search import ACTIONS, run_forced

SCRATCH = os.environ.get(
    "RI_SCRATCH",
    os.path.join(os.path.dirname(__file__), "campaigns", "witness"))
LBL = os.path.join(os.path.dirname(__file__), "data", "blueteam")
DUMPS = [os.path.join(LBL, x) for x in os.environ.get(
    "RI_DUMPS", "obs_dump_C_train.csv;obs_dump_C_unseen.csv").split(";")]
OUT_JSON = os.path.join(LBL, os.environ.get("RI_OUT", "induced_rules.json"))
PREFIX = os.environ.get("RI_PREFIX", "dense_")
DUR = 6.0
FEATS = ("rng", "ata", "eata", "kcas", "alt", "agap", "hp_lead",
         "clos", "pursue", "hotrun", "eclimb", "dalt")
PAD0 = dict(rng=200, ata=5, eata=5, kcas=10, alt=500, agap=500, hp_lead=1,
            clos=20, pursue=0.05, hotrun=0.5, eclimb=30, dalt=30, es_rel=500,
            t=5, fdmg=2,
            race=7, vdiff=15,
            armed=1,
            # 루프38 롤 축 — LOS 기준 당김면 방향[deg], ±180 범위.
            # 패딩은 조준각(ata=5)·경쟁축(race=7)보다 넉넉히: 롤은 자세가 크게 흔들려도
            # 전술적 의미(적이 내 당김면 어느 쪽에 있나)는 잘 안 바뀐다.
            roff=10, eroff=10)   # 루프31 파생 관계축 + 루프34 가드 + 루프38 롤
# RI_FEATS: 쉼표 목록으로 귀납 특징 부분집합 지정(예: 관계형-전용 — 절대축 alt/kcas
# 제거). 박스 dict 는 지정 축만 담으므로 런타임 _surgical 은 그대로 동작한다.
if os.environ.get("RI_FEATS"):
    FEATS = tuple(k for k in os.environ["RI_FEATS"].split(",") if k)
    assert set(FEATS) <= set(PAD0), f"미지 특징: {set(FEATS)-set(PAD0)}"


def load_witnesses():
    wit = {}   # case -> list[(t0, act, dhp)]
    for p in sorted(glob.glob(os.path.join(SCRATCH, PREFIX + "*.log"))):
        stem_side = os.path.basename(p)[len(PREFIX):-len(".log")]
        # 진영 구분자는 **마지막 밑줄이 아니다.** 파일명은 `<stem>_<side>[@국면][@s시드]`
        # 인데, 국면 이름에 밑줄이 있으면(perch_defense) rsplit("_",1) 이 그 안을 잘라
        # `…blue@perch / defense@s11` 같은 깨진 키를 만든다(실측 KeyError).
        # 진영 토큰(blue|red)을 직접 집는다.
        if "~" in stem_side:
            case = stem_side.replace("~", "/")          # 신규 인코딩 — 무손실
        else:
            m0 = re.match(r"^(.*)_(blue|red)(@.*)?$", stem_side)
            if not m0:
                continue                                # 구 인코딩 — 경로-슬롯은 복원 불가
            case = f"{m0.group(1)}/{m0.group(2)}{m0.group(3) or ''}"
        for line in open(p, encoding="utf-8"):
            # RI_DRAW_OK=1(루프35 ③층): ★무(패 아님·HP 비열세) 증인도 수용 —
            # "일반해 하한=무승부" 사전등록에 따라 패→무 전환을 진전으로 인정.
            pat = (r"\s*t0=\s*([\d.]+)\s+(\w+)\s+d=\s*[\d.]+ → ★[승무] Δ\s*([+-][\d.]+)"
                   if os.environ.get("RI_DRAW_OK") == "1" else
                   r"\s*t0=\s*([\d.]+)\s+(\w+)\s+d=\s*[\d.]+ → ★승 Δ\s*([+-][\d.]+)")
            m = re.match(pat, line)
            if m:
                wit.setdefault(case, []).append(
                    (float(m.group(1)), m.group(2), float(m.group(3))))
    return wit


def load_dumps():
    data = {}   # tag -> list[(t, np.array feats)]
    armed_only = os.environ.get("RI_ARMED_ONLY", "0") == "1"
    for path in DUMPS:
        for r in csv.DictReader(open(path)):
            # 루프34 armed-가드 정합: 가드 하에서 armed 이전 상태는 발화 불가 —
            # 유효 상태공간에서 제외(표적·구름 모두). 구 덤프(열 없음)는 통과.
            if armed_only and float(r.get("armed", 1.0)) < 0.5:
                continue
            data.setdefault(r["tag"], []).append(
                (float(r["t"]), np.array([float(r[k]) for k in FEATS])))
    return data


def feats_at(data, case, t0):
    rows = data[case]
    t, v = min(rows, key=lambda x: abs(x[0] - t0))
    return (t, v) if abs(t - t0) <= 0.6 else (None, None)


def build_cloud(data, all_targets, min_pick_t):
    """무간섭 구름: 비표적(승리 판) 전체 + 피복 표적의 조기(t < pick-3) 틱.

    표적 전체를 구름에서 제외한다 — 표적끼리는 서로 발화해도 됨(각자 규칙으로
    이기면 그만; 쌍둥이 궤적이 서로를 분리불가로 만드는 문제의 해결). 교차 간섭의
    최종 판정은 전수 재채점이 담당."""
    rows = []
    for tag, lst in data.items():
        if tag in all_targets:
            cut = min_pick_t.get(tag)
            if cut is not None:
                rows += [v for t, v in lst if t < cut - 3.0]
        else:
            rows += [v for _, v in lst]
    return np.vstack(rows)


def box_expand(seed_lo, seed_hi, X):
    lo, hi = seed_lo.copy(), seed_hi.copy()

    def inside(lo, hi):
        m = np.ones(len(X), bool)
        for i in range(len(FEATS)):
            m &= (X[:, i] >= lo[i]) & (X[:, i] <= hi[i])
        return int(m.sum())

    if inside(lo, hi) > 0:
        return None
    scale = np.array([PAD0[k] for k in FEATS], float)
    for _ in range(30):
        for i in range(len(FEATS)):
            for sgn, arr in ((-1, lo), (1, hi)):
                trial_lo, trial_hi = lo.copy(), hi.copy()
                (trial_lo if sgn < 0 else trial_hi)[i] += sgn * 0.1 * scale[i]
                if inside(trial_lo, trial_hi) == 0:
                    lo, hi = trial_lo, trial_hi
    return lo, hi


def entry_tick(data, case, lo, hi):
    for t, v in data[case]:
        if np.all(v >= lo) and np.all(v <= hi):
            return t
    return None


def main():
    clf = C.load_clf()
    wit = load_witnesses()
    data = load_dumps()
    targets = set(wit)
    print(f"표적 {len(targets)}개, 증인 {sum(len(v) for v in wit.values())}개")

    uncovered = set(targets)
    rules = []
    ver_cache = {}   # (case, act, te) → win  — 동일 검증 재시뮬 방지

    def verify(c, act, te):
        key = (c, act, round(te, 2))
        if key not in ver_cache:
            stem, side = c.split("/")
            # 루프30 시드-인지: 케이스 "stem/side@sN" → IC 시드 N 으로 재롤아웃.
            if "@s" in side:
                side, _s = side.split("@s")
                os.environ["LG_IC_SEED"] = _s
            else:
                os.environ.pop("LG_IC_SEED", None)
            win, dhp, cond, tend, _ = run_forced(stem, side, clf,
                                                 (te, DUR, ACTIONS[act]))
            ok = win or (os.environ.get("RI_DRAW_OK") == "1" and dhp >= 0.0)
            print(f"  {act} 진입틱 {c} t={te:.2f} → {'✓' if ok else '✗'} "
                  f"Δ{dhp:+.1f}", flush=True)
            ver_cache[key] = ok
        return ver_cache[key]

    def attempt(act, cover, pick, med, sd):
        """피복 축소 루프. 성공 시 (rule, covered) / 실패 시 (None, []).

        단일 케이스 분리불가 시 fallback: 같은 유형의 **승리 쌍둥이**(동일 궤적로
        분리를 막는 비표적)를 구름에서 빼고 공동발화 허용 — 대신 그 쌍둥이의
        진입틱에서도 같은 행동이 **승리를 보존**하는지 롤아웃 검증(루프21 원리)."""
        cover = list(cover)
        cofire_pool: set = set()
        while cover:
            seed = np.vstack([pick[c][1] for c in cover])
            lo, hi = seed.min(0), seed.max(0)
            # 엄격 분리(rel3 교차발화 교훈): 구름 제외는 **현재 피복 케이스**(+cofire
            # 쌍둥이)만 — 비피복 표적의 궤적도 구름에 넣어 남의 진입틱을 무산시키는
            # 표적-간 선발화를 원천 금지한다. 같은 가족 쌍둥이는 같은 규칙에 공동
            # 피복되므로(cover0 에 함께 들어옴) 이 강화와 양립.
            cloud = build_cloud(data, set(cover) | cofire_pool,
                                {c: pick[c][0] for c in cover})
            box = box_expand(lo, hi, cloud)
            if box is None:
                if len(cover) == 1:
                    c0 = cover[0]
                    arch = c0.split("/")[0].rsplit("_", 1)[0]
                    sibs = {t for t in data if t not in targets
                            and t.split("/")[0].rsplit("_", 1)[0] == arch} \
                        - cofire_pool
                    if sibs:
                        print(f"  분리불가 → 승리 쌍둥이 {sorted(sibs)} 공동발화 허용 재시도")
                        cofire_pool |= sibs
                        continue
                    print(f"  [분리불가] {act} ⊃ {cover}")
                    return None, []
                dists = {c: np.linalg.norm((pick[c][1] - med) / sd) for c in cover}
                drop = max(sorted(dists), key=dists.get)   # 동률 시 이름순(결정론)
                print(f"  분리실패 → {drop} 제외 재시도")
                cover.remove(drop)
                continue
            lo, hi = box
            fails = [c for c in cover
                     if not verify(c, act, entry_tick(data, c, lo, hi))]
            if fails:
                for c in fails:
                    cover.remove(c)
                continue
            # 공동발화 쌍둥이의 승리 보존 검증(발화되는 경우만)
            cofired = []
            ok = True
            for s in sorted(cofire_pool):
                te = entry_tick(data, s, lo, hi)
                if te is None:
                    continue
                if not verify(s, act, te):
                    print(f"  [공동발화 위반] {s} — 이 시도 폐기")
                    ok = False
                    break
                cofired.append(s)
            if not ok:
                return None, []
            rule = dict(box={k: [float(lo[i]), float(hi[i])]
                             for i, k in enumerate(FEATS)},
                        act=act, dur=DUR, covers=cover, cofire=cofired,
                        t_width={c: twin[c] for c in cover if c in twin})
            return rule, cover
        return None, []

    # 행동 우선순위: 미피복 케이스를 많이 덮는 행동부터. 실패한 행동의 증인은
    # 소진 처리(무한 재시도 방지 — v1 의 while-else 버그로 무한루프 실측).
    while uncovered:
        acts_left = {a for c in uncovered for _, a, _ in wit[c]}
        if not acts_left:
            break
        # 결정론(루프33): set 순회는 해시-씨드에 따라 동률 타이브레이크가 달라져
        # 탐욕 경로 전체가 갈린다(LOFO 이월 수치가 씨드 복권이던 실측 결함).
        # sorted 로 순서를 고정 — 같은 입력 = 같은 문장.
        best = max(sorted(acts_left), key=lambda a: sum(
            1 for c in uncovered if any(a == x for _, x, _ in wit[c])))
        act = best
        cover0 = sorted(c for c in uncovered if any(act == a for _, a, _ in wit[c]))
        pts = {}
        for c in cover0:
            vs = [(t0, feats_at(data, c, t0)[1]) for t0, a, _ in wit[c] if a == act]
            vs = [(t0, v) for t0, v in vs if v is not None]
            if vs:
                pts[c] = vs
        cover0 = [c for c in cover0 if c in pts]
        rule = None
        if cover0:
            allv = np.vstack([v for c in cover0 for _, v in pts[c]])
            med, sd = allv.mean(0), allv.std(0) + 1e-9

            def _widest_run(ts):
                """승리 t0 목록의 최장 연속구간 [a,b] (격자 간격 자동 추정)."""
                ts = sorted(set(ts))
                if len(ts) < 2:
                    return (ts[0], ts[0]) if ts else (0.0, 0.0)
                step = min(b - a for a, b in zip(ts, ts[1:]))
                best = cur0 = ts[0]; prev = ts[0]; best_w = 0.0
                for t_ in ts[1:] + [None]:
                    if t_ is None or t_ - prev > step + 0.1:
                        if prev - cur0 > best_w:
                            best_w, best = prev - cur0, cur0
                        if t_ is not None:
                            cur0 = t_
                    if t_ is not None:
                        prev = t_
                return (best, best + best_w)

            twin = {}
            if os.environ.get("RI_ROBUST") == "1":
                # 루프35: 시간창-강건 증인 선택 — 최장 승리 연속구간(강건 정박점)
                # 안의 증인을 우선, 동률은 medoid. 폭은 문장 메타데이터로 기록.
                pick = {}
                for c in cover0:
                    a, b = _widest_run([t0 for t0, _ in pts[c]])
                    twin[c] = round(b - a, 1)
                    inside = [tv for tv in pts[c] if a <= tv[0] <= b] or pts[c]
                    pick[c] = min(inside,
                                  key=lambda tv: np.linalg.norm((tv[1] - med) / sd))
            else:
                pick = {c: min(pts[c],
                               key=lambda tv: np.linalg.norm((tv[1] - med) / sd))
                        for c in cover0}
            rule, covered = attempt(act, cover0, pick, med, sd)
        if rule is not None:
            rules.append(rule)
            print(f"[규칙 {len(rules)}] {act} d{DUR:g} ⊃ {covered}")
            uncovered -= set(covered)
        else:
            # 이 행동으론 아무것도 못 덮음 → 미피복 케이스의 그 행동 증인 소진
            for c in list(uncovered):
                wit[c] = [w for w in wit[c] if w[1] != act]
                if not wit[c]:
                    print(f"[미해결 반례] {c} — 증인 소진")
                    uncovered.discard(c)

    json.dump(rules, open(OUT_JSON, "w"), indent=1)
    print(f"\n규칙 {len(rules)}개 저장: {OUT_JSON}")
    print(f"미피복: {sorted(uncovered) if uncovered else '없음(전 반례 피복)'}")


if __name__ == "__main__":
    raise SystemExit(main())
