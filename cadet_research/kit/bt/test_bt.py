"""bt/ 자가점검. python bt/test_bt.py (pytest 로도 돈다). 약 1–3분.

1. 기준 θ 트리 == 원본 energy_fighter.yaml (YAML 구조·값 비교, 숫자는 float 로 맞춤)
2. 파라미터마다 값을 바꾸면 params.yaml 의 node.key 자리 하나만 바뀐다 (자리표시자 위치 검증)
3. 범위 밖 θ 는 거부, 같은 θ 는 같은 파일·같은 theta_id. --r0 는 params 범위 밖을 허용하되 DSL 범위 밖은 거부
4. 원본 트리와 기준 θ 트리로 같은 경기를 돌리면 결과가 같다 (의미상 동일)
5. 같은 경기 두 번 = 모든 열이 같다 (wall_s, host 제외)
"""
import json
import os
import sys

import yaml

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import make_tree as mt  # noqa: E402
import run_bt  # noqa: E402

ORIGINAL = os.path.join(BT, "energy_fighter.yaml")   # 원본 (ai-combat-core2-main/examples 에서 옮김, 내용 그대로)
BASE = {**mt.BASE, "dummy": mt.DUMMY["base"]}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _num(x):
    if isinstance(x, dict):
        return {k: _num(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_num(v) for v in x]
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


def _leaves(x, path=()):
    """(경로, 값, 그 값을 가진 dict). dict 의 name 으로 노드를 식별한다."""
    if isinstance(x, dict):
        for k, v in x.items():
            if isinstance(v, (dict, list)):
                yield from _leaves(v, path + (k,))
            else:
                yield path + (k,), v, x
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _leaves(v, path + (i,))


def test_baseline_equals_original():
    assert _num(_load(mt.make_tree(BASE))) == _num(_load(ORIGINAL))


def test_each_param_hits_its_node():
    base = list(_leaves(_num(_load(mt.make_tree(BASE)))))
    for p in mt.PARAMS:
        v = p["lo"] if float(p["lo"]) != float(p["base"]) else p["hi"]
        got = list(_leaves(_num(_load(mt.make_tree({**BASE, p["name"]: v})))))
        diff = [(a, b) for a, b in zip(base, got) if a[1] != b[1]]
        assert len(diff) == 1, (p["name"], diff)
        (path, old, node), (_, new, _) = diff[0]
        assert node.get("name") == p["node"] and path[-1] == p["key"], (p["name"], path, node)
        assert old == float(p["base"]) and new == float(v), (p["name"], old, new)


def test_reject_and_stable_id():
    for bad in ({**BASE, "gun_range_ft": 3500}, {**BASE, "lead_time_s": 3.2}, {**BASE, "dummy": 2},
                {k: v for k, v in BASE.items() if k != "floor_ft"}):
        try:
            mt.make_tree(bad)
        except ValueError:
            continue
        raise AssertionError(f"거부해야 함: {bad}")
    as_int = {**BASE, "merge_range_ft": 6000, "floor_ft": 4500}
    assert mt.theta_id(as_int) == mt.theta_id(BASE) and mt.make_tree(as_int) == mt.make_tree(BASE)
    assert mt.make_tree({**BASE, "dummy": 0.1}) == mt.make_tree(BASE)        # 트리는 같고
    assert mt.theta_id({**BASE, "dummy": 0.1}) != mt.theta_id(BASE)          # θ 는 다르다


def test_r0_and_win_mode():
    r0 = {**BASE, "floor_ft": 40000}
    assert mt.normalize(r0, r0=True)["floor_ft"] == 40000.0 and os.path.isfile(mt.make_tree(r0, r0=True))
    for bad in ({**BASE, "lead_time_s": 3.2}, {**BASE, "break_g_burst": 1.5}):    # DSL 범위 밖
        try:
            mt.make_tree(bad, r0=True)
        except ValueError:
            continue
        raise AssertionError(f"r0 여도 DSL 이 거부해야 함: {bad}")
    wm = run_bt.win_mode
    assert (wm("blue", "health_zero"), wm("blue", "hard_deck"), wm("blue", "stall"), wm("blue", "timeout"),
            wm("blue", "out_of_bounds"), wm("red", "health_zero"), wm("draw", "no_contact")) ==         ("shootdown", "opp_hard_deck", "opp_stall", "judge", "other", "", "")


def _job(tree):
    j = run_bt.build_jobs([mt.normalize(BASE)], "bt-smoke")
    j = next(x for x in j if x["scenario"] == "neutral" and x["opponent"] == "B2_Extender_00")
    return {**j, "tree": tree, "engine_sha": "test"}


VOLATILE = ("wall_s", "host", "tree_sha")


def test_same_match_as_original_and_deterministic():
    a = run_bt.play(_job(mt.make_tree(BASE)))
    b = run_bt.play(_job(mt.make_tree(BASE)))
    o = run_bt.play(_job(ORIGINAL))
    assert a["end_reason"] != "wall_clock", a
    diff = [k for k in run_bt.FIELDS if k not in VOLATILE and a[k] != b[k]]
    assert not diff, ("같은 경기 두 번이 다르다", {k: (a[k], b[k]) for k in diff})
    diff = [k for k in run_bt.FIELDS if k not in VOLATILE and a[k] != o[k]]
    assert not diff, ("원본 트리와 결과가 다르다", {k: (a[k], o[k]) for k in diff})
    assert abs(sum(json.loads(a["node_frac"]).values()) - 1) < 1e-3, a["node_frac"]
    print("  경기:", {k: a[k] for k in ("winner", "end_reason", "win_mode", "hp_blue", "hp_red", "node_frac", "wall_s")})


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("[ok]", name)
    print("bt 자가점검 통과")
