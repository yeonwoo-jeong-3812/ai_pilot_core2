"""장식 노브 회귀 검사 — 참가자에게 "튜닝 가능"이라 연 값이 거동에 도달하는가.

배경(2026-08-24): 개방 목록의 4필드가 `audit` 딕셔너리 안에서만 소비되고 있었다
(slant_ft_lo·ata_target_lo/hi·corner_kcas_hi). 문법도 이름도 멀쩡해서 리뷰·타입체크·
기존 테스트 전부를 통과했다. 같은 부류(= 지령했는데 출력이 안 변함)를 잡는 정적 검사다.

이 검사가 잡는 것: 소비처가 로그/감사뿐인 필드.
이 검사가 못 잡는 것: 소비는 하는데 결과에 영향이 없는 경우(예: 설정 객체에 넘겼으나
그 객체가 무시). 그건 게이트 발동 계측(실매치 tick 집계)이 담당한다 — 상보 관계다.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.guidance.doctrine import DOCTRINE_BOUNDS
from aircombat.tactics import dsl

GUIDANCE = os.path.join(os.path.dirname(__file__), "..", "aircombat", "guidance",
                        "bfm_guidance.py")

# 감사 전용으로 두는 것이 정당한 필드 — 근거를 여기 적고 통과시킨다.
# corner_kcas_hi: 코너 플래토 상한. limiter 는 lo 만 쓴다(상한은 구조 한계로 이미 포화,
#   limiter.py 주석 참조). 물리적으로 조절에 연결할 자리가 없다 — 개방 목록에서 빼는
#   것이 정직하나, 이미 공지된 필드라 운영 결정 전까지 예외로 둔다.
AUDIT_ONLY_OK = {"corner_kcas_hi"}


def _audit_line_range(src: str) -> tuple[int, int]:
    """`audit = {` … 닫는 `}` 의 줄 범위 (1-based, 양끝 포함)."""
    lines = src.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("audit = {"))
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            return start + 1, i + 1
    raise AssertionError("audit 딕셔너리의 끝을 찾지 못했다")


class TestNoDeadKnobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(GUIDANCE, encoding="utf-8") as f:
            cls.src = f.read()
        cls.lines = cls.src.splitlines()
        cls.audit_lo, cls.audit_hi = _audit_line_range(cls.src)

    def _outside_audit(self, pattern: str) -> list[int]:
        rx = re.compile(pattern)
        return [i for i, ln in enumerate(self.lines, 1)
                if rx.search(ln) and not (self.audit_lo <= i <= self.audit_hi)]

    def test_doctrine_fields_reach_control(self):
        """교리 필드는 감사 딕셔너리 밖에서 최소 한 번 소비돼야 한다."""
        for key in DOCTRINE_BOUNDS:
            with self.subTest(field=key):
                hits = self._outside_audit(rf"\bdoc(?:trine)?\.{key}\b|self\.doc\.{key}\b")
                if key in AUDIT_ONLY_OK:
                    continue
                self.assertTrue(hits,
                                f"교리 필드 {key!r} 가 audit 안에서만 쓰인다 — "
                                "참가자에게 튜닝 가능하다고 열어 두고 거동은 안 바뀐다. "
                                "조절에 연결하거나 DOCTRINE_BOUNDS 에서 뺄 것.")

    def test_action_params_reach_control(self):
        """액션 숫자 파라미터도 마찬가지 — 유도 계산에 도달해야 한다."""
        for key in dsl._ACTION_BOUNDS:
            with self.subTest(param=key):
                hits = self._outside_audit(rf"\b{key}\b")
                self.assertTrue(hits,
                                f"액션 파라미터 {key!r} 가 유도 계산에 도달하지 않는다.")

    def test_audit_only_exceptions_are_justified(self):
        """예외 목록은 실제로 개방된 필드만 담아야 한다(오타·유물 방지)."""
        self.assertTrue(AUDIT_ONLY_OK <= set(DOCTRINE_BOUNDS),
                        f"예외 목록에 개방되지 않은 필드가 있다: "
                        f"{AUDIT_ONLY_OK - set(DOCTRINE_BOUNDS)}")


if __name__ == "__main__":
    unittest.main()
