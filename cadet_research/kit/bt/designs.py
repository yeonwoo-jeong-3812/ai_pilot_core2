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
    """라틴 하이퍼큐브 n 점 (dummy 포함 11차원). 같은 seed 면 같은 목록."""
    raise NotImplementedError


def write(thetas: list[dict], path: str) -> None:
    """θ 목록을 CSV(.csv) 또는 JSON(.json)으로 쓴다. 열 순서 = make_tree.NAMES + ["dummy"]."""
    raise NotImplementedError
