"""다이어트 실측 검증 — 시뮬 통과분을 재롤아웃으로 재판한다(원리 4).

`slim_rules` 의 축 제거는 **덤프 위 발화-기록 시뮬**로 검증한다. 그런데 덤프는
%.2f 로 반올림돼 있어 경계 면도날(0.01 미만 차이)을 못 본다 — 실제로 그 한계가
실현된 사고가 있었다(문장 #10 의 축 제거가 배포에서 한 판을 승 +19.5 → 패 −53.6
으로 뒤집음. 시뮬은 "스케줄 불변"이라 통과시켰다).

그래서 이 도구가 **결정론 오라클**로 재판한다:

  1) 슬림본 전판 재채점 → 다이어트 **전** 결과와 대조
  2) 달라진 판이 있으면, 그 판을 탐침으로 **문장별 단독 슬림**을 시험해 범인 특정
     (전판이 아니라 깨진 판만 돌리므로 싸다)
  3) 범인 문장은 원본 축으로 되돌린 **하이브리드** 생성 → 재검증
  4) 통과분을 정본 슬림으로 저장(실패 시 전량 원복)

usage:
  python -m research.verify_slim --full <rules.json> --slim <slim.json> \
         --roster <목록.txt> --ref <다이어트전 재채점.log> --out <verified.json>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
LBL = os.path.join(PM, "data", "blueteam")
RE_RES = re.compile(r"\s*(\S+/(?:blue|red))\s+(승|무|패)\s+([+-][\d.]+)")


CONFIG: dict[str, str] = {}          # 기준 로그에서 읽은 정책 구성(#CONFIG)


def _read_config(path: str) -> dict:
    """기준 로그의 #CONFIG 서명 → 재채점 환경. 없으면 빈 dict(경고)."""
    try:
        for ln in open(path, encoding="utf-8", errors="ignore"):
            if ln.startswith("#CONFIG "):
                return dict(t.split("=", 1) for t in ln.split()[1:] if "=" in t)
            if ln.startswith("==="):
                break
    except OSError:
        pass
    return {}


def _rescore(rules_path: str, slots: str, log: str | None = None) -> dict:
    """기준과 **같은 구성**으로 재채점 — 구성이 다르면 비교 자체가 무의미하다
    (루프36 사고: LG_BASEFN 미전달로 기저가 트리로 돌아 34건 오탐)."""
    env = dict(os.environ, LG_ONLY=slots, LG_SURGICAL="1",
               LG_RULEBOX=os.path.relpath(rules_path, ROOT), PYTHONHASHSEED="0")
    if CONFIG.get("basefn") and CONFIG["basefn"] != "tree":
        env["LG_BASEFN"] = CONFIG["basefn"]
    env["LG_RULESEL"] = CONFIG.get("rulesel", "0")
    r = subprocess.run([sys.executable, os.path.join("research", "proto_ledger_gate.py")],
                       cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    out = r.stdout or ""
    if log:
        open(log, "w", encoding="utf-8").write(out)
    res = {}
    for ln in out.splitlines():
        m = RE_RES.match(ln)
        if m:
            res[m.group(1)] = (m.group(2), float(m.group(3)))
    return res


def _parse_log(path: str) -> dict:
    res = {}
    for ln in open(path, encoding="utf-8", errors="ignore"):
        m = RE_RES.match(ln)
        if m:
            res[m.group(1)] = (m.group(2), float(m.group(3)))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True)
    ap.add_argument("--slim", required=True)
    ap.add_argument("--roster", required=True)
    ap.add_argument("--ref", default="", help="다이어트 전 재채점 로그(없으면 직접 측정)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    full = json.load(open(a.full))
    slim = json.load(open(a.slim))
    slots = ",".join(x.strip() for x in open(os.path.join(ROOT, a.roster),
                                             encoding="utf-8")
                     .read().replace(chr(13), "").replace(chr(10), ",").split(",")
                     if x.strip())

    # 1) 기준(다이어트 전) 확보
    if a.ref and os.path.exists(a.ref):
        ref = _parse_log(a.ref)
        CONFIG.update(_read_config(a.ref))
        print(f"기준: {a.ref} ({len(ref)}판) · 구성 "
              + (" ".join(f"{k}={v}" for k, v in CONFIG.items()) if CONFIG
                 else "서명 없음 — 현재 환경 사용(주의)"))
    else:
        print("기준 측정(다이어트 전 전판 재채점)…", flush=True)
        ref = _rescore(a.full, slots)
    # 2) 슬림본 실측
    print("슬림본 전판 재채점…", flush=True)
    got = _rescore(a.slim, slots)
    diff = sorted(c for c in set(ref) | set(got) if ref.get(c) != got.get(c))
    print(f"다이어트 전후 불일치: {len(diff)}건 {diff[:5]}")
    if not diff:
        json.dump(slim, open(a.out, "w"), indent=1)
        print(f"검증 통과 — 슬림본 그대로 채택 → {a.out}")
        return 0

    # 3) 깨진 판을 탐침으로 범인 문장 특정 (문장별 단독 슬림)
    probe = ",".join(diff[:3])
    culprits = []
    for i in range(len(full)):
        mix = [dict(slim[j]) if j == i else dict(full[j]) for j in range(len(full))]
        p = os.path.join(LBL, "_vs_probe.json")
        json.dump(mix, open(p, "w"), indent=1)
        r = _rescore(p, probe)
        bad = [c for c in diff[:3] if r.get(c) != ref.get(c)]
        if bad:
            culprits.append(i)
            print(f"  문장#{i} 단독 슬림 → 이탈 {bad}")
    print(f"범인 문장: {culprits}")

    # 4) 범인만 원본 축으로 되돌린 하이브리드 → 전판 재검증
    hybrid = [dict(full[i]) if i in culprits else dict(slim[i])
              for i in range(len(full))]
    p = os.path.join(LBL, "_vs_hybrid.json")
    json.dump(hybrid, open(p, "w"), indent=1)
    print("하이브리드 전판 재채점…", flush=True)
    h = _rescore(p, slots)
    hdiff = sorted(c for c in set(ref) | set(h) if ref.get(c) != h.get(c))
    if hdiff:
        print(f"하이브리드도 이탈 {len(hdiff)}건 {hdiff[:5]} — 전량 원복(안전)")
        json.dump(full, open(a.out, "w"), indent=1)
    else:
        json.dump(hybrid, open(a.out, "w"), indent=1)
        keep = sum(len(x["box"]) for x in hybrid)
        print(f"하이브리드 검증 통과 — 범인 {len(culprits)}문장만 원본 축 유지 "
              f"(총 {keep}축) → {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
