"""실전 매치에서 L3 조종 권한이 실제로 얼마나 포화되는지 계측.

run_corner_pull.py 는 "최대G 지령을 계속 준다"는 **강제된 최악 케이스**라 elevator
포화율이 100% 로 나온다. 하지만 실제 교리(`_regulate_g`)는 ATA 비례 백오프·에너지
백오프를 걸므로 매치 중 상시 최대G 는 아니다. 따라서 봉투 모델을 손댈지 말지는
**실전 분포**로 판단해야 한다.

계측 항목 (매 L3 틱):
  · elevator/aileron 명령 포화 여부 (|u| > 0.999)
  · 교리가 지령한 g_target vs 실제 달성 G (감사 로그 정직성)
  · g_target 이 리미터 상한(g_avail)에 붙어 있는 비율
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.control.limiter import G_FT_S2
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.match import Match
from aircombat.engine.scenarios import initial_conditions


def instrument(pilot, log: list):
    """control_step 을 감싸 매 틱 권한·G 지표를 적재 (엔진 무변경)."""
    inner = pilot.control_step

    def wrapped(foe):
        inner(foe)
        p = pilot.plant
        phi, theta = p["attitude/phi-rad"], p["attitude/theta-rad"]
        g_lift = float(np.cos(phi) * np.cos(theta))
        n_act = (p["velocities/q-rad_sec"] * p["velocities/vt-fps"] / G_FT_S2
                 + g_lift)
        au = pilot._gc.audit if pilot._gc else {}
        log.append((abs(p["fcs/elevator-cmd-norm"]) > 0.999,
                    abs(p["fcs/aileron-cmd-norm"]) > 0.999,
                    au.get("g_target", np.nan), au.get("g_avail", np.nan),
                    n_act, p["velocities/vc-kts"],
                    au.get("g_deficit", np.nan),      # L2 감사가 스스로 신고한 격차
                    au.get("g_sustained", np.nan)))
    pilot.control_step = wrapped


def report(tag: str, log: list):
    a = np.array(log, dtype=float)
    g_cmd, g_avail, g_act = a[:, 2], a[:, 3], a[:, 4]
    on_limiter = g_cmd > 0.98 * g_avail
    hard = g_cmd > 4.0                      # 유의미한 당김 구간만
    print(f"\n[{tag}]  틱 {len(a)}")
    print(f"  elevator 포화     {100 * a[:, 0].mean():>5.1f} %"
          f"   (당김 구간만: {100 * a[hard, 0].mean() if hard.any() else 0:>5.1f} %)")
    print(f"  aileron  포화     {100 * a[:, 1].mean():>5.1f} %")
    print(f"  g_target 이 상한  {100 * on_limiter.mean():>5.1f} %")
    print(f"  g_target  평균/95%ile  {np.nanmean(g_cmd):>5.2f} / "
          f"{np.nanpercentile(g_cmd, 95):>5.2f}")
    print(f"  실제 G    평균/95%ile  {np.nanmean(g_act):>5.2f} / "
          f"{np.nanpercentile(g_act, 95):>5.2f}")
    if hard.any():
        err = g_act[hard] - g_cmd[hard]
        print(f"  당김 구간 지령-실제 격차  평균 {np.nanmean(err):>+5.2f} G"
              f"  (지령 {np.nanmean(g_cmd[hard]):.2f} → 실제 {np.nanmean(g_act[hard]):.2f})")
    print(f"  KCAS 평균/최저    {np.nanmean(a[:, 5]):>5.0f} / {np.nanmin(a[:, 5]):>5.0f}")
    if a.shape[1] > 6 and not np.all(np.isnan(a[:, 6])):
        # 교차검증: L2 감사가 신고한 g_deficit 이 독립 계산과 일치해야 한다
        print(f"  감사 g_deficit 평균 {np.nanmean(a[:, 6]):>+5.2f} G"
              f"  (지속 봉투 평균 {np.nanmean(a[:, 7]):>4.2f} G)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blue", default="redteams/red_textbook.yaml")
    ap.add_argument("--red", default="redteams/red_two_circle.yaml")
    ap.add_argument("--scenario", default="headon")
    args = ap.parse_args()

    ic = initial_conditions(args.scenario)
    bp, bd = load_policy(args.blue)
    rp, rd = load_policy(args.red)
    blue = make_pilot("Blue", ic["blue"], bp, bd)
    red = make_pilot("Red", ic["red"], rp, rd)
    blue_log, red_log = [], []
    instrument(blue, blue_log)
    instrument(red, red_log)

    m = Match(blue, red)
    res = m.run()
    print(f"\n결과: {res.winner} ({res.condition}) {res.time_s:.1f}s"
          f"  |  {args.blue} vs {args.red} / {args.scenario}")
    report(os.path.basename(args.blue), blue_log)
    report(os.path.basename(args.red), red_log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
