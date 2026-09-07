"""공정3b 문장 다이어트 — 발화-무관 축 제거 + 경계 정리(함수-구간 가독화).

문장 박스는 귀납기가 전 축을 저장하지만, 실제 발화를 구속하는 축은 소수다.
축 하나를 빼도 **배포-구성 128판 전 궤적에서 전체 발화 스케줄(2차 발화·만료
포함)이 불변**이면 그 축은 문장의 의미에 기여하지 않는다 → 제거.

검증기: 원본 _surgical 의미론(순서 스캔·활성 우선·1회성)을 덤프 위에서 전-발화
시뮬레이션. ⚠ 덤프는 %.2f 반올림이라 런타임 면도날(<0.01)은 못 본다 — 최종
판정은 전 128판 실측(run_match --roster)이 담당(루프15 교훈).

경계 정리: 남은 축의 [lo, hi] 를 바깥쪽 2자리 반올림(floor/ceil) — 기존 발화점
포함성은 보존되고(넓어지기만 함), 새 발화 유입은 시뮬+실측이 검출.

usage: python -m research.slim_rules <in.json> <dump.csv> <out.json>
"""
from __future__ import annotations

import csv
import json
import math
import sys


def load_dump(path: str) -> dict[str, list[tuple[float, dict]]]:
    by = {}
    for r in csv.DictReader(open(path)):
        feats = {k: float(v) for k, v in r.items() if k != "tag"}
        by.setdefault(r["tag"], []).append((float(r["t"]), feats))
    return by


def schedule(rules: list, dump: dict) -> list:
    """전-발화 이벤트 목록 [(tag, t, rule_idx, 'fire'|'hold' 수 제외)] — 원본
    _surgical 의미론(순서 스캔·활성 우선 반환·만료 시 소진·1회성) 재현."""
    events = []
    for tag in sorted(dump):
        until = [None] * len(rules)
        done = [False] * len(rules)
        for t, f in dump[tag]:
            if f.get("armed", 1.0) < 0.5:
                continue                        # 루프34 armed-가드 동조
            for i, r in enumerate(rules):
                u = until[i]
                if u is not None:
                    if t < u:
                        break                       # 활성 유지(스캔 종료 = return)
                    until[i], done[i] = None, True
                    continue
                if done[i]:
                    continue
                if all(lo <= f[k] <= hi for k, (lo, hi) in r["_box"].items()):
                    until[i] = t + r["dur"]
                    events.append((tag, round(t, 2), i))
                    break
    return events


def main(src: str, dump_csv: str, out: str) -> None:
    rules = json.load(open(src))
    for r in rules:
        r["_box"] = {k: tuple(v) for k, v in r["box"].items()}
    dump = load_dump(dump_csv)
    ref = schedule(rules, dump)
    print(f"기준 발화 {len(ref)}건 / 문장 {len(rules)}")

    # ① 축 다이어트 — 문장별·축별 제거 시도(스케줄 불변이면 확정)
    removed = 0
    for i, r in enumerate(rules):
        for k in sorted(r["_box"], key=lambda k: -(r["_box"][k][1] - r["_box"][k][0])):
            save = r["_box"].pop(k)
            if schedule(rules, dump) == ref:
                removed += 1
            else:
                r["_box"][k] = save
        print(f"  문장#{i} {r['act']:<8} 축 {len(r['box'])} → {len(r['_box'])}")
    # ② 경계 정리 — 바깥쪽 4자리 반올림(부동소수 먼지 제거; 스케줄 검증, 실패 시 원복)
    exact = [dict(r["_box"]) for r in rules]
    for r in rules:
        r["_box"] = {k: (math.floor(lo * 10000) / 10000, math.ceil(hi * 10000) / 10000)
                     for k, (lo, hi) in r["_box"].items()}
    if schedule(rules, dump) != ref:
        print("  [경계 정리] 시뮬 이탈 — 정확값 유지로 원복")
        for r, b in zip(rules, exact):
            r["_box"] = b
    slim = [dict(box={k: [lo, hi] for k, (lo, hi) in r["_box"].items()},
                 act=r["act"], dur=r["dur"], covers=r.get("covers", []),
                 cofire=r.get("cofire", []),
                 t_width=r.get("t_width", {})) for r in rules]
    json.dump(slim, open(out, "w"), indent=1)
    total = sum(len(r["box"]) for r in slim)
    print(f"축 제거 {removed}개 → 총 {total}축 저장: {out}")
    print("※ 최종 판정은 전 128판 실측 필요(덤프 반올림 한계)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
