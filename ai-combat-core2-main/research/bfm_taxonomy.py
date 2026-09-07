r"""고전 BFM 기동 분류기 — 녹화 자세 시계열에서 교범 기동을 식별한다.

## 왜 필요한가

유도된 문장 어디에도 "임멜만"이라는 이름의 노드는 없다. 그런데 녹화를 보면 임멜만처럼
보이는 궤적이 나온다. 이 도구는 그 관찰을 **일화에서 계측으로** 바꾼다.

## 이 계측기로 무엇을 주장할 수 있고 무엇은 못 하는가 — 반드시 읽을 것

레드팀 감사(2026-07-20)에서 드러난 사실: **대조군 없이 이 계측기의 개수를 인용하면
안 된다.** 기동 어휘가 전혀 없는 순수추격 스크립트(A1_PurePursuer)도 챔피언과 거의
같은 빈도로 "임멜만"으로 집계됐다(챔피언 227 : 상대 217). 즉 초기 판본이 센 것은
기동이 아니라 **라벨**이었다.

그래서 이 판본은 두 가지를 강제한다.

1. **대조군 동시 계측.** 같은 매치의 상대(스크립트 기체)를 자동으로 함께 잰다.
   주장은 절대 개수가 아니라 **차이**로만 성립한다.
2. **패딩 오염 제거.** 초기 판본은 사건 전후 3초를 붙인 창에서 Δ방위를 쟀는데,
   전투기는 6초면 90° 넘게 선회한다. 감사 결과 **"180° 반전" 판정의 47%가 패딩이
   만들어 낸 것**이었다. 이제 방위·고도 변화는 기동 구간 안에서만 잰다.

## 판정 원리

| 기동 | 교범 정의 | 이 구현의 판정 |
|---|---|---|
| 루프 | 수직면 360° 선회, 시작 방위 복귀 | 급수직 + 배면 경유 + \|Δψ\| < `TURN_TOL` |
| 임멜만 | 상승 반원 + 반롤 → 방위 반전·고도 획득 | 급수직(기수 상방) + 배면 경유 + \|Δψ\|≈180 + Δh > `ALT_TOL` |
| 스플릿S | 반롤 + 하강 반원 → 방위 반전·고도 상실 | 급수직(기수 하방) + 배면 경유 + \|Δψ\|≈180 + Δh < −`ALT_TOL` |
| 급상승 | 배면 없는 급상승(하이 요요 계열) | 급수직(기수 상방) + 배면 미경유 |
| 급강하 | 배면 없는 급강하(로우 요요·다이브) | 급수직(기수 하방) + 배면 미경유 |

**"급수직"이지 "수직 통과"가 아니다.** 오일러 피치는 정의상 ±90°를 넘지 못하므로
(실측 최대 89.4°) 자세각만으로는 "기수가 수직을 지났다"를 판정할 수 없다. `VERT_DEG`
는 "기수가 가파르게 들렸다/숙였다"를 뜻할 뿐이며, 이 한계는 이름에 반영해 두었다.

**배면 판정은 오일러 롤이 아니라 동체 z축의 연직 성분(cosφ·cosθ)으로 한다.** θ가
±90에 가까우면 오일러 φ가 악조건이라 프레임당 롤 변화가 최대 18.5°(=1,850°/s)까지
튀는데, 초기 판본은 그 잡음에 `|φ|>120` 임계를 걸고 있었다. cos 는 0°·180° 부근에서
평탄해 같은 잡음에 훨씬 둔감하고, 기수가 진짜 수직일 때는 자연히 0으로 수렴한다
(그 자세에서 "배면"은 물리적으로 정의되지 않는 게 맞다).

## 남은 한계 (해석 시 감안)

- `VERT_DEG` 를 ±10° 흔들면 총 개수가 2.7배까지 변한다. 절대 개수는 임계값의 함수이며,
  **조건 간 차이만 인용할 것.**
- 시저스·배럴롤처럼 롤이 지배적인 기동은 다루지 않는다(급수직이 없어 미검출).
- 라벨은 조종사의 의도가 아니라 **궤적의 모양**이다.

usage:
  python -m research.bfm_taxonomy <녹화.acmi> [...]        # 챔프/상대 동시
  python -m research.bfm_taxonomy --dir <폴더>             # 폴더 전수 집계
  python -m research.bfm_taxonomy --sweep <녹화.acmi>      # 임계값 민감도
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.debrief.replay_debrief import parse_acmi  # noqa: E402

# ── 판정 임계값 ───────────────────────────────────────────────────────────
VERT_DEG = 60.0      # |θ| 가 이 값을 넘으면 "급수직" (수직 '통과'가 아님 — 위 주석)
SETTLE_PITCH = 20.0  # |θ| 가 이 값 이하이고 정립이면 '안정' — 기동의 자연 경계
SETTLE_UP = 0.8      # cosφ·cosθ 가 이 값 이상이면 정립 수평
EXT_MAX_S = 6.0      # 안정 상태를 못 만나도 이 이상은 넓히지 않는다(폭주 방지)
MIN_S, MAX_S = 1.0, 30.0   # 기동 구간(패딩 제외) 지속시간 허용 범위
INVERT_UP = -0.5     # cosφ·cosθ 가 이 값 미만이면 배면 (−1=완전 배면, +1=정립)
INVERT_S = 0.3       # 배면이 이 시간 이상 지속돼야 "배면을 경유"로 인정
TURN_TOL = 40.0      # 방위 반전 허용 오차 (180°±TURN_TOL). 감사 지적으로 70→40
ALT_TOL = 500.0      # 고도 획득/상실로 인정할 최소 변화 [ft]
GAP_S = 2.0          # 급수직이 이 시간 안에 재개되면 같은 기동으로 잇는다

# 챔피언(피계측 정책)의 콜사인 접두사. 나머지 기체는 자동으로 대조군이 된다.
CHAMP_PREFIXES = ("Champion", "LedgerGate", "Transcribed", "FloorRec")
KINDS = ["임멜만", "스플릿S", "루프", "급상승", "급강하", "배면기타"]


def _wrap(a):
    """각도를 (-180, 180] 로."""
    return (np.asarray(a, float) + 180.0) % 360.0 - 180.0


def focus_ids(path):
    """(챔프 oid, 상대 oid). 슬롯이 red 면 챔프가 200 이므로 콜사인으로 고른다.

    감사에서 적발된 치명 결함: oid 를 100 으로 고정하면 `*_red.acmi` 에서는 상대
    기체를 재게 된다. 150판 폴더를 통째로 훑으면 챔프와 상대가 반반 섞인 수치가
    나오는데, 그럴듯해 보여서 더 위험하다.
    """
    obj = parse_acmi(path)
    for oid in (100, 200):
        name = str(obj[oid].get("name", ""))
        if name.startswith(CHAMP_PREFIXES):
            return oid, (200 if oid == 100 else 100)
    return 100, 200


def load_series(path: str, oid: int):
    """녹화 → (t, pitch, roll, yaw, alt). 중복 타임스탬프 제거."""
    s = parse_acmi(path)[oid]
    t = np.asarray(s["t"], float)
    _, keep = np.unique(t, return_index=True)
    keep.sort()
    pick = lambda k: np.asarray(s[k], float)[keep]  # noqa: E731
    return t[keep], pick("pitch"), pick("roll"), pick("yaw"), pick("alt")


def classify_series(series, *, vert=VERT_DEG, turn_tol=TURN_TOL, alt_tol=ALT_TOL,
                    invert_up=INVERT_UP, invert_s=INVERT_S, min_s=MIN_S, max_s=MAX_S):
    """자세 시계열 → 기동 목록. **파일 I/O 없는 순수 함수.**

    series: (t, pitch, roll, yaw, alt). yaw unwrap·중복 t 는 여기서 처리한다.
    반환: [{kind, t0, dur, dpsi, dalt, censored}, ...]

    Δψ·Δh 는 **기동 구간 안에서만** 잰다. 앞뒤로 여유를 붙여 재면 인접한 수평선회가
    딸려 들어와 반전을 조작해 낸다(감사: 반전 판정의 47%가 그렇게 만들어졌다).
    """
    t, th, ro, ps, alt = (np.asarray(x, float) for x in series)
    if len(t) < 10:
        return []
    _, keep = np.unique(t, return_index=True)
    keep.sort()
    t, th, ro, alt = t[keep], th[keep], ro[keep], alt[keep]
    ps = np.degrees(np.unwrap(np.radians(ps[keep])))

    idx = np.flatnonzero(np.abs(th) > vert)
    if not len(idx):
        return []

    # 급수직 구간을 GAP_S 이내면 하나로 잇는다(정상 부근에서 θ가 잠시 내려와도 같은 기동).
    groups, start, prev = [], idx[0], idx[0]
    for k in idx[1:]:
        if t[k] - t[prev] > GAP_S:
            groups.append((start, prev))
            start = k
        prev = k
    groups.append((start, prev))

    # 배면 지표: 동체 z축의 연직 성분. +1 정립, −1 배면, 0 기수 수직(배면 미정의).
    up = np.cos(np.radians(ro)) * np.cos(np.radians(th))

    # 기동의 경계는 **물리로** 잡는다: 기수가 가파른 구간에서 시작해, 앞뒤로 각각
    # "정립 수평으로 안정될 때까지" 넓힌다. 고정 패딩(±3초)을 쓰면 인접한 수평선회가
    # 딸려 들어와 반전을 조작해 내고(감사: 반전 판정의 47%), 반대로 가파른 구간만
    # 쓰면 임멜만의 결정적 증거인 '정상에서 배면 수평'이 창 밖으로 밀려난다.
    settled = (np.abs(th) <= SETTLE_PITCH) & (up >= SETTLE_UP)

    # 같은 이유로 **붙어 있는 구간을 병합**한다. 루프는 기수가 위로 한 번, 아래로 한 번
    # 가파른데 그 사이 배면 수평(θ≈0)을 지나므로, 시간 간격만 보면 두 사건으로 갈린다.
    # "그 사이에 정립 수평으로 안정된 적이 없으면 하나의 기동"이라는 같은 물리 기준을
    # 쓰면 루프가 온전히 한 사건으로 잡힌다. (감사: 루프가 사실상 검출되지 않던 원인)
    merged = [groups[0]]
    for g in groups[1:]:
        prev_i, prev_j = merged[-1]
        if not settled[prev_j:g[0] + 1].any():
            merged[-1] = (prev_i, g[1])
        else:
            merged.append(g)
    groups = merged

    events = []
    for i, j in groups:
        a = i
        while a > 0 and not settled[a] and t[i] - t[a] < EXT_MAX_S:
            a -= 1
        b = j
        while b < len(t) - 1 and not settled[b] and t[b] - t[j] < EXT_MAX_S:
            b += 1
        dur = float(t[b] - t[a])
        if not (min_s <= dur <= max_s):
            continue
        dpsi = float(_wrap(ps[b] - ps[a]))
        dalt = float(alt[b] - alt[a])
        # 배면을 '지속' 경유했는가 — 한 프레임 튐으로 계열이 갈리지 않게 시간으로 본다.
        inv_mask = up[a:b + 1] < invert_up
        dt = np.gradient(t[a:b + 1]) if b > a else np.zeros(1)
        inverted = float(np.sum(inv_mask * dt)) >= invert_s
        # 기수 방향은 '가파른 구간'의 부호로 본다 — 넓힌 창에는 수평 비행이 섞인다.
        nose_up = float(th[i:j + 1].mean()) > 0
        reversed_ = abs(abs(dpsi) - 180.0) < turn_tol
        # 매치 끝에 걸려 기동이 잘렸는가 — 격추 순간의 기동이 여기 걸리므로 표시한다.
        censored = bool(b >= len(t) - 2)

        if not inverted:
            kind = "급상승" if nose_up else "급강하"
        elif reversed_ and dalt > alt_tol and nose_up:
            kind = "임멜만"
        elif reversed_ and dalt < -alt_tol and not nose_up:
            kind = "스플릿S"
        elif abs(dpsi) < turn_tol:
            kind = "루프"
        else:
            kind = "배면기타"
        events.append(dict(kind=kind, t0=float(t[a]), dur=dur, dpsi=dpsi,
                           dalt=dalt, censored=censored))
    return events


def classify(path: str, oid: int | None = None, **kw):
    """녹화 파일 → (기동 목록, 매치 길이). oid 미지정 시 챔프를 자동 선택."""
    if oid is None:
        oid, _ = focus_ids(path)
    t, th, ro, ps, alt = load_series(path, oid)
    if len(t) < 10:
        return [], float(t[-1]) if len(t) else 0.0
    return classify_series((t, th, ro, ps, alt), **kw), float(t[-1])


def classify_pair(path: str, **kw):
    """한 매치에서 챔프와 상대를 **함께** 잰다 — 대조군을 공짜로 얻는 핵심 경로.

    같은 매치·같은 초기조건·같은 상대 기하이므로, 두 기체의 기동 빈도 차이는
    정책 차이로만 설명된다. 절대 개수 대신 이 차이를 인용해야 한다.
    """
    champ, foe = focus_ids(path)
    ev_c, dur = classify(path, champ, **kw)
    ev_f, _ = classify(path, foe, **kw)
    return ev_c, ev_f, dur


def _counts(events):
    return collections.Counter(e["kind"] for e in events)


def sweep_stability(path: str):
    """임계값 섭동에 라벨 구성이 얼마나 흔들리는가.

    거리 척도는 **총변동거리**다. 초기 판본은 `Counter & base` 의 합을 기준 총합으로
    나눴는데, 이는 원소별 최솟값이라 **개수가 늘어나는 방향의 불안정을 못 본다** —
    실제로 개수가 51% 증가한 섭동에 대해 "유지율 98.7%"를 보고했다.
    """
    base = _counts(classify(path)[0])
    rows = []
    for name, kw in [
        ("기준", {}),
        ("vert 50", {"vert": 50.0}), ("vert 70", {"vert": 70.0}),
        ("turn 30", {"turn_tol": 30.0}), ("turn 60", {"turn_tol": 60.0}),
        ("alt 300", {"alt_tol": 300.0}), ("alt 1000", {"alt_tol": 1000.0}),
        ("inv -0.3", {"invert_up": -0.3}), ("inv -0.7", {"invert_up": -0.7}),
        ("invS 0.1", {"invert_s": 0.1}), ("invS 0.6", {"invert_s": 0.6}),
    ]:
        c = _counts(classify(path, **kw)[0])
        keys = set(base) | set(c)
        tvd = sum(abs(c[k] - base[k]) for k in keys)
        denom = max(sum(base.values()), sum(c.values()), 1)
        rows.append((name, dict(c), 1.0 - tvd / denom))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="고전 BFM 기동 분류")
    ap.add_argument("acmi", nargs="*", help="녹화 경로")
    ap.add_argument("--dir", default=None, help="폴더 전수(재귀)")
    ap.add_argument("--sweep", action="store_true", help="임계값 민감도만 보고")
    ap.add_argument("--quiet", action="store_true", help="합계만")
    a = ap.parse_args()

    paths = list(a.acmi)
    if a.dir:
        paths += sorted(glob.glob(os.path.join(a.dir, "**", "*.acmi"), recursive=True))
    if not paths:
        ap.error("녹화를 지정하세요 (경로 또는 --dir)")

    if a.sweep:
        for p in paths:
            print(f"\n{os.path.basename(p)}")
            for name, c, keep in sweep_stability(p):
                print(f"  {name:10s} 유지율 {keep:6.1%}  {dict(c)}")
        return 0

    champ_tot, foe_tot = collections.Counter(), collections.Counter()
    dur_tot = 0.0
    for p in paths:
        ev_c, ev_f, dur = classify_pair(p)
        cc, cf = _counts(ev_c), _counts(ev_f)
        champ_tot.update(cc); foe_tot.update(cf); dur_tot += dur
        if not a.quiet:
            print(f"{os.path.basename(p)[:46]:48s} {dur:5.0f}s  "
                  f"챔프 {dict(cc) or '—'}  |  상대 {dict(cf) or '—'}")

    mins = dur_tot / 60.0
    print(f"\n녹화 {len(paths)}개 · 총 {mins:.1f}분")
    print(f"{'기동':<8}{'챔프':>8}{'상대(대조군)':>14}{'챔프 분당':>12}{'상대 분당':>12}")
    for k in KINDS:
        print(f"{k:<8}{champ_tot[k]:8d}{foe_tot[k]:14d}"
              f"{champ_tot[k]/max(mins,1e-9):12.3f}{foe_tot[k]/max(mins,1e-9):12.3f}")
    print(f"{'합계':<8}{sum(champ_tot.values()):8d}{sum(foe_tot.values()):14d}")
    print("\n주의: 절대 개수는 임계값의 함수다. 상대(대조군)와의 **차이**만 인용할 것.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
