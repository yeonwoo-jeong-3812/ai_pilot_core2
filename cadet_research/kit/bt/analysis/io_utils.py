"""결과 CSV·설계 파일을 pandas 로 읽는 유일한 방법 (CONTRACT.md §2). 읽기만 한다.

pandas 기본 읽기는 식별자를 숫자로 바꾼다: theta_id "686747538e50" → 6.87e+58, "242774203459" → 정수,
engine_sha "1e0101026959" → inf. 그래서 식별자·문자열 열은 문자열로 읽고, 숫자 열만 숫자로 바꾼다.

  from io_utils import read_games, read_design      # bt/analysis/ 가 sys.path 에 있을 때
  df = read_games("bt/out/bt-main/games.csv")
  design = read_design("bt/thetas/main_morris_r16.csv")
"""
from __future__ import annotations

import os
import sys

import pandas as pd

BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BT not in sys.path:
    sys.path.insert(0, BT)

# 문자열로 둘 열 (CONTRACT.md §2 의 식별자·문자열 열). 이 밖의 열은 숫자로 바꾼다 (빈 칸 → NaN).
STR_COLS = ("stage", "theta_id", "scenario", "opponent", "opponent_set", "seed_salt", "seed", "winner", "end_reason",
            "win_mode", "node_frac", "node_frac_red", "engine_sha", "tree_sha", "code_commit", "host", "python_version")


def _read(path: str, str_cols) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)          # 먼저 모두 문자열 그대로
    for c in df.columns:
        if c not in str_cols:
            df[c] = pd.to_numeric(df[c].replace("", None), errors="raise")
    return df


def read_games(path: str) -> pd.DataFrame:
    """games.csv (또는 같은 열 이름의 부분 집합: fixtures, merge 결과) → DataFrame.
    STR_COLS 는 문자열 (빈 칸은 ""), 나머지는 숫자 (빈 칸은 NaN, 숫자가 아니면 오류)."""
    return _read(path, STR_COLS)


def read_design(path: str) -> pd.DataFrame:
    """설계 파일 (bt/thetas/*.csv) → DataFrame. 파라미터 11개는 float, trajectory·step 은 int, variant 는 문자열 (있으면).
    theta_id 열을 붙인다: run_bt.read_thetas 와 같은 값 정규화로 make_tree.theta_id 를 계산하므로 games.csv 의 theta_id 와 같다."""
    import make_tree as mt
    import run_bt
    df = _read(path, ("variant",))
    for c in ("trajectory", "step"):
        if c in df.columns:
            df[c] = df[c].astype(int)
    df["theta_id"] = [mt.theta_id(t) for t in run_bt.read_thetas(path)]
    return df
