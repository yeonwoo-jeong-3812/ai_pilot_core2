"""agent.schema.json 생성기 — 어휘 완전성 + 전 코퍼스 스키마 통과 (드리프트 감시).

jsonschema 는 개발 전용 의존성 — 미설치면 코퍼스 검증만 skip (어휘 검사는 항상).
"""
import glob
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ROOT)
import gen_references  # noqa: E402
from aircombat.tactics.conditions import CONDITIONS  # noqa: E402

try:
    import jsonschema
except ImportError:
    jsonschema = None
import yaml  # noqa: E402


class TestAgentSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = gen_references.build_schema()   # 내부 assert 가 DSL 드리프트 검사

    def test_condition_vocab_complete(self):
        cond = self.schema["definitions"]["node"]["properties"]["condition"]
        names = {v["properties"]["name"]["const"] for v in cond["anyOf"][1:]}
        self.assertEqual(names, set(CONDITIONS))
        self.assertEqual(set(cond["anyOf"][0]["enum"]), set(CONDITIONS))

    @unittest.skipIf(jsonschema is None, "jsonschema 미설치 (개발 전용)")
    def test_corpus_validates(self):
        files = [os.path.join(ROOT, "config", "tactics.yaml")]
        for d in ("examples", "redteams"):
            files += sorted(glob.glob(os.path.join(ROOT, d, "*.yaml")))
        self.assertGreater(len(files), 5)
        for p in files:
            with open(p, encoding="utf-8") as f:
                spec = yaml.safe_load(f)
            with self.subTest(file=os.path.relpath(p, ROOT)):
                jsonschema.validate(spec, self.schema)

    @unittest.skipIf(jsonschema is None, "jsonschema 미설치 (개발 전용)")
    def test_doc_snippets_validate(self):
        """REFERENCE 의 학습용 YAML 스니펫은 손으로 쓴 산문 — 어휘가 바뀌면 조용히 썩는다."""
        blocks = re.findall(r"```yaml\n(.*?)```", gen_references._actions(), re.S)
        self.assertGreaterEqual(len(blocks), 3)
        for i, block in enumerate(blocks):
            with self.subTest(snippet=i):
                jsonschema.validate(yaml.safe_load(block), self.schema)


if __name__ == "__main__":
    unittest.main()
