"""실험 설계: θ 목록 만들기. 팀원 몫 (빈 틀). 계약은 bt/CONTRACT.md §4.

출력은 run_bt.py 가 읽는 θ 목록 파일(CSV 또는 JSON)이다. 열 = params.yaml 의 10개 이름 + dummy.
범위는 make_tree.PARAMS 의 lo/hi 를 쓴다. 값 검사는 make_tree.normalize 가 한다.
"""
from __future__ import annotations


def baseline() -> list[dict]:
    """기준 θ 1개. 반환: [{<10개 이름>: float, "dummy": float}]"""
    raise NotImplementedError


def oat(levels: int) -> list[dict]:
    """한 번에 하나씩(OAT): 기준에서 파라미터 하나만 lo..hi 를 levels 등분으로 바꾼 θ 들."""
    raise NotImplementedError


def lhs(n: int, seed: int) -> list[dict]:
    """라틴 하이퍼큐브 n 점 (dummy 포함 11차원). 같은 seed 면 같은 목록.
    차원마다 [0,1) 을 n 층으로 나눠 층을 무작위로 섞고 층 안에서 균등 추출 → lo..hi 로 늘린다."""
    import numpy as np
    import make_tree as mt
    rng = np.random.default_rng(seed)
    dims = mt.PARAMS + [mt.DUMMY]
    u = (np.array([rng.permutation(n) for _ in dims]).T + rng.random((n, len(dims)))) / n
    return [{p["name"]: float(p["lo"]) + float(x) * (float(p["hi"]) - float(p["lo"]))
             for p, x in zip(dims, row)} for row in u]


def morris(r: int, levels: int, seed: int) -> list[dict]:
    """Morris 궤적 r 개 (SALib.sample.morris.sample 표준 생성, 수준 levels, dummy 포함 11요인).
    반환: 궤적마다 θ 12개 (= 요인 + 1), 순서대로. 각 θ 에 trajectory (0..r-1), step (0..11) 을 붙인다. 같은 seed 면 같은 목록."""
    from SALib.sample import morris as ms
    import make_tree as mt
    dims = mt.PARAMS + [mt.DUMMY]
    problem = {"num_vars": len(dims), "names": [p["name"] for p in dims],
               "bounds": [[float(p["lo"]), float(p["hi"])] for p in dims]}
    x = ms.sample(problem, N=r, num_levels=levels, seed=seed)
    k = len(dims) + 1
    return [{**{p["name"]: float(v) for p, v in zip(dims, row)}, "trajectory": i // k, "step": i % k}
            for i, row in enumerate(x)]


def write(thetas: list[dict], path: str) -> None:
    """θ 목록을 CSV(.csv) 또는 JSON(.json)으로 쓴다. 열 순서 = make_tree.NAMES + ["dummy"]."""
    raise NotImplementedError


MAIN_SEED = 20261108   # PREREG_BT.md §5


def make_main(out_dir: str) -> dict:
    """본실험 설계 파일 두 개를 만든다 (PREREG_BT.md §5). 반환: {파일 이름: SHA-256}.
    main_lhs64.csv = lhs(64, MAIN_SEED), main_morris_r16.csv = morris(16, 4, MAIN_SEED) (+ trajectory, step 열)."""
    import csv
    import hashlib
    import os
    import make_tree as mt
    cols = mt.NAMES + ["dummy"]
    out = {}
    for name, rows, extra in (("main_lhs64.csv", lhs(64, MAIN_SEED), []),
                              ("main_morris_r16.csv", morris(16, 4, MAIN_SEED), ["trajectory", "step"])):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols + extra, lineterminator="\n")
            w.writeheader()
            w.writerows({k: (repr(v) if isinstance(v, float) else v) for k, v in t.items()} for t in rows)
        with open(path, "rb") as f:
            out[name] = hashlib.sha256(f.read()).hexdigest()
    return out


if __name__ == "__main__":     # python bt/designs.py → bt/thetas/main_*.csv 생성, SHA-256 출력
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for k, v in make_main(os.path.join(os.path.dirname(os.path.abspath(__file__)), "thetas")).items():
        print(k, v)
