"""디브리프 한글 라벨 회귀 — 폰트가 있는데도 두부(□)로 나가지 않는가.

2026-08 Lambda 이관 후 실제로 났던 사고: 이미지에는 Noto CJK 가 깔려 있었지만
후보 이름 목록에 없어 DejaVu 로 떨어졌고, 웹 매치 상세의 디브리프 PNG 한글이
전부 두부가 됐다. 이름 목록이 아니라 **글리프 보유**로 고르는지 확인한다.
"""
import os
import sys
import unittest
import warnings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.debrief.trace import init_mpl, korean_family


class TestDebriefFont(unittest.TestCase):
    def setUp(self):
        self.plt = init_mpl()
        if self.plt is None:
            self.skipTest("matplotlib 미설치")
        if korean_family() is None:
            self.skipTest("한글 폰트가 없는 환경 — 여기서는 두부가 정상")

    def test_selected_family_has_hangul(self):
        """고른 폰트는 한글 글리프를 실제로 갖고 있다 (DejaVu 가 뽑히면 실패)."""
        from matplotlib import font_manager as fm
        from matplotlib.ft2font import FT2Font
        path = fm.findfont(korean_family(), fallback_to_default=False)
        self.assertNotEqual(FT2Font(path).get_char_index(ord("한")), 0)

    def test_korean_label_renders_without_missing_glyph(self):
        """한글 라벨을 실제로 그려 '글리프 없음' 경고가 나오지 않음을 확인."""
        fig = self.plt.figure(figsize=(2, 1))
        fig.text(0.1, 0.5, "매치 디브리프 잔여 체력")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.canvas.draw()
        self.plt.close(fig)
        missing = [str(w.message) for w in caught if "missing from font" in str(w.message)]
        self.assertEqual(missing, [], f"두부로 렌더됐다: {missing}")


if __name__ == "__main__":
    unittest.main()
