"""분석: games.csv → 결과. 팀원 몫 (빈 틀). 입력 열의 정의는 bt/CONTRACT.md §2.

모든 함수는 games.csv 를 읽기만 한다. 원자료를 고치거나 지우지 않는다.
"""
from __future__ import annotations


def load(path: str):
    """games.csv → DataFrame. end_reason == "wall_clock" 행은 빼고, 뺀 수를 알린다."""
    raise NotImplementedError


def score(df):
    """경기별 점수 열 추가. 입력: load() 결과. 출력: 같은 DataFrame + 점수 열 (승 1 / 무 0.5 / 패 0 등, 정의는 사전등록)."""
    raise NotImplementedError


def theta_table(df):
    """θ 별 요약. 출력: theta_id 당 1행, 10개 파라미터 + dummy + 48셀 평균 점수·off_frac·def_frac·e_adv_ft."""
    raise NotImplementedError


def sensitivity(table):
    """파라미터 민감도. 입력: theta_table() 결과. 출력: 파라미터당 1행 (dummy 포함, dummy 는 잡음 하한 기준선)."""
    raise NotImplementedError
