"""논문 도식 초안: 그림 1(5계층 구조와 열화 주입 위치), 그림 2(설계 흐름), 그림 8(사용 지도). 자료를 읽지 않는 도형 그림.

  python supplementary/paper_diagrams.py   # → paper_figs/fig1_architecture.png, fig2_design.png, fig8_usage.png

숫자는 원고(PAPER_DRAFT_v2.md)와 결과 보고서에서 옮겼다. 고칠 때는 원고와 함께 고친다.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "paper_figs")
plt.rcParams.update({"font.family": ["Malgun Gothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9})
INK, INK2, LINE = "#2b2b2b", "#6b6b6b", "#b5b3ad"
BLUE, ORANGE, GREEN, AMBER = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
FILL = {"ink": "#f4f3f0", "blue": "#e8f1fb", "orange": "#fdeee6", "green": "#e6f6ef", "amber": "#fdf4dd"}


def canvas(w, h):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, edge=INK2, fill="#ffffff", size=8.5, bold_first=True, ls="-", lw=1.2, align="center"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                                fc=fill, ec=edge, lw=lw, ls=ls))
    lines = text.split("\n")
    tx = x + w / 2 if align == "center" else x + 0.012
    ha = "center" if align == "center" else "left"
    n = len(lines)
    for i, s in enumerate(lines):
        yy = y + h / 2 + (n - 1) * 0.5 * 0.034 * (size / 8.5) - i * 0.034 * (size / 8.5)
        ax.text(tx, yy, s, ha=ha, va="center", fontsize=size if (i or not bold_first) else size + 0.5,
                fontweight="bold" if (i == 0 and bold_first) else "normal", color=INK)


def arrow(ax, p, q, color=INK2, lw=1.3, ls="-", style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=11, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0))


def label(ax, x, y, s, color=INK2, size=7.8, ha="left", va="center", **kw):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, **kw)


# ---------------------------------------------------------------- 그림 1
def fig1():
    fig, ax = canvas(7.2, 6.6)
    X, W = 0.04, 0.48
    L = [(0.885, 0.075, "전술 계층 — 행동트리  (20 Hz)\n추격·회피·사격 등 행동 선택", FILL["ink"]),
         (0.765, 0.075, "기본 전투 기동(BFM) 유도  (60 Hz)\n행동 → 롤 목표·피치 각속도 명령 q_cmd", FILL["ink"]),
         (0.645, 0.075, "자세→각속도 변환 · G·받음각 리미터\n하중 +9 G / −3 G, 받음각 25°에서 1 G, 롤 220 °/s", FILL["ink"]),
         (0.285, 0.235, "", FILL["blue"]),
         (0.045, 0.11, "JSBSim F-16  (120 Hz)\n비행 물리. 요 축만 내장 비행제어 법칙(FLCS)", FILL["ink"])]
    for y, h, t, f in L:
        box(ax, X, y, W, h, t, fill=f, edge=BLUE if f == FILL["blue"] else INK2)
    y4, h4 = 0.285, 0.235
    ax.text(X + 0.012, y4 + h4 - 0.03, "INDI 각속도 제어기  (120 Hz, 피치·롤)", fontsize=9, fontweight="bold", color=INK)
    for i, s in enumerate(["ν = K(ω_cmd − ω_f)         원하는 각가속도",
                           "Δu = G⁻¹(ν − ω̇_f)          더 움직일 조종면",
                           "u = u_f + Δu                  지금 위치 + 증분",
                           "K = 9 s⁻¹,  동기화 필터 25 Hz(2차)",
                           "열화는 이 계층에만 넣는다"]):
        ax.text(X + 0.02, y4 + h4 - 0.072 - i * 0.034, s, fontsize=8, color=INK if i < 4 else BLUE,
                fontweight="bold" if i == 4 else "normal")
    cx = X + W / 2
    for (y_top, y_bot, s) in ((0.879, 0.846, "행동"), (0.759, 0.726, "명령"), (0.279, 0.161, "조종면 명령 u")):
        arrow(ax, (cx, y_top), (cx, y_bot))
        label(ax, cx + 0.012, (y_top + y_bot) / 2, s)
    arrow(ax, (cx, 0.639), (cx, 0.526))
    label(ax, cx + 0.012, 0.605, "제한된 명령 ω_cmd")
    # mae 기록 지점: 리미터 뒤, 명령 지연 앞
    ax.plot([cx], [0.605], marker="o", ms=6.5, color=BLUE, mec="white", mew=1.2, zorder=5)
    label(ax, cx - 0.015, 0.605, "mae 기록 지점\n(이 명령 대 실제 피치 각속도)", color=BLUE, size=7.2, ha="right")
    # 되먹임
    arrow(ax, (X + W, 0.11), (X + W + 0.035, 0.11), style="-")
    arrow(ax, (X + W + 0.035, 0.11), (X + W + 0.035, 0.33), style="-")
    arrow(ax, (X + W + 0.035, 0.33), (X + W, 0.33))
    label(ax, X + W + 0.042, 0.15, "측정\nω, ω̇,\n조종면 위치", size=7.4)
    # 열화 주입 (오른쪽 꼬리표)
    TX, TW, TH = 0.665, 0.32, 0.068
    tags = [(0.545, "명령 전달 지연 CMD n틱 (P8)\n유도 명령이 n틱 늦게 도착", (cx + 0.004, 0.555)),
            (0.452, "κ: 제어효과 G를 κ배로 믿음\n→ 응답 시상수 ≈ κ·Δt", (X + W, 0.44)),
            (0.359, "k_q: 피치 게인 K의 배율\nf_c: 동기화 필터 차단주파수", (X + W, 0.38)),
            (0.244, "σ: 자이로 잡음 (세 축)\n비동기·동기 측정 지연 n틱", (X + W + 0.035, 0.26))]
    for y, t, tip in tags:
        box(ax, TX, y, TW, TH, t, edge=ORANGE, fill=FILL["orange"], size=7.6)
        arrow(ax, (TX, y + TH / 2), tip, color=ORANGE, lw=1.1)
    box(ax, TX, 0.04, TW, 0.15,
        "실제형 구성 (P7·P8·P9-c)\n① 구동기 1차 지연 20.2 rad/s\n   + 속도 제한(승강타 60 °/s)\n② 각가속도 = 자이로 각속도 차분\n③ 조종면 위치 = 2틱 전 실제 위치",
        edge=GREEN, fill=FILL["green"], size=7.4, align="left")
    label(ax, TX, 0.635, "열화 주입 위치", color=ORANGE, size=8.5, fontweight="bold")
    label(ax, 0.04, 0.985, "그림 1. 5계층 구조와 열화 주입 위치", color=INK, size=9.5, fontweight="bold")
    fig.savefig(os.path.join(OUT, "fig1_architecture.png"), dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- 그림 2
def fig2():
    fig, ax = canvas(7.4, 5.4)
    label(ax, 0.02, 0.97, "그림 2. 설계 흐름 — 본실험에서 나온 사후 발견을 실행 전에 기준을 고정한 새 실험으로 확인", color=INK, size=9.5,
          fontweight="bold")
    rows = [(0.70, "본실험 (사전 등록)", BLUE, FILL["blue"], "-"),
            (0.42, "결과를 본 뒤 나온 발견", INK2, FILL["ink"], "--"),
            (0.10, "확인 실험 (각각 실행 전 사전 등록)", ORANGE, FILL["orange"], "-")]
    for y, s, c, _, _ in rows:
        label(ax, 0.02, y + 0.205, s, color=c, size=8.5, fontweight="bold")
    W, H, G = 0.225, 0.17, 0.018
    xs = [0.02 + i * (W + G) for i in range(4)]
    r1 = ["E1 보정\ncal 시드 8\n가짜 변형 → 허용폭\nδ_D = 0.079",
          "E2 적합\nmain 시드 8, 20조건\n(필터 × 비동기 지연)\nD = 0.144 + 0.053·mae",
          "E3 처음 보는 원인\n22조건 (κ, k_q, σ,\n동기 지연, 조합)\n5묶음 예측 성공",
          "E4 다른 참가자 12종\ngen 시드 4\n판정 없이 오차 보고"]
    r2 = ["P0 기술 점수 (사후)\n상수 예측보다\n44 % 덜 틀림",
          "E3X 높은 수준 (사전 등록)\n동기 24·κ 100·400\n예측 실패",
          "P3 오차 두 유형 (서술)\n둔한 형 대 진동형\n(교전 명령 0.14 Hz)",
          "ASYM 한 기체 열화 (사전 등록)\n점수가 U자\n(가설과 반대)"]
    r3 = ["P4 새 시드 재현\nrep 시드 8\nE3X 실패·U자·유형 대비\n모두 재현",
          "P7 실제형 구성\n센서·구동기를 바꾸면?\n기울기 0.022로 바뀜\n유형 효과 +0.172 남음",
          "P8 κ가 아닌 둔한 원인\nx8 시드 8, 실제형\n명령 지연·낮은 k_q\n유형 효과 +0.330",
          "P9 U자의 원인\n원래: 자체 진동과 함께\n위치 관계 변화\n실제형: 반등 없음"]
    for (y, _, c, f, ls), texts in zip(rows, (r1, r2, r3)):
        for i, (x, t) in enumerate(zip(xs, texts)):
            box(ax, x, y, W, H, t, edge=c, fill=f, ls=ls, size=7.6)
            if i < 3 and y != rows[1][0]:
                arrow(ax, (x + W, y + H / 2), (x + W + G, y + H / 2), color=c)
    mid = 0.5
    arrow(ax, (mid, rows[0][0] - 0.01), (mid, rows[1][0] + H + 0.01), color=INK2, lw=2.0)
    label(ax, mid + 0.012, (rows[0][0] + rows[1][0] + H) / 2, "결과를 본 뒤", size=7.6)
    arrow(ax, (mid, rows[1][0] - 0.01), (mid, rows[2][0] + H + 0.01), color=ORANGE, lw=2.0)
    label(ax, mid + 0.012, (rows[1][0] + rows[2][0] + H) / 2, "판정 기준을 먼저 고정하고 새 실험으로 확인", size=7.6,
          color=ORANGE)
    label(ax, 0.02, 0.035, "곁가지 확인: P1 교전 없는 시험 비행으로 대체 불가 · P2-b 정밀 조준 기총에서도 반등 64 % · P5 참가자 대 시드 판정 불가 · "
          "P6 정밀 조준 기총 대칭 판정 불가", size=7.2)
    fig.savefig(os.path.join(OUT, "fig2_design.png"), dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- 그림 8
def fig8():
    fig, ax = canvas(7.2, 5.0)
    label(ax, 0.02, 0.965, "그림 8. 사용 지도 — 교전 중 피치 추종 오차로 결과 변화를 가늠해도 되는가", color=INK, size=9.5,
          fontweight="bold")
    Q = dict(edge=INK2, fill="#ffffff", size=8)
    NO = dict(edge=AMBER, fill=FILL["amber"], size=7.6)
    YES = dict(edge=GREEN, fill=FILL["green"], size=7.8)
    qx, qw, qh = 0.04, 0.40, 0.11
    qs = [(0.79, "① 곡선을 맞춘 것과 같은 제어기 구성인가?"),
          (0.60, "② 알고 싶은 것이 결과 변화의 '크기'인가?"),
          (0.41, "③ 비교하는 열화들의 오차 유형이 비슷한가?"),
          (0.22, "④ 열화가 있는 조건끼리 비교하는가?")]
    nos = ["곡선을 다시 맞춘다\n(구성당 약 2.7만 경기. 실제형에서 기울기 0.053 → 0.022)",
           "방향(좋아짐·나빠짐)이 궁금하면 쓰지 않는다\n(자체 진동이 있는 제어기에서는 방향을 거꾸로 가리킬 수 있다)",
           "한 곡선에 섞지 않는다\n(같은 mae에서 둔한 형이 결과를 더 바꾼다)",
           "열화 유무의 효과라면 쓰지 않는다\n(열화가 있기만 해도 흔들림 바닥 약 0.10–0.17)"]
    for (y, q), n in zip(qs, nos):
        box(ax, qx, y, qw, qh, q, bold_first=False, **Q)
        box(ax, 0.52, y, 0.45, qh, n, bold_first=False, **NO)
        arrow(ax, (qx + qw, y + qh / 2), (0.52, y + qh / 2), color=AMBER)
        label(ax, qx + qw + 0.008, y + qh / 2 + 0.02, "아니오", color=AMBER, size=7.2)
    for (y1, _), (y2, _) in zip(qs[:-1], qs[1:]):
        arrow(ax, (qx + qw / 2, y1), (qx + qw / 2, y2 + qh), color=GREEN)
        label(ax, qx + qw / 2 + 0.01, (y1 + y2 + qh) / 2, "예", color=GREEN, size=7.2)
    arrow(ax, (qx + qw / 2, qs[-1][0]), (qx + qw / 2, 0.15), color=GREEN)
    label(ax, qx + qw / 2 + 0.01, 0.185, "예", color=GREEN, size=7.2)
    box(ax, 0.04, 0.03, 0.93, 0.12,
        "쓸 수 있다: 결과 변화의 크기를 상수 예측보다 44 % 덜 틀리게 가늠(사후 비교)\n"
        "검증한 범위 mae ≲ 3.6 °/s 안에서 D 단위 ±0.03–0.05 정도로 쓰고, 교전 없는 시험 비행 값으로 대신하지 않는다",
        bold_first=False, **YES)
    fig.savefig(os.path.join(OUT, "fig8_usage.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig1(); fig2(); fig8()
    print("done", [f for f in os.listdir(OUT) if f.startswith(("fig1", "fig2", "fig8"))])
