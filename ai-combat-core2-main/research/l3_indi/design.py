"""본실험 설계 상수 — 개정 A6(조건 선택), A9(기동), A11(RQ2 조건) 을 한곳에 모은다.

능력표는 `reports/capability_05b869f2e4.csv` (P2 보고서가 쓴 표) 에서 격자점 값을 그대로 읽는다.
"""
from __future__ import annotations

import csv
import os

from .harness import Condition

HERE = os.path.dirname(os.path.abspath(__file__))
CAPABILITY_CSV = os.path.join(HERE, "reports", "capability_05b869f2e4.csv")

RQ1_ALTS_KFT = (8, 14, 24)          # P2 보고서 §4 (개정 A6 선택 규칙 적용 결과)
RQ1_KCAS = (250, 350, 400)
RQ2_ALT_KFT = 14                    # 개정 A11-5
RQ2_KCAS = (250, 350, 400)


def rq1_conditions(fbw: int) -> list[Condition]:
    return [Condition(a * 1000.0, float(k), fbw_override=fbw) for a in RQ1_ALTS_KFT for k in RQ1_KCAS]


def rq2_conditions(fbw: int) -> list[Condition]:
    return [Condition(RQ2_ALT_KFT * 1000.0, float(k), fbw_override=fbw) for k in RQ2_KCAS]


_CAP = None


def capability(cond: Condition) -> dict:
    """격자점 (alt_kft, kcas, fbw) 의 능력표 행. 격자점이 아니면 KeyError."""
    global _CAP
    if _CAP is None:
        _CAP = {}
        with open(CAPABILITY_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (int(r["fbw_override"]), int(float(r["alt_kft"])), int(float(r["kcas"])))
                _CAP[key] = {"C_nz": float(r["C_nz"]), "C_p": float(r["C_p"]),
                             "trim_valid": r["trim_valid"] in ("1", "1.0", "True")}
    return _CAP[(int(cond.fbw_override), int(round(cond.alt_ft / 1000.0)), int(round(cond.kcas)))]
