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


def test_lhs_reproducible():
    import csv
    import designs
    a, b = designs.lhs(50, 20261102), designs.lhs(50, 20261102)
    assert a == b and a != designs.lhs(50, 1)
    for p in mt.PARAMS + [mt.DUMMY]:                     # 차원마다 n 층에 한 점씩
        lo, hi = float(p["lo"]), float(p["hi"])
        strata = sorted(min(int((t[p["name"]] - lo) / (hi - lo) * 50), 49) for t in a)
        assert strata == list(range(50)), p["name"]
    with open(os.path.join(BT, "thetas", "pilot_lhs50.csv"), encoding="utf-8", newline="") as f:
        assert [{k: float(v) for k, v in r.items()} for r in csv.DictReader(f)] == a    # 저장된 목록 = lhs(50, 20261102)


def test_patched_opponents_only_climb_node():
    """보정 상대 = 원본에서 최우선 low_altitude → climb 노드만 바뀜 (floor_ft 4500, g_burst 0.8). 나머지 바이트 동일."""
    for name, rel in run_bt.OPPONENTS.items():
        src = open(os.path.join(run_bt.KIT, rel), "rb").read()
        dst = open(os.path.join(run_bt.KIT, run_bt.OPPONENT_SETS["patched"][name]), "rb").read()
        nl = b"\r\n" if b"\r\n" in src else b"\n"
        old = nl.join([b"      floor_ft: 1200.0", b"  - action:", b"      pursuit: pure", b"      aim_above_ft: 4000.0"])
        new = nl.join([b"      floor_ft: 4500.0", b"  - action:", b"      pursuit: pure", b"      g_burst: 0.8",
                       b"      aim_above_ft: 4000.0"])
        assert src.count(old) == 1 and dst == src.replace(old, new), name
        top = yaml.safe_load(dst)["selector"][0]["sequence"]
        assert top == [{"condition": {"name": "low_altitude", "floor_ft": 4500.0}},
                       {"action": {"pursuit": "pure", "g_burst": 0.8, "aim_above_ft": 4000.0, "name": "climb"}}], name


def test_shard_partition():
    """--shard i/n: 겹치지 않고 빠짐없이 나뉘고, 합치면 전체와 같다 (같은 θ 목록·n)."""
    import designs
    jobs = run_bt.build_jobs([mt.normalize(t) for t in designs.lhs(5, 7)], "bt-smoke")
    key = lambda j: tuple(str(j[k]) for k in run_bt.KEY)
    for n in (1, 2, 3, 7):
        parts = [run_bt.shard(jobs, f"{i}/{n}") for i in range(1, n + 1)]
        keys = [key(j) for p in parts for j in p]
        assert len(keys) == len(set(keys)) == len(jobs) and set(keys) == {key(j) for j in jobs}, n
        assert max(map(len, parts)) - min(map(len, parts)) <= 1, n
    assert run_bt.shard(jobs, None) == jobs
    for bad in ("0/2", "3/2", "2", "a/b"):
        try:
            run_bt.shard(jobs, bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_nseeds_default_unchanged():
    """--nseeds 기본 4 는 예전 시드와 같고, 36 이면 앞 4개가 같은 시드에 32개가 더 붙는다."""
    th = [mt.normalize(BASE)]
    old = [(j["scenario"], j["opponent"], j["seed_salt"], j["seed"]) for j in run_bt.build_jobs(th, "bt-cal")]
    assert old == [(j["scenario"], j["opponent"], j["seed_salt"], j["seed"]) for j in run_bt.build_jobs(th, "bt-cal", nseeds=4)]
    assert len(old) == 48 and {x[2] for x in old} == {f"bt-cal-{i}" for i in range(4)}
    assert old[0][3] == run_bt.derive_seed(old[0][0], "bt-cal-0")
    many = run_bt.build_jobs(th, "bt-confirm", nseeds=36)
    assert len(many) == 432 and len({j["seed_salt"] for j in many}) == 36
    four = {(j["scenario"], j["opponent"], j["seed_salt"], j["seed"]) for j in run_bt.build_jobs(th, "bt-confirm")}
    assert four <= {(j["scenario"], j["opponent"], j["seed_salt"], j["seed"]) for j in many}


def test_main_design_files():
    """본실험 설계 파일: 범위·더미·θ 개수·궤적 구조, 같은 seed 면 같은 파일 (PREREG_BT.md §5 의 SHA-256)."""
    import csv
    import hashlib
    import shutil
    import tempfile
    import designs
    tmp = tempfile.mkdtemp()
    try:
        made = designs.make_main(tmp)
        for name, sha in made.items():
            with open(os.path.join(BT, "thetas", name), "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")                       # 줄끝 LF 기준 (bt/.gitattributes)
                assert hashlib.sha256(data).hexdigest() == sha, name           # 저장된 파일 = 같은 seed 로 다시 만든 파일
        assert designs.make_main(tmp) == made
    finally:
        shutil.rmtree(tmp)
    dims = mt.PARAMS + [mt.DUMMY]
    for name, n in (("main_lhs64.csv", 64), ("main_morris_r16.csv", 192)):
        with open(os.path.join(BT, "thetas", name), encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == n and "dummy" in rows[0], name
        for p in dims:
            assert all(float(p["lo"]) <= float(r[p["name"]]) <= float(p["hi"]) for r in rows), (name, p["name"])
        ths = run_bt.read_thetas(os.path.join(BT, "thetas", name))         # 설명 열은 θ 에서 빠진다
        assert len({mt.theta_id(t) for t in ths}) == n, name
    m = designs.morris(16, 4, designs.MAIN_SEED)
    assert m == designs.morris(16, 4, designs.MAIN_SEED) and m != designs.morris(16, 4, 1)
    assert len(m) == 192 and sorted({t["trajectory"] for t in m}) == list(range(16))
    for p in dims:
        assert len({t[p["name"]] for t in m}) == 4, p["name"]                 # 수준 4
    for tr in range(16):                                                     # 궤적 안에서 한 번에 요인 하나만 바뀐다
        pts = [t for t in m if t["trajectory"] == tr]
        assert [t["step"] for t in pts] == list(range(12))
        changed = [sum(a[p["name"]] != b[p["name"]] for p in dims) for a, b in zip(pts, pts[1:])]
        assert changed == [1] * 11, (tr, changed)
        assert sorted(next(p["name"] for p in dims if a[p["name"]] != b[p["name"]]) for a, b in zip(pts, pts[1:])) == \
            sorted(p["name"] for p in dims)


def test_read_games_keeps_ids():
    """숫자+e·숫자만인 theta_id 와 engine_sha 를 read_games 는 문자열로 보존하고, pandas 기본 읽기는 깨뜨린다."""
    import csv
    import math
    import tempfile
    import pandas as pd
    sys.path.insert(0, os.path.join(BT, "analysis"))
    from io_utils import read_games, read_design
    ids = ["686747538e50", "06930348e037", "242774203459"]          # 본실험 θ 에 실제로 있는 형태
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["theta_id", "seed", "engine_sha", "code_commit", "wez_blue", "wez_red", "t_first_wez", "node_frac"])
            for i in ids:
                w.writerow([i, "0123", "1e0101026959", "a7bbb5f88b9d", "3.5", "1.25", "", ""])
        bad = pd.read_csv(path)                                      # pandas 기본
        assert bad.theta_id.dtype != object and math.isinf(bad.engine_sha.iloc[0]), bad.dtypes
        assert str(bad.theta_id.iloc[1]) != "06930348e037"
        good = read_games(path)
        assert list(good.theta_id) == ids and list(good.engine_sha) == ["1e0101026959"] * 3
        assert list(good.seed) == ["0123"] * 3 and list(good.code_commit) == ["a7bbb5f88b9d"] * 3
        assert list(good.wez_blue - good.wez_red) == [2.25] * 3 and good.t_first_wez.isna().all()
        assert list(good.node_frac) == [""] * 3
    finally:
        os.remove(path)
    d = read_design(os.path.join(BT, "thetas", "main_morris_r16.csv"))
    l = read_design(os.path.join(BT, "thetas", "main_lhs64.csv"))
    e_ids = {"686747538e50", "443592e60339", "06930348e037", "220745e32020"}     # 본실험 θ 256개 중 숫자+e 형태 전부
    assert set(d.theta_id) | set(l.theta_id) >= e_ids and "242774203459" in set(d.theta_id) | set(l.theta_id)
    assert str(d.trajectory.dtype).startswith("int") and len(d) == 192 and len(l) == 64


def _job(tree):
    j = run_bt.build_jobs([mt.normalize(BASE)], "bt-smoke")
    j = next(x for x in j if x["scenario"] == "neutral" and x["opponent"] == "B2_Extender_00")
    return {**j, "tree": tree, "engine_sha": "test", "code_commit": "test"}


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
