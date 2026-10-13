"""재현 확인 — 저장소에 들어 있는 기존 경기 6개를 이 컴퓨터에서 다시 돌려 소수점 끝자리까지 같은지 본다.

  python research/indi/verify_repro.py

모두 일치  → 이 컴퓨터의 결과를 기존 results/indi/*.json 과 섞어 써도 된다.
불일치 있음 → 실행은 되지만 경기별 값이 다르다. 새 실험은 한 컴퓨터에서 끝까지 돌리고(대응 쌍이 같은 환경에서 나오게),
             논문 재현 정보에 아래 '환경' 줄을 적는다. 통계 결론은 바뀌지 않을 것으로 보지만 개별 경기는 다를 수 있다.
기준 환경: Windows 11, Python 3.14.3, jsbsim 1.3.1, numpy 2.4.2, Intel i5-1135G7 (2026-10-13 확인, 6/6 일치).
"""
from __future__ import annotations

import json
import os
import platform
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import runner                                           # noqa: E402
from workers import auto_workers, ram_gb                # noqa: E402

# (결과 파일, 경기 순번) — 명목 / 튜닝 설정 / 양측 지연 / 청군만 지연 / 지연 용량 / 적 트리·시나리오가 고루 섞이게
REF = [("e3_nominal", 0), ("e2_n100", 7), ("e2_n100", 1512), ("e3_wide_delay", 7), ("e5_asym", 133), ("e5_dose", 1001)]
KEYS = ("winner", "condition", "time_s", "hp_blue", "hp_red", "ata_blue", "ata_red")


def _games(o):
    if isinstance(o, list):
        for x in o:
            if isinstance(x, dict) and "winner" in x and "blue_cfg" in x:
                yield x
            else:
                yield from _games(x)
    elif isinstance(o, dict):
        for v in o.values():
            yield from _games(v)


def _replay(g):
    from aircombat.control.indi import INDIConfig, SensorConfig
    t = time.time()
    r = runner.play(runner.BLUE_TREE, os.path.join(runner.ROOT, "redteams", f"{g['red']}.yaml"),
                    g["scenario"], g["seed"], blue_cfg=INDIConfig(**g["blue_cfg"]), red_cfg=INDIConfig(**g["red_cfg"]),
                    sensor=SensorConfig(**g["sensor"]), nz_protect=g["nz_protect"], envelope=g["envelope"],
                    model=g["model"], cond=g["cond"])
    return {k: r[k] for k in KEYS}, time.time() - t


def main():
    import jsbsim
    import numpy
    print(f"환경: {platform.platform()} | Python {platform.python_version()} | jsbsim {jsbsim.__version__} | "
          f"numpy {numpy.__version__} | {platform.processor() or platform.machine()} | "
          f"코어 {os.cpu_count()} | 메모리 {ram_gb():.1f} GB | 자동 병렬 수 {auto_workers()}")
    refs = []
    for fn, i in REF:
        g = list(_games(json.load(open(os.path.join(runner.ROOT, "results", "indi", f"{fn}.json"), encoding="utf-8"))))[i]
        refs.append((f"{fn}[{i}]", g))
    t0 = time.time()
    out = runner.pmap(_replay, [g for _, g in refs])
    ok = 0
    for (name, g), (r, sec) in zip(refs, out):
        diff = [k for k in KEYS if r[k] != g[k]]
        ok += not diff
        print(f"{'일치' if not diff else '불일치'}  {name:20s} {g['red']:13s} {g['scenario']:14s} "
              f"지연 {g['sensor']['delay_ticks']}틱  {g['winner']}/{g['condition']}  {sec:5.1f} s"
              + "".join(f"\n      {k}: 저장 {g[k]!r}  재실행 {r[k]!r}" for k in diff))
    print(f"\n{ok}/{len(refs)} 일치 — 총 {time.time() - t0:.0f} s"
          + ("  → 기존 결과와 섞어 써도 됩니다." if ok == len(refs) else "  → verify_repro.py 맨 위 설명을 보세요."))
    sys.exit(0 if ok == len(refs) else 1)


if __name__ == "__main__":
    main()
