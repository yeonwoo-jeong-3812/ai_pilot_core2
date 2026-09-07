"""M1 — 파이프라인 자가검증 pytest (AUTOMATION_PLAN §S8, 판정 기준: 함정 주입 시 검출).

usage: python -m pytest research/test_pipeline_invariants.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from research import pipeline_invariants as I

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
FINAL = os.path.join(I.LBL, "induced_rules_f31_A11.json")   # 정본(루프31)
DUMP_V2 = os.path.join(I.LBL, "obs_dump_f31_A11.csv")        # 배포-구성 덤프


# 함정 1 — 좌표계: 덤프 키가 런타임 _feats 와 일치
def test_feats_schema():
    assert I.feats_schema_matches()


# 함정 2 — 실행 스위치: RULEBOX 만 있고 SURGICAL 없으면 경고 발생 (주입 검사)
def test_switch_guard_warns():
    env = dict(os.environ, LG_RULEBOX=FINAL)
    env.pop("LG_SURGICAL", None)
    r = subprocess.run([sys.executable, "-c",
                        "import sys; sys.path.insert(0,'.'); "
                        "import research.proto_ledger_gate"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    assert "LG_SURGICAL" in r.stderr and "경고" in r.stderr


# 함정 3 — 순서·차폐: 검증된 스케줄 지문에서의 이탈을 검출 (주입 검사)
def test_shadow_fingerprint_canonical():
    assert I.fingerprint_drift(FINAL, DUMP_V2) == {}, "정본 스케줄 드리프트"


def test_shadow_detects_reorder(tmp_path):
    import shutil
    rules = json.load(open(FINAL))
    reordered = rules[1:] + rules[:1]          # 후행-선두 원칙 위반 주입(r3 를 꼴찌로)
    p = str(tmp_path / "reordered.json")
    json.dump(reordered, open(p, "w"))
    shutil.copy(FINAL.replace(".json", ".fingerprint.json"),
                p.replace(".json", ".fingerprint.json"))
    # 지문의 rule 인덱스는 순서 의존 → 재배치는 (t, idx) 어느 쪽으로든 이탈해야 함
    drift = I.fingerprint_drift(p, DUMP_V2)
    assert drift, "순서 위반 주입이 지문 대조에서 검출되지 않음"


# 함정 5 — 파일명·CRLF (주입 검사 포함)
def test_witness_names():
    assert I.witness_names_valid() == []


def test_witness_names_detects_bad(tmp_path):
    (tmp_path / "bs_NoSuchStem_blue.log").write_text("x")
    assert I.witness_names_valid(str(tmp_path)) != []


def test_crlf_lint_detects(tmp_path):
    p = tmp_path / "cases.txt"
    p.write_bytes(b"A1/blue 38\r\n")
    assert I.crlf_lint([str(p)]) == [str(p)]
    inputs = os.path.join(PM, "campaigns", "logs", "inputs")
    real = [os.path.join(os.path.dirname(PM), "roster", "all_128.txt")] + [
        os.path.join(inputs, f)
        for f in ("loop30_reps.txt", "loop30_groups.txt", "win_only.txt",
                  "unlearned_44.txt", "bs_cases_loop29.txt", "bs_cases_rel3.txt")]
    for fp in real:
        # 부재도 실패 — crlf_lint 는 없는 파일을 건너뛰므로(재편 후 조용히
        # 무력화됐던 결함) 존재부터 단언해야 검사가 살아 있다.
        assert os.path.exists(fp), f"검사 대상 소실: {fp}"
        assert I.crlf_lint([fp]) == [], f"CRLF 오염: {fp}"


# 함정 6 — 세대 덮어쓰기 방지 (주입 검사)
def test_claim_generation_dir(tmp_path):
    d = tmp_path / "gen1"
    I.claim_generation_dir(str(d))             # 신규 → 성공
    (d / "a.acmi").write_text("x")
    with pytest.raises(FileExistsError):
        I.claim_generation_dir(str(d))         # 비어있지 않음 → 거부
