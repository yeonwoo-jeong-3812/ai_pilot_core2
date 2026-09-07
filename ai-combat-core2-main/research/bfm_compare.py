"""두 조건의 기동 분류 대조 — H₀-a 판정용.

## 무엇을 가르는가

귀무가설 **H₀-a: 임멜만·스플릿S 같은 교범 기동은 유도층(bfm_guidance)이 만들고,
유도된 문장(결정층)과 무관하다.**

문장을 전부 끈 플레인 기저와 최종 정책을 같은 상대·같은 초기조건으로 돌려 기동
분포를 비교한다. 기저에서도 같은 빈도로 나오면 H₀-a 를 기각하지 못하고, 창발의
주어는 "유도된 명세"가 아니라 "명세 스택 전체"가 된다.

## 왜 개수를 그냥 비교하면 안 되는가

**오래 사는 정책은 그 이유만으로 기동을 더 쌓는다.** 최종 정책은 이기므로 교전이
길고, 플레인 기저는 져서 일찍 끝난다. 원시 개수 비교는 "정책이 기동을 더 한다"와
"정책이 더 오래 산다"를 구분하지 못한다. 그래서 **분당 발생률**로 정규화하고,
같은 슬롯끼리 짝지어(대응표본) 상대 난이도 차이를 상쇄한다.

효과크기와 신뢰구간을 보고한다 — 판수가 많으면 무의미하게 작은 차이도 유의해지므로
p값만으로는 아무것도 말할 수 없다.

usage:
  python -m research.bfm_compare --a replays/canon/h0a_plain --b replays/canon/h0a_final \
         --label-a "플레인 기저" --label-b "최종 정책" [--csv out.csv]
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from research.bfm_taxonomy import KINDS, classify_pair  # noqa: E402

def slot_key(path: str) -> str:
    """녹화 파일명 → 슬롯 키(상대/진영). 조건 간 짝짓기의 기준."""
    b = os.path.basename(path)
    for pre in ("champ_vs_", "vs_"):
        if b.startswith(pre):
            b = b[len(pre):]
            break
    return b.rsplit(".", 1)[0]


_SCAN_CACHE: dict = {}


def scan(folder: str, oid=None):
    """폴더 → {슬롯: (챔프 기동 Counter, 매치 길이, 상대 기동 Counter)}

    챔프는 콜사인으로 고른다 — red 슬롯에서는 챔프가 oid 200 이라, 고정 oid 로 읽으면
    절반의 판에서 상대 기체를 재게 된다(감사 적발 치명 결함).
    """
    if folder in _SCAN_CACHE:            # 같은 폴더를 여러 번 훑지 않는다(파싱이 비싸다)
        return _SCAN_CACHE[folder]
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, "**", "*.acmi"), recursive=True)):
        ev_c, ev_f, dur = classify_pair(p)
        out[slot_key(p)] = (collections.Counter(e["kind"] for e in ev_c), dur,
                            collections.Counter(e["kind"] for e in ev_f))
    _SCAN_CACHE[folder] = out
    return out


def _boot_ci(diffs, n=5000, seed=0):
    """부트스트랩 95% 신뢰구간 — 분포 가정 없이."""
    if len(diffs) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(diffs), size=(n, len(diffs)))
    means = np.asarray(diffs)[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def load_fired(fingerprint_path: str) -> set[str]:
    """발화 지문 → 문장이 한 번이라도 발화한 슬롯 집합.

    발화하지 않은 슬롯에서는 두 조건이 **같은 정책**이다(문장이 휴면이므로 기저만
    남는다). 그런 판을 섞으면 차이가 0인 판이 다수를 차지해 전체 평균이 희석되고,
    "문장은 기동을 바꾸지 않는다"는 잘못된 결론으로 이어진다. 반드시 갈라서 본다.
    """
    import json
    with open(fingerprint_path, encoding="utf-8") as f:
        sched = json.load(f).get("schedule", {})
    return {k.replace("/", "_") for k in sched}


def compare(a_dir, b_dir, oid=None, label_a="A", label_b="B", only=None):
    A, B = scan(a_dir, oid), scan(b_dir, oid)
    shared = sorted(set(A) & set(B))
    if only is not None:
        shared = [s for s in shared if s in only]
    rows, summary = [], {}

    dur_a = np.array([A[s][1] for s in shared])
    dur_b = np.array([B[s][1] for s in shared])

    for kind in KINDS + ["합계"]:
        get = (lambda c: sum(c.values())) if kind == "합계" else (lambda c, k=kind: c[k])
        ca = np.array([get(A[s][0]) for s in shared], float)
        cb = np.array([get(B[s][0]) for s in shared], float)
        # 분당 발생률 — 생존시간 차이를 상쇄
        ra = ca / np.maximum(dur_a, 1e-9) * 60.0
        rb = cb / np.maximum(dur_b, 1e-9) * 60.0
        d = rb - ra
        lo, hi = _boot_ci(d)
        rows.append((kind, ca.sum(), cb.sum(), ra.mean(), rb.mean(),
                     d.mean(), lo, hi, int((d > 0).sum()), int((d < 0).sum())))
        summary[kind] = dict(rate_a=ra.mean(), rate_b=rb.mean(), diff=d.mean(),
                             ci=(lo, hi))

    return shared, rows, summary, (dur_a.mean(), dur_b.mean())


def main() -> int:
    ap = argparse.ArgumentParser(description="두 조건의 기동 분류 대조")
    ap.add_argument("--a", required=True, help="조건 A 녹화 폴더")
    ap.add_argument("--b", required=True, help="조건 B 녹화 폴더")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--fired", default=None,
                    help="발화 지문 JSON — 발화판/휴면판을 갈라 각각 보고(권장)")
    ap.add_argument("--csv", default=None, help="판당 상세 CSV 경로")
    o = ap.parse_args()

    oid = None   # 챔프는 콜사인으로 자동 선택 (--side 는 더 이상 쓰지 않는다)
    groups = [("전체", None)]
    if o.fired:
        fired = load_fired(o.fired)
        all_slots = set(scan(o.a, oid)) & set(scan(o.b, oid))
        groups = [("발화판", fired & all_slots),
                  ("휴면판(두 조건 동일 정책)", all_slots - fired)]
    for gname, only in groups:
        _report(o, oid, gname, only)
    return 0


def _report(o, oid, gname, only) -> int:
    shared, rows, _, (da, db) = compare(o.a, o.b, oid, o.label_a, o.label_b, only)
    if not shared:
        print(f"\n[{gname}] 공통 슬롯 없음")
        return 1
    print(f"\n[{gname}]")

    print(f"짝지은 슬롯 {len(shared)}개   평균 교전시간  "
          f"{o.label_a} {da:.0f}s / {o.label_b} {db:.0f}s")
    print(f"\n{'기동':<8}{'개수 '+o.label_a:>12}{'개수 '+o.label_b:>12}"
          f"{'분당 '+o.label_a:>12}{'분당 '+o.label_b:>12}{'차이':>9}"
          f"{'95% CI':>20}{'B우세/A우세':>12}")
    for k, ca, cb, ra, rb, d, lo, hi, nb, na in rows:
        sig = "  ←유의" if (lo > 0 or hi < 0) else ""
        print(f"{k:<8}{ca:12.0f}{cb:12.0f}{ra:12.3f}{rb:12.3f}{d:+9.3f}"
              f"  [{lo:+.3f}, {hi:+.3f}]{nb:6d}/{na:<6d}{sig}")

    print("\n해석: 차이는 분당 발생률의 대응표본 평균차(B−A). "
          "신뢰구간이 0을 포함하면 조건 간 차이의 증거가 없다.")

    if o.csv:
        import csv as _csv
        A, B = scan(o.a, oid), scan(o.b, oid)
        out = o.csv if only is None else o.csv.replace(".csv", f"_{gname[:3]}.csv")
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = _csv.writer(f)
            w.writerow(["slot", "dur_a", "dur_b"]
                       + [f"a_{k}" for k in KINDS] + [f"b_{k}" for k in KINDS])
            for s in shared:
                w.writerow([s, f"{A[s][1]:.1f}", f"{B[s][1]:.1f}"]
                           + [A[s][0][k] for k in KINDS]
                           + [B[s][0][k] for k in KINDS])
        print(f"판당 상세 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
