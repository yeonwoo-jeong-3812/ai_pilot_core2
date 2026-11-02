"""θ(dict) → 트리 YAML. 같은 θ 면 같은 파일(bt/trees/<theta_id>.yaml)이 나온다.

  python bt/make_tree.py                         # 기준 θ 트리를 만들고 경로를 찍는다
  python bt/make_tree.py thetas.csv [--r0]       # 목록의 θ 마다 트리를 만들고 경로를 찍는다

θ 는 params.yaml 의 10개 이름(+ 선택 dummy)을 키로 갖는 dict. 범위 밖이거나 엔진 DSL 이
거부하는 값은 ValueError. 트리 내용은 dummy 와 무관하다.
r0=True (R0 검증 전용) 일 때만 params.yaml 범위 검사를 건너뛴다. 엔진 DSL 검사(load_policy)는 그대로 한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

import yaml

BT = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(BT)
sys.path.insert(0, KIT)

from aircombat.engine.factory import load_policy  # noqa: E402

TREES = os.path.join(BT, "trees")
with open(os.path.join(BT, "params.yaml"), encoding="utf-8") as f:
    _P = yaml.safe_load(f)
PARAMS = _P["params"]
NAMES = [p["name"] for p in PARAMS]
DUMMY = _P["dummy"]
BASE = {p["name"]: float(p["base"]) for p in PARAMS}
with open(os.path.join(BT, "tree_template.yaml"), encoding="utf-8") as f:
    TEMPLATE = f.read()


def normalize(theta: dict, r0: bool = False) -> dict:
    """키 검사 + float 변환 + 범위 검사(r0 면 생략). dummy 가 없으면 None."""
    keys = set(theta) - {"dummy"}
    if keys != set(NAMES):
        raise ValueError(f"θ 키 불일치: 빠짐 {sorted(set(NAMES) - keys)}, 미지 {sorted(keys - set(NAMES))}")
    out, errors = {}, []
    for p in PARAMS + [DUMMY]:
        v = theta.get(p["name"])
        if v is None or v == "":
            if p is DUMMY:
                out["dummy"] = None
                continue
            errors.append(f"{p['name']} 값 없음")
            continue
        v = float(v)
        if not r0 and not p["lo"] <= v <= p["hi"]:
            errors.append(f"{p['name']}={v} — 범위 [{p['lo']}, {p['hi']}] 밖")
        out[p["name"]] = v
    if errors:
        raise ValueError("θ 거부: " + "; ".join(errors))
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def theta_id(theta: dict, r0: bool = False) -> str:
    """θ(10개 + dummy)의 해시. 숫자는 float repr 로 맞춰서 6000 과 6000.0 이 같다."""
    t = normalize(theta, r0)
    return _sha(json.dumps({k: t[k] for k in NAMES + ["dummy"]}, sort_keys=True))


def render(theta: dict, r0: bool = False) -> str:
    t = normalize(theta, r0)
    return re.sub(r"\{([a-z_]+)\}", lambda m: repr(t[m.group(1)]), TEMPLATE)


def make_tree(theta: dict, r0: bool = False) -> str:
    """트리 파일 경로. 파일 이름은 트리에 들어가는 10개 값의 해시라 dummy 만 다른 θ 는 같은 파일을 쓴다."""
    text = render(theta, r0)
    t = normalize(theta, r0)
    path = os.path.join(TREES, _sha(json.dumps({k: t[k] for k in NAMES}, sort_keys=True)) + ".yaml")
    if not os.path.isfile(path):
        os.makedirs(TREES, exist_ok=True)
        tmp = path + f".{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        try:
            load_policy(tmp)           # 엔진이 경기 때 쓰는 바로 그 검증 (DSL 범위 포함)
        except Exception as e:
            os.remove(tmp)
            raise ValueError(f"엔진이 트리를 거부: {e}") from e
        os.replace(tmp, path)
    return path


def tree_sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


if __name__ == "__main__":
    import argparse
    import csv
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("thetas", nargs="?", help="θ 목록 CSV (없으면 기준 θ)")
    ap.add_argument("--r0", action="store_true", help="params.yaml 범위 밖 허용 (R0 검증 전용, DSL 범위는 지킴)")
    a = ap.parse_args()
    if a.thetas:
        with open(a.thetas, encoding="utf-8", newline="") as f:
            for th in csv.DictReader(f):
                print(theta_id(th, a.r0), make_tree(th, a.r0))
    else:
        print(make_tree({**BASE, "dummy": DUMMY["base"]}, a.r0))
