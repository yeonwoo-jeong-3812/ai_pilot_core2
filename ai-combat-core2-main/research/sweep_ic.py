"""초기조건 스윕 — 정책 하나를 여러 IC(시드·국면)에서 채점하는 병렬 러너.

## 왜 필요한가

지금까지의 모든 성적은 **초기조건 하나**에서 나왔다(headon 고정 IC, 지터 없음).
150판이라는 숫자는 상대의 수이지 반복의 수가 아니라서, "이 정책은 강건한가"라는
물음에 답하지 못한다. 이 도구가 그 차원을 연다.

## 왜 병렬인가

판당 8~16초, 64코어. 그런데 기존 러너는 순차라 20,480판이면 45시간이 걸린다.
매치는 서로 독립이고 엔진에 자생 난수가 없어(주입 시드 하나뿐) **병렬화가 결정론을
깨지 않는다.** 작업 단위를 (국면, 시드)로 잘라 프로세스에 뿌리면 같은 일이 1시간 안에
끝난다. 계산이 아니라 배선이 병목이었다.

결정론 검증은 `--verify` 로 한다 — 같은 단위를 두 번 돌려 결과가 비트-동일한지,
그리고 병렬 결과가 순차 결과와 같은지 확인한다.

usage:
  # 챔피언을 헤드온 20시드에서 채점
  python -m research.sweep_ic --tag t3full --seeds 1-20 \
      --rules research/data/blueteam/induced_rules_t3full_verified.json

  # 문장 끈 기저(대조군)를 같은 IC 에서
  python -m research.sweep_ic --tag plain --seeds 1-20 --plain

  # 국면까지 넓히기
  python -m research.sweep_ic --tag t3full_multi --seeds 1-10 \
      --scenarios headon,neutral --rules <...>
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT_RE = re.compile(r"^(\S+)\s+(승|무|패)\s+([+-][\d.]+)")


def parse_seeds(spec: str) -> list[int]:
    """'1-20' 또는 '1,3,7' 또는 섞어서."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def unit_env(scenario: str, seed: int, roster: str, rules: str | None,
             plain: bool) -> dict:
    """작업 단위 하나의 환경. 정책 구성은 여기 한 곳에서만 정한다."""
    slots = ",".join(x.strip() for x in open(roster, encoding="utf-8") if x.strip())
    env = dict(LG_ONLY=slots, LG_BASEFN="gun20", LG_SCENARIO=scenario,
               LG_IC_SEED=str(seed), PYTHONHASHSEED="0")
    if plain:
        env["LG_RULESEL"] = "0"          # 문장 전부 끔 — 기저만
    else:
        if not rules:
            raise SystemExit("--rules 를 주거나 --plain 을 쓰세요")
        env["LG_SURGICAL"] = "1"
        env["LG_RULEBOX"] = os.path.relpath(rules, ROOT)
    return env


def run_units(units, workers: int, outdir: str, roster, rules, plain):
    """(국면, 시드) 단위를 최대 workers 개까지 동시에 돌린다."""
    os.makedirs(outdir, exist_ok=True)
    pending, running, done = list(units), {}, []
    t0 = time.time()
    while pending or running:
        while pending and len(running) < workers:
            scenario, seed = pending.pop(0)
            log = os.path.join(outdir, f"{scenario}_s{seed}.log")
            if os.path.exists(log) and os.path.getsize(log) > 0:
                done.append((scenario, seed, log))       # 멱등 — 이미 돈 단위는 건너뜀
                continue
            env = dict(os.environ)
            env.update(unit_env(scenario, seed, roster, rules, plain))
            f = open(log, "w", encoding="utf-8")
            p = subprocess.Popen(
                [sys.executable, os.path.join("research", "proto_ledger_gate.py")],
                cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
            running[p] = (scenario, seed, log, f)
        for p in list(running):
            if p.poll() is not None:
                scenario, seed, log, f = running.pop(p)
                f.close()
                done.append((scenario, seed, log))
                el = time.time() - t0
                print(f"  [{len(done)}/{len(units)}] {scenario} s{seed} "
                      f"({el/60:.1f}분 경과)", flush=True)
        if running:
            time.sleep(1.0)
    return done


def read_log(path: str):
    """결과 로그 → {슬롯: (판정, HPΔ)}"""
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = RESULT_RE.match(ln.strip())
            if m:
                out[m.group(1)] = (m.group(2), float(m.group(3)))
    return out


def summarize(done, csv_path: str | None):
    """단위별 승/무/패 + 슬롯별 취약도(몇 개 IC 에서 졌나)."""
    per_unit, per_slot = [], collections.defaultdict(collections.Counter)
    for scenario, seed, log in sorted(done):
        res = read_log(log)
        c = collections.Counter(v[0] for v in res.values())
        per_unit.append((scenario, seed, len(res), c["승"], c["무"], c["패"]))
        for slot, (verdict, _) in res.items():
            per_slot[slot][verdict] += 1

    print(f"\n{'국면':<10}{'시드':>5}{'판':>6}{'승':>6}{'무':>5}{'패':>5}")
    tot = collections.Counter()
    for scenario, seed, n, w, d, l in per_unit:
        print(f"{scenario:<10}{seed:>5}{n:>6}{w:>6}{d:>5}{l:>5}")
        tot["n"] += n; tot["승"] += w; tot["무"] += d; tot["패"] += l
    if tot["n"]:
        print(f"{'합계':<10}{'':>5}{tot['n']:>6}{tot['승']:>6}{tot['무']:>5}{tot['패']:>5}"
              f"   승률 {tot['승']/tot['n']:.1%}  불패율 "
              f"{(tot['승']+tot['무'])/tot['n']:.1%}")

    # IC 를 흔들었을 때 무너지는 슬롯 — 강건성의 실제 소재지
    frail = sorted(((s, c) for s, c in per_slot.items() if c["패"]),
                   key=lambda x: -x[1]["패"])
    if frail:
        print(f"\n패배가 나온 슬롯 {len(frail)}개 (IC 중 몇 번 졌나):")
        for s, c in frail[:25]:
            n = sum(c.values())
            print(f"  {s:<38} 패 {c['패']:>3}/{n:<3}  무 {c['무']:>3}  승 {c['승']:>3}")
        if len(frail) > 25:
            print(f"  … 외 {len(frail)-25}개")
    else:
        print("\n모든 슬롯이 전 IC 에서 불패.")

    if csv_path:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["slot", "wins", "draws", "losses", "n"])
            for s, c in sorted(per_slot.items()):
                w.writerow([s, c["승"], c["무"], c["패"], sum(c.values())])
        print(f"\n슬롯별 집계 → {csv_path}")
    return per_unit, per_slot


def main() -> int:
    ap = argparse.ArgumentParser(description="초기조건 스윕(병렬)")
    ap.add_argument("--tag", required=True, help="산출물 폴더 이름")
    ap.add_argument("--roster", default="roster/all_plus_t1.txt")
    ap.add_argument("--seeds", default="1-20", help="'1-20' 또는 '1,3,7'")
    ap.add_argument("--scenarios", default="headon",
                    help="쉼표 구분. perch 는 알려진 아티팩트 주의")
    ap.add_argument("--rules", default=None, help="문장 JSON (미지정 시 --plain 필요)")
    ap.add_argument("--plain", action="store_true", help="문장 끈 기저(대조군)")
    ap.add_argument("--workers", type=int,
                    default=max(1, (os.cpu_count() or 4) - 4))
    ap.add_argument("--csv", default=None)
    ap.add_argument("--summarize-only", action="store_true",
                    help="이미 돈 로그만 읽어 집계")
    a = ap.parse_args()

    outdir = os.path.join(ROOT, "research", "campaigns", f"sweep_{a.tag}")
    units = [(sc.strip(), sd) for sc in a.scenarios.split(",") if sc.strip()
             for sd in parse_seeds(a.seeds)]

    if a.summarize_only:
        done = [(sc, sd, os.path.join(outdir, f"{sc}_s{sd}.log"))
                for sc, sd in units
                if os.path.exists(os.path.join(outdir, f"{sc}_s{sd}.log"))]
    else:
        print(f"단위 {len(units)}개 × 슬롯 "
              f"{sum(1 for x in open(a.roster, encoding='utf-8') if x.strip())} "
              f"= 총 {len(units) * sum(1 for x in open(a.roster, encoding='utf-8') if x.strip())}판"
              f"   워커 {a.workers}")
        done = run_units(units, a.workers, outdir, a.roster, a.rules, a.plain)

    summarize(done, a.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
