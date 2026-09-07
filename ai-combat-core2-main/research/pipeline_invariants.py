"""M1 — 파이프라인 불변식 라이브러리 (AUTOMATION_PLAN §S8).

함정 카탈로그(방법론 6.2·3.2)를 기계 검사로 변환한다. pytest 는
test_pipeline_invariants.py 참조; 이 모듈은 검사 함수 자체를 제공한다.
"""
from __future__ import annotations

import csv
import glob
import json
import os

PM = os.path.dirname(os.path.abspath(__file__))
LBL = os.path.join(PM, "data", "blueteam")
REP = os.path.join(PM, "campaigns")
WIT = os.path.join(REP, "witness")
LOGS = os.path.join(REP, "logs")
OPP = os.path.normpath(os.path.join(PM, "..", "roster"))


# ── 함정 3(순서·차폐) — 정적 발화 스케줄 시뮬레이터 ────────────────────────
def load_rules(path: str) -> list[dict]:
    return json.load(open(path))


def load_dump_case(dump_path: str, case: str) -> list[tuple[float, dict]]:
    rows = []
    with open(dump_path) as f:
        for r in csv.DictReader(f):
            if r["tag"] == case:
                rows.append((float(r["t"]), r))
    return rows


def static_fire_schedule(rules: list[dict], rows: list[tuple[float, dict]]
                         ) -> list[tuple[float, int]]:
    """_surgical 의미론 그대로: 순서대로 검사, 활성 우선반환, 1회성 소진.

    반환: [(t, rule_idx)] — 각 결정틱에 제어를 쥔 문장(발화 or 활성유지).
    ※ 근사 한계: 첫 발화 이후 실제 궤적은 분기하므로, 이 스케줄은 "첫 발화
    이전"까지가 정확하고 이후는 무발화-가정 궤적 기준이다. 차폐(자기 문장의
    진입이 남의 활성 창에 먹히는 것)는 첫 발화 전후 판정이 목적이라 유효.
    """
    until: list[float | None] = [None] * len(rules)
    consumed: list[bool] = [False] * len(rules)
    events = []
    for t, r in rows:
        got = None
        for i, ru in enumerate(rules):
            if until[i] is not None:
                if t < until[i]:
                    got = i
                    break
                consumed[i] = True
                until[i] = None
                continue
            if consumed[i]:
                continue
            box = ru["box"]
            try:
                inside = all(float(box[k][0]) <= float(r[k]) <= float(box[k][1])
                             for k in box)
            except KeyError:
                inside = False   # 덤프에 없는 특징 축 → 발화 불가로 간주
            if inside:
                until[i] = t + float(ru.get("dur", 6.0))
                got = i
                break
        if got is not None:
            events.append((t, got))
    return events


def shadow_fingerprint(rules_path: str, dump_path: str) -> dict[str, list]:
    """검증-시점 발화 스케줄 지문: case -> [t, first_rule_idx].

    차폐가 항상 결함은 아니다(공동 피복 문장의 의도된 선점 존재 — E1_06 r3).
    올바른 불변식은 "검증된 구성의 스케줄에서의 이탈"이므로, 정본화 시점에
    지문을 저장하고 이후 실행은 지문 대조로 드리프트를 검출한다."""
    rules = load_rules(rules_path)
    fp = {}
    cases = sorted({c for ru in rules for c in ru.get("covers", [])})
    for case in cases:
        rows = load_dump_case(dump_path, case)
        ev = static_fire_schedule(rules, rows) if rows else []
        fp[case] = [round(ev[0][0], 2), ev[0][1]] if ev else None
    return fp


def save_fingerprint(rules_path: str, dump_path: str) -> str:
    out = rules_path.replace(".json", ".fingerprint.json")
    json.dump(dict(dump=os.path.basename(dump_path),
                   schedule=shadow_fingerprint(rules_path, dump_path)),
              open(out, "w"), indent=1)
    return out


def fingerprint_drift(rules_path: str, dump_path: str) -> dict:
    """저장된 지문 대비 현재 스케줄의 이탈 목록 (없으면 빈 dict)."""
    ref_p = rules_path.replace(".json", ".fingerprint.json")
    ref = json.load(open(ref_p))["schedule"]
    cur = shadow_fingerprint(rules_path, dump_path)
    return {c: dict(ref=ref.get(c), cur=cur.get(c))
            for c in set(ref) | set(cur) if ref.get(c) != cur.get(c)}


def shadow_report(rules_path: str, dump_path: str) -> dict[str, dict]:
    """각 문장의 covers 케이스에 대해: 제 문장이 첫 제어를 쥐는가 판정.

    상태: OK(자기 문장이 첫 발화) / SHADOWED(다른 문장이 먼저 발화·활성) /
    NOFIRE(아무 문장도 발화 예측 없음).
    """
    rules = load_rules(rules_path)
    out = {}
    for i, ru in enumerate(rules):
        for case in ru.get("covers", []):
            rows = load_dump_case(dump_path, case)
            if not rows:
                out[case] = dict(status="NODATA", rule=i)
                continue
            ev = static_fire_schedule(rules, rows)
            if not ev:
                out[case] = dict(status="NOFIRE", rule=i)
            else:
                first = ev[0][1]
                out[case] = dict(status="OK" if first == i else "SHADOWED",
                                 rule=i, first_rule=first, t=ev[0][0])
    return out


# ── 함정 1(좌표계) — 덤프 키와 런타임 특징의 동일성 ──────────────────────
def feats_schema_matches() -> bool:
    """LedgerPilot._DUMP_KEYS ⊆ _feats 반환 키 (스텁 호출로 실검사)."""
    import types
    import research.proto_ledger_gate as G
    stub = types.SimpleNamespace(
        _prev_alt=None, health=100.0,
        ledger=types.SimpleNamespace(foe_dmg=0.0, hot_run=0.0, t=0.0, armed=False,
                                     pursue_ratio=lambda: 0.0))
    o = types.SimpleNamespace(distance_ft=1e4, ata_deg=1.0, aa_deg=179.0,
                              ego_vc_kts=350.0, ego_alt_ft=15000.0,
                              alt_gap_ft=0.0, closure_kts=800.0,
                              enm_vc_kts=350.0, enm_theta_deg=0.0,
                              enm_alt_ft=15000.0)
    feats = G.LedgerPilot._feats(stub, o)
    return set(G.LedgerPilot._DUMP_KEYS) <= set(feats)


# ── 함정 5(파일명·개행) ───────────────────────────────────────────────────
def witness_names_valid(scratch: str = WIT) -> list[str]:
    """bs_*.log 파일명이 실존 상대 stem 으로 파싱되는지. 위반 목록 반환."""
    stems = {os.path.splitext(f)[0] for f in os.listdir(OPP)
             if f.endswith(".yaml")}
    bad = []
    for p in glob.glob(os.path.join(scratch, "bs_*.log")):
        b = os.path.basename(p)[3:-4]
        core = b.split("@")[0]
        if "_" not in core:
            bad.append(p)
            continue
        stem, side = core.rsplit("_", 1)
        if side not in ("blue", "red") or stem not in stems:
            bad.append(p)
    return bad


def crlf_lint(paths: list[str]) -> list[str]:
    """드라이버가 read 하는 텍스트 파일의 CR 오염 검사. 위반 목록 반환."""
    bad = []
    for p in paths:
        if os.path.exists(p) and b"\r" in open(p, "rb").read():
            bad.append(p)
    return bad


# ── 함정 6(세대 덮어쓰기) ─────────────────────────────────────────────────
def claim_generation_dir(path: str) -> str:
    """세대 폴더 선점 — 이미 내용물이 있으면 거부(덮어쓰기 사고 방지)."""
    if os.path.isdir(path) and os.listdir(path):
        raise FileExistsError(
            f"세대 폴더가 비어있지 않음: {path} — 새 세대명을 쓰거나 기존을 "
            "이름 변경 보존하십시오 (v2 세대 소실 사고 재발 방지)")
    os.makedirs(path, exist_ok=True)
    return path
