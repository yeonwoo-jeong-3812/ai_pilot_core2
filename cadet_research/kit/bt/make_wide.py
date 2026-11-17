"""넓은 상대 일반화 실험의 후보 상대 31개 → bt/opponents_wide/ (cadet_research/PREREG_BT_ADDENDUM_WIDE.md §3). 같은 입력이면 같은 파일.

  python bt/make_wide.py

후보 = 지금 엔진에서 불러올 수 있고, 앞서 쓴 상대 14종·청 트리와 트리가 같지 않은 상대. 같은 계열은 이름 순 앞 2개까지.
변종 (near) = 앞서 쓴 계열에서 나온 상대, 새 유형 (far) = 앞서 쓰지 않은 계열.
고도 보정은 opponent_patch_rules.md 와 같은 바이트 규칙 (최우선 low_altitude floor_ft 1200 → climb 노드만). 패턴이 없으면 원본 그대로.
원본 파일은 읽기만 한다. 합격 점검 (bt/analysis/wide_check.py) 을 통과한 상대만 본실험 묶음 wide 에 들어간다.
"""
from __future__ import annotations

import csv
import os

import yaml

BT = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(BT)
CORE = os.path.join(os.path.dirname(os.path.dirname(KIT)), "ai-combat-core2-main")
OUT = os.path.join(BT, "opponents_wide")
E4, ROSTER, RED, AGENTS, EX = "kit:agents/e4", "core:roster", "core:redteams", "core:agents", "core:examples"
BLUE_NODES = {"recover_altitude", "break_defense", "gun_track", "energy_recover", "press_offense", "yoyo_pull_up", "yoyo_dive_cut", "pure_default"}

# (이름, 출처 폴더, 계열, 종류). 같은 트리가 kit/agents/e4 에도 있으면 e4 쪽을 쓴다.
CANDIDATES = [
    ("A1_PurePursuer_02", ROSTER, "A1", "near"), ("A1_PurePursuer_05", E4, "A1", "near"),
    ("A2_GunTracker_03", ROSTER, "A2", "near"), ("A2_GunTracker_06", E4, "A2", "near"),
    ("A3_LagAngler_03", ROSTER, "A3", "near"), ("A3_LagAngler_06", E4, "A3", "near"),
    ("B1_EnergyFighter_06", E4, "B1", "near"), ("B2_Extender_04", E4, "B2", "near"),
    ("C1_TwoCircleRate_03", E4, "C1", "near"), ("red_reactive", RED, "D1", "near"),
    ("red_adaptive", RED, "E1", "near"), ("redteam_energy", ROSTER, "red_energy", "near"),
    ("Iceman_v1", AGENTS, "Iceman", "far"), ("Iceman_v2", AGENTS, "Iceman", "far"),
    ("maverick_JesterF", AGENTS, "JesterF", "far"), ("meta_hybrid_v1", AGENTS, "meta_hybrid", "far"),
    ("test-eebba6a2", AGENTS, "participant", "far"), ("doctrine_regulator", EX, "doctrine_regulator", "far"),
    ("starter", EX, "starter", "far"), ("textbook_headon", EX, "textbook_headon", "far"),
    ("red_allround", RED, "allround", "far"), ("red_attacker", RED, "attacker", "far"),
    ("red_knife", RED, "knife", "far"), ("red_phangman", RED, "phangman", "far"),
    ("red_pressure", RED, "pressure", "far"), ("redteam_pressure", ROSTER, "pressure", "far"),
    ("red_textbook", RED, "textbook", "far"), ("red_two_circle", RED, "two_circle", "far"),
    ("E2_Passive_00", ROSTER, "E2", "far"), ("anchor_aggressive", ROSTER, "anchor", "far"),
    ("anchor_simple", ROSTER, "anchor", "far"),
]


def source(folder: str, name: str) -> str:
    root, sub = folder.split(":")
    return os.path.join(KIT if root == "kit" else CORE, sub, name + ".yaml")


def patch(src: bytes) -> tuple[bytes, bool]:
    nl = b"\r\n" if b"\r\n" in src else b"\n"
    old = nl.join([b"      floor_ft: 1200.0", b"  - action:", b"      pursuit: pure", b"      aim_above_ft: 4000.0"])
    new = nl.join([b"      floor_ft: 4500.0", b"  - action:", b"      pursuit: pure", b"      g_burst: 0.8", b"      aim_above_ft: 4000.0"])
    n = src.count(old)
    assert n <= 1
    return src.replace(old, new), n == 1


def _actions(node, out):
    if isinstance(node, dict):
        a = node.get("action")
        if isinstance(a, dict) and "name" in a:
            out.append(a["name"])
        for v in node.values():
            _actions(v, out)
    elif isinstance(node, list):
        for v in node:
            _actions(v, out)
    return out


def recovery_node(tree: dict) -> str:
    """최우선 분기가 low_altitude 로 시작하면 그 분기의 action 이름 (고도 회복 노드), 아니면 빈칸."""
    first = (tree.get("selector") or [None])[0]
    seq = first.get("sequence") if isinstance(first, dict) else None
    if not seq:
        return ""
    c = seq[0].get("condition") if isinstance(seq[0], dict) else None
    if (c if isinstance(c, str) else (c or {}).get("name")) != "low_altitude":
        return ""
    names = _actions(seq, [])
    return names[0] if names else ""


def build() -> list[dict]:
    rows = []
    for name, folder, family, kind in CANDIDATES:
        src = open(source(folder, name), "rb").read()
        dst, patched = patch(src)
        tree = yaml.safe_load(dst.decode("utf-8"))
        acts = set(_actions(tree, []))
        rows.append(dict(name=name, source=folder.replace("kit:", "kit/").replace("core:", "ai-combat-core2-main/") + "/" + name + ".yaml",
                         family=family, kind=kind, patched=int(patched), recovery_node=recovery_node(tree),
                         blue_overlap=len(acts & BLUE_NODES), bytes=dst))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = build()
    for r in rows:
        open(os.path.join(OUT, r["name"] + ".yaml"), "wb").write(r["bytes"])
    cols = ["name", "source", "family", "kind", "patched", "recovery_node", "blue_overlap"]
    with open(os.path.join(OUT, "manifest.csv"), "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r["name"], r["kind"], r["family"], "patched" if r["patched"] else "-", r["recovery_node"] or "(no recovery node)", r["blue_overlap"])


if __name__ == "__main__":
    main()
