"""교리 파라미터 배선 회귀 — 2026-08-17 개방(기본 on). 거부 경로도 회귀 유지. (JSBSim 불필요)"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.guidance import doctrine as doc_mod
from aircombat.guidance.doctrine import Doctrine, DOCTRINE_BOUNDS
from aircombat.tactics.dsl import load_agent_yaml
from aircombat.tactics.policy import TacticPolicy

AGENT_WITH_DOCTRINE = """\
doctrine:
  initial_pull_g: 6.5
  fighting_kts_lo: 330.0
selector:
  - action: {pursuit: pure, name: x}
"""

AGENT_TREE_ONLY = """\
selector:
  - action: {pursuit: pure, name: x}
"""


def _tmp_yaml(text: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    return f.name


class _TuningOff:
    """테스트 한정 잠금 토글 — 미개방 거부 경로 회귀용."""
    def __enter__(self):
        self._saved = doc_mod.TUNING_ENABLED
        doc_mod.TUNING_ENABLED = False

    def __exit__(self, *exc):
        doc_mod.TUNING_ENABLED = self._saved


class TestDoctrineOverrides(unittest.TestCase):
    def test_no_overrides_is_default(self):
        self.assertEqual(Doctrine.from_overrides(None), Doctrine())
        self.assertEqual(Doctrine.from_overrides({}), Doctrine())

    def test_open_by_default(self):
        # 2026-08-17 개방 — 기본 상태에서 doctrine 블록 수용
        self.assertTrue(doc_mod.TUNING_ENABLED)
        d = Doctrine.from_overrides({"initial_pull_g": 6.5})
        self.assertEqual(d.initial_pull_g, 6.5)

    def test_locked_state_rejects(self):
        # 거부 경로 회귀 — 재잠금 시에도 명시적 오류가 유지되어야 한다
        with _TuningOff(), self.assertRaisesRegex(ValueError, "개방"):
            Doctrine.from_overrides({"initial_pull_g": 6.5})

    def test_valid_overrides(self):
        d = Doctrine.from_overrides({"initial_pull_g": 6.5,
                                     "fighting_kts_lo": 330.0})
        self.assertEqual(d.initial_pull_g, 6.5)
        self.assertEqual(d.fighting_kts_lo, 330.0)
        self.assertEqual(d.g_fraction, Doctrine().g_fraction)   # 나머지는 기본값

    def test_unknown_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "미지 교리 필드"):
            Doctrine.from_overrides({"warp_drive": 1.0})

    def test_out_of_manual_range_rejected(self):
        with self.assertRaisesRegex(ValueError, "허용 범위"):
            Doctrine.from_overrides({"initial_pull_g": 9.5})   # 교범 6–8G

    def test_band_lo_above_hi_rejected(self):
        with self.assertRaisesRegex(ValueError, "lo > hi"):
            Doctrine.from_overrides({"fighting_kts_lo": 375.0,
                                     "fighting_kts_hi": 325.0})

    def test_bounds_cover_all_fields(self):
        # 클램프 테이블 = Doctrine 전체 필드 (자동 문서·검증의 단일 진실 보장)
        self.assertEqual(set(DOCTRINE_BOUNDS), set(Doctrine().to_yaml_dict()))
        for lo, hi in DOCTRINE_BOUNDS.values():
            self.assertLessEqual(lo, hi)

    def test_defaults_inside_bounds(self):
        d = Doctrine().to_yaml_dict()
        for k, (lo, hi) in DOCTRINE_BOUNDS.items():
            self.assertTrue(lo <= d[k] <= hi, k)


class TestAgentYamlDoctrineBlock(unittest.TestCase):
    def test_block_extracted_and_tree_built(self):
        p = _tmp_yaml(AGENT_WITH_DOCTRINE)
        try:
            overrides, root, _, _ = load_agent_yaml(p)
            self.assertEqual(overrides, {"initial_pull_g": 6.5,
                                         "fighting_kts_lo": 330.0})
            self.assertIsNotNone(root)
            pol = TacticPolicy.from_yaml(p)
            self.assertEqual(pol.doctrine_overrides, overrides)
        finally:
            os.unlink(p)

    def test_tree_only_has_no_overrides(self):
        p = _tmp_yaml(AGENT_TREE_ONLY)
        try:
            overrides, _, agent_name, _ = load_agent_yaml(p)
            self.assertIsNone(overrides)
            self.assertIsNone(agent_name)
            self.assertIsNone(TacticPolicy.from_yaml(p).doctrine_overrides)
        finally:
            os.unlink(p)

    def test_agent_name_extracted(self):
        p = _tmp_yaml("agent_name: MyViper\naction: {pursuit: pure, name: x}\n")
        try:
            _, root, agent_name, _ = load_agent_yaml(p)
            self.assertEqual(agent_name, "MyViper")
            self.assertIsNotNone(root)                       # 트리는 정상 파싱
            self.assertEqual(TacticPolicy.from_yaml(p).agent_name, "MyViper")
        finally:
            os.unlink(p)

    def test_agent_name_must_be_string(self):
        p = _tmp_yaml("agent_name: [1, 2]\naction: {pursuit: pure, name: x}\n")
        try:
            with self.assertRaisesRegex(ValueError, "agent_name"):
                load_agent_yaml(p)
        finally:
            os.unlink(p)

    def test_doctrine_only_file_rejected(self):
        p = _tmp_yaml("doctrine: {initial_pull_g: 6.5}\n")
        try:
            with self.assertRaisesRegex(ValueError, "전술 트리가 없습니다"):
                load_agent_yaml(p)
        finally:
            os.unlink(p)

    def test_empty_file_rejected(self):
        p = _tmp_yaml("")
        try:
            with self.assertRaisesRegex(ValueError, "빈 에이전트 파일"):
                load_agent_yaml(p)
        finally:
            os.unlink(p)

    def test_non_mapping_block_rejected(self):
        p = _tmp_yaml("doctrine: 6.5\nselector:\n  - action: {pursuit: pure, name: x}\n")
        try:
            with self.assertRaisesRegex(ValueError, "매핑"):
                load_agent_yaml(p)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
