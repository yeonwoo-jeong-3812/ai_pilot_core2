"""디브리프 PNG 용량 회귀 — 팔레트 변환이 실제로 걸려 있는가.

리플레이 스토리지에서 디브리프 PNG 가 ACMI 와 맞먹는 852 MB 를 차지하던 것을
`_save` 의 256색 변환으로 줄였다(실측 1,065 KB → 368 KB). 이 변환이 조용히
빠지면 용량만 도로 늘고 그림은 멀쩡해 보여서 아무도 눈치채지 못한다.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.debrief.replay_debrief import _save


def _figure(plt):
    """디브리프와 비슷한 다색 선 플롯 — 단색 도형이면 압축 차이가 안 난다."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 6))
    for i, ax in enumerate(axes.ravel()):
        for k in range(6):
            ax.plot([x / 50 for x in range(500)],
                    [((x * (k + 1) + i * 37) % 100) / 10 for x in range(500)], lw=1.2)
        ax.grid(alpha=.3)
        ax.legend([f"s{k}" for k in range(6)], fontsize=7)
    fig.tight_layout()
    return fig


class TestDebriefPngSize(unittest.TestCase):
    def setUp(self):
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            self.skipTest("matplotlib 미설치")
        from PIL import Image           # matplotlib 전이 의존성 — 없으면 변환도 못 한다
        self.plt, self.Image = plt, Image

    def test_palette_shrinks_and_keeps_geometry(self):
        with tempfile.TemporaryDirectory() as d:
            plain = os.path.join(d, "plain.png")
            small = os.path.join(d, "small.png")

            fig = _figure(self.plt)
            fig.savefig(plain, dpi=130)          # _save 가 안쪽에서 하는 것과 같은 호출
            self.plt.close(fig)

            fig = _figure(self.plt)
            _save(fig, small)
            self.plt.close(fig)

            self.assertLess(os.path.getsize(small), os.path.getsize(plain),
                            "팔레트 변환이 안 걸렸다 — 용량이 줄지 않았다")
            with self.Image.open(plain) as a, self.Image.open(small) as b:
                self.assertEqual(a.size, b.size, "해상도가 바뀌었다 — 축소는 색만이어야 한다")
                self.assertEqual(b.mode, "P", f"팔레트 이미지가 아니다: {b.mode}")

    def test_kwargs_pass_through(self):
        """bbox_inches 같은 savefig 인자가 그대로 전달된다(plot_debrief 가 쓴다)."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "tight.png")
            fig = _figure(self.plt)
            _save(fig, out, bbox_inches="tight")
            self.plt.close(fig)
            self.assertTrue(os.path.getsize(out) > 0)


if __name__ == "__main__":
    unittest.main()
