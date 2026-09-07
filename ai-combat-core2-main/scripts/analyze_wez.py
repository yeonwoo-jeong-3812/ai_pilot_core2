"""Gun WEZ 교전 분석 — 기록된 .acmi 리플레이에서 교전 시계열을 읽어
그래프(PNG)와 콘솔 요약을 낸다. 엔진(match.py)이 이미 프레임별로 다 찍으므로
이 스크립트는 읽기전용 파서일 뿐이다(엔진 변경 없음).

세 종류의 그림을 낸다 (패널 12개 — 중복·저판독 패널은 2026-07 정리):
  <이름>_wez.png      — 거리·ATA·HP·접근율-거리 위상궤적 (WEZ 근접·만족·결과)
  <이름>_energy.png   — G 사용·비에너지 Es·Ps·도그하우스 (에너지·기동 성능)
  <이름>_tactics.png  — 평면 궤적·ATA-AA 상태평면·RollOff vs dphi·L1 노드 간트

핵심(참가자용): Gavail(리미터 허용 G, 속도 이점이 곧 상한)과 Gtarget(실제 명령 G)
의 갭 = "안 쓴 G 여유". 조준 오차(ATA)가 남았는데 이 여유가 크고 코너속도 이상이면
'더 당겨 ATA 를 줄일 수 있었던 기회 후보'로 검출·표시한다(판단은 참가자 몫).

사용:
    python scripts/analyze_wez.py replays/xxx.acmi [more.acmi ...] [--show]
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.geometry.units import WEZ_ATA_TIERS
from aircombat.control.limiter import G_FT_S2
# 파서·시계열 유도·공통 헬퍼의 정본은 aircombat.debrief.trace 로 승격됨
# (replay_debrief 의 디브리프 6패널과 공유). 여기선 import 만 한다.
from aircombat.debrief.trace import (
    parse_trace as parse_acmi, bool_runs as _bool_runs, shade_runs as _shade_runs,
    smooth as _smooth, turn_rate as _turn_rate, init_mpl as _init_mpl,
    detect_opportunities, estimate_g_fraction,
    set_labels as _set_labels, matchup as _matchup,
    C_BLUE, C_RED, C_BAND, WEZ_MIN_FT, WEZ_MAX_FT,
    G_STRUCT_MAX, KCAS_CORNER_LO, KCAS_CORNER_HI, SLACK_G, OPP_ATA_LO,
)

KT_TO_FPS = 1.68781     # kt → ft/s (도그하우스 이론 선회율용)


# ── 그림 1: WEZ 근접·만족 ────────────────────────────────────────────────
def make_wez_plot(sides, events, out_png, show):
    plt = _init_mpl(show)
    if plt is None:
        print("  (그래프 생략 — matplotlib 미설치: pip install matplotlib)")
        return
    blue, red = _set_labels(sides)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(f"Gun WEZ 근접·만족 ({_matchup(blue, red)})", fontsize=13)

    # (1) 거리 vs 시간 — WEZ 사거리 밴드
    ax = axes[0, 0]
    ax.axhspan(WEZ_MIN_FT, WEZ_MAX_FT, color=C_BAND, alpha=0.18,
               label=f"WEZ 사거리 {WEZ_MIN_FT:.0f}–{WEZ_MAX_FT:.0f} ft")
    ax.plot(blue.t, blue.dist, color=C_BLUE, lw=1.5)   # 거리는 상호적 — 한 선
    ax.set_title("거리 (기체 간 사거리)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("거리 [ft]")
    ax.set_ylim(0, min(np.nanmax(blue.dist) if blue.dist.size else 1e4, 12000))
    ax.legend(loc="upper right", fontsize=8)

    # (2) ATA vs 시간 — tier 경계선 + InWEZ 음영
    ax = axes[0, 1]
    for s, c in ((blue, C_BLUE), (red, C_RED)):
        ax.plot(s.t, s.ata, color=c, lw=1.5, label=s.label)
        _shade_runs(ax, s.t, _bool_runs(s.in_wez), c)
    for boundary, _ in WEZ_ATA_TIERS:
        ax.axhline(boundary, color=C_BAND, lw=0.7, ls="--")
    ax.set_title("ATA (조준 오차, 음영은 InWEZ 구간)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("ATA [deg]")
    ax.set_ylim(0, 135)
    ax.legend(loc="upper right", fontsize=8)

    # (3) HP vs 시간 + HIT 마커
    ax = axes[1, 0]
    for s, c in ((blue, C_BLUE), (red, C_RED)):
        ax.plot(s.t, s.hp, color=c, lw=1.8, label=s.label)
    for et, _ in events:
        ax.axvline(et, color=C_BAND, lw=0.8, ls=":", alpha=0.7)
    ax.set_title(f"HP (체력, 점선은 피격 {len(events)}회)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("HP")
    ax.set_ylim(0, 105)
    ax.legend(loc="lower left", fontsize=8)

    # (4) 접근율–거리 위상궤적 — WEZ 로 수렴하는 나선인가, 과속 오버슈트인가
    ax = axes[1, 1]
    ax.axvspan(WEZ_MIN_FT, WEZ_MAX_FT, color=C_BAND, alpha=0.15, label="WEZ 사거리")
    ax.axhline(0, color=C_BAND, lw=0.8)
    sc = ax.scatter(blue.dist, blue.clo, c=blue.t, cmap="viridis", s=6,
                    alpha=0.7, edgecolors="none")
    fig.colorbar(sc, ax=ax, label="시간 [s]")
    ax.set_title("접근율–거리 위상궤적 (양수=접근; 거리는 상호적 — 한 계열)")
    ax.set_xlabel("거리 [ft]"); ax.set_ylabel("접근율 [kt]")
    ax.set_xlim(0, 10000)
    ax.legend(loc="upper right", fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_png, dpi=120)
    print(f"  그래프 저장: {out_png}")
    if show:
        plt.show()
    plt.close(fig)


# ── 그림 2: 에너지·기동 (참가자 성능 개선) ───────────────────────────────
def make_energy_plot(sides, out_png, show, opps, gf):
    plt = _init_mpl(show)
    if plt is None:
        print("  (그래프 생략 — matplotlib 미설치: pip install matplotlib)")
        return
    blue, red = _set_labels(sides)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(f"에너지·기동 ({_matchup(blue, red)})", fontsize=13)
    pair = ((blue, C_BLUE), (red, C_RED))

    # (1) G 사용: Gavail(허용 상한, 점선)·Gtarget(명령, 가는선)·Nz(실측, 굵은선)
    #     + 기회 음영 + maxG 러그. 명령–실측 갭 = 기체가 못 따라간 구간(양력·추종 한계).
    ax = axes[0, 0]
    has_nz = any(np.isfinite(s.nz).any() for s, _ in pair)
    for s, c in pair:
        ax.plot(s.t, s.gavail, color=c, lw=1.0, ls="--", alpha=0.7,
                label=f"{s.label} Gavail")
        if has_nz:
            ax.plot(s.t, s.gtgt, color=c, lw=0.8, alpha=0.5, label=f"{s.label} Gtarget")
            ax.plot(s.t, s.nz, color=c, lw=1.6, label=f"{s.label} Nz 실측")
        else:
            ax.plot(s.t, s.gtgt, color=c, lw=1.6, label=f"{s.label} Gtarget")
        _shade_runs(ax, s.t, [o["runs"] for o in opps[s.color]], c, alpha=0.14)
        rug = s.t[s.maxg]
        if rug.size:
            ax.scatter(rug, np.full(rug.size, 0.3), s=4, color=c, marker="|")
    ax.set_title("G 사용 (점선 Gavail 상한, 굵은선 실측 Nz, 가는선 Gtarget 명령, 음영 기회 후보)"
                 if has_nz else
                 "G 사용 (점선 Gavail 상한, 실선 Gtarget 명령, 음영 해당 진영 기회 후보)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("하중배수 [g]")
    ax.set_ylim(-2 if has_nz else 0, 9.5)   # 실측 Nz 는 푸시오버에서 음수 가능
    ax.legend(loc="upper right", fontsize=7, ncol=2)

    # (2) 에너지 상태: 비에너지 Es(t)
    ax = axes[0, 1]
    for s, c in pair:
        ax.plot(s.t, s.es_ft, color=c, lw=1.6, label=s.label)
    ax.set_title("비에너지 Es (높을수록 에너지 우세)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("Es = 고도 + V²/2g  [ft]")
    ax.legend(loc="upper right", fontsize=8)

    # (3) Ps 비잉여출력 + ΔEs 에너지 우세 — 에너지를 태운 구간과 회복 구간
    ax = axes[1, 0]
    ps_all = []
    for s, c in pair:
        ps = _smooth(np.gradient(s.es_ft, s.t), s.t)
        ps_all.append(ps)
        ax.plot(s.t, ps, color=c, lw=1.4, label=f"{s.label} Ps")
    ax.axhline(0, color=C_BAND, lw=0.8)
    ax.set_title("Ps 비잉여출력 (0 위=에너지 회복) / 회색 점선 ΔEs 우세")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("Ps = dEs/dt  [ft/s]")
    # 시작/종료 프레임의 gradient 경계 스파이크가 스케일을 누르지 않게 분위 기반 ylim
    ps_all = np.concatenate(ps_all)
    if np.isfinite(ps_all).any():
        ax.set_ylim(np.nanpercentile(ps_all, 0.5) - 50, np.nanpercentile(ps_all, 99.5) + 50)
    ax.legend(loc="upper left", fontsize=8)
    if blue.t.size == red.t.size:
        ax2 = ax.twinx()
        ax2.plot(blue.t, _smooth(blue.es_ft - red.es_ft, blue.t), color="#555555",
                 lw=1.2, ls="--")
        ax2.axhline(0, color="#555555", lw=0.5, alpha=0.5)
        ax2.set_ylabel("ΔEs (blue-red) [ft]", color="#555555", fontsize=8)

    # (4) 도그하우스 — 속도별 실제 선회율 vs 리미터 한계 (rate fight 성능)
    #     교리 상한(g_fraction) 점선 포함 — 상한과 실측의 간격이 백오프(YAML 조정 가능).
    ax = axes[1, 1]
    vv = np.linspace(150, 520, 200)
    g_curve = np.minimum(G_STRUCT_MAX, G_STRUCT_MAX * (vv / KCAS_CORNER_LO) ** 2)
    # 이론 선회율: ω = g·√(G²−1)/V (수평 정상선회 근사, CAS≈TAS 가정 — 저고도 근사)
    w_max = np.degrees(G_FT_S2 * np.sqrt(np.maximum(g_curve**2 - 1, 0))
                       / (vv * KT_TO_FPS))
    ax.plot(vv, w_max, "k", lw=1.4, label="이론 최대 선회율 (Gavail 한계)")
    if gf is not None:
        w_gf = np.degrees(G_FT_S2 * np.sqrt(np.maximum((gf * g_curve) ** 2 - 1, 0))
                          / (vv * KT_TO_FPS))
        ax.plot(vv, w_gf, color="#666666", lw=1.2, ls="--",
                label=f"교리 상한 (g_fraction~{gf:.2f} x Gavail)")
    ax.axvspan(KCAS_CORNER_LO, KCAS_CORNER_HI, color=C_BAND, alpha=0.15,
               label=f"코너속도 {KCAS_CORNER_LO:.0f}–{KCAS_CORNER_HI:.0f} kt")
    for s, c in pair:
        ax.scatter(s.cas, _turn_rate(s), s=5, color=c, alpha=0.2,
                   edgecolors="none", label=s.label)
    ax.set_title("도그하우스 (코너속도에서 최대 선회율을 뽑았나)")
    ax.set_xlabel("CAS [kt]"); ax.set_ylabel("선회율 [deg/s]")
    ax.set_xlim(150, 520); ax.set_ylim(0, float(np.max(w_max)) * 1.05)
    ax.legend(loc="upper right", fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_png, dpi=120)
    print(f"  그래프 저장: {out_png}")
    if show:
        plt.show()
    plt.close(fig)


# ── 그림 3: 전술 기하 (포지셔널·의사결정) ────────────────────────────────
def make_tactics_plot(sides, events, out_png, show):
    plt = _init_mpl(show)
    if plt is None:
        print("  (그래프 생략 — matplotlib 미설치: pip install matplotlib)")
        return
    blue, red = _set_labels(sides)
    pair = ((blue, C_BLUE), (red, C_RED))
    tmax = blue.t[-1]
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(f"전술 기하 ({_matchup(blue, red)})", fontsize=13)

    # (1) 평면 궤적 (god's-eye view) — 턴서클·lag/lead·원서클/투서클이 육안으로
    ax = fig.add_subplot(2, 2, 1)
    step = max(1, int(round(15.0 / max(float(np.median(np.diff(blue.t))), 1e-6))))
    for s, c in pair:
        ax.plot(s.e_ft, s.n_ft, color=c, lw=1.0, alpha=0.8, label=s.label)
        for i0, i1 in _bool_runs(s.in_wez):
            ax.plot(s.e_ft[i0:i1 + 1], s.n_ft[i0:i1 + 1], color=c, lw=3.0)
        # 시작 마커를 초기 기수 방향으로 회전 (matplotlib 은 CCW, HDG 는 CW → 부호 반전)
        hdg0 = float(s.hdg[0]) if np.isfinite(s.hdg[0]) else 0.0
        ax.plot(s.e_ft[0], s.n_ft[0], marker=(3, 0, -hdg0), color=c, ms=11)
        ax.plot(s.e_ft[::step], s.n_ft[::step], ".", color=c, ms=3)
    for et, _ in events:
        i = min(int(np.searchsorted(blue.t, et)), blue.t.size - 1)
        for s, _c in pair:
            ax.plot(s.e_ft[i], s.n_ft[i], "x", color="k", ms=7, mew=1.5)
    ax.set_title("평면 궤적 (삼각형=시작 위치·기수 방향, 점 15s 간격, 굵은선 InWEZ, ×피격)")
    ax.set_xlabel("동 [ft]"); ax.set_ylabel("북 [ft]")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="upper right", fontsize=8)

    # (2) ATA–AA 상태평면 — BFM 포지셔널 다이어그램 (밝→어두움 = 시간 진행)
    ax = fig.add_subplot(2, 2, 2)
    for s, cmap in ((blue, "Blues"), (red, "Reds")):
        ax.scatter(s.aa, s.ata, c=s.t, cmap=cmap, vmin=-0.6 * tmax, s=6,
                   alpha=0.7, edgecolors="none", label=s.label)
    for x, y, txt, ha, va in ((3, 3, "공세", "left", "bottom"),
                              (177, 177, "수세", "right", "top"),
                              (177, 3, "헤드온", "right", "bottom"),
                              (3, 177, "이탈(tail-to-tail)", "left", "top")):
        ax.text(x, y, txt, fontsize=9, color="#444444", ha=ha, va=va)
    ax.set_title("ATA–AA 상태평면 (공세로 수렴하는가; 어두울수록 나중)")
    ax.set_xlabel("AA [deg] (0=적 6시 점유)"); ax.set_ylabel("ATA [deg] (0=조준)")
    ax.set_xlim(0, 180); ax.set_ylim(0, 180)
    ax.legend(loc="center right", fontsize=8)

    # (3) RollOff vs 명령 dphi — 실선·점선 간격 = 조준 오프셋(lead/lag)의 효과
    ax = fig.add_subplot(2, 2, 3)
    for s, c in pair:
        ax.plot(s.t, s.rolloff, color=c, lw=1.2, alpha=0.9, label=f"{s.label} RollOff")
        if np.isfinite(s.dphi).any():
            ax.plot(s.t, s.dphi, color=c, lw=1.0, ls="--", alpha=0.6,
                    label=f"{s.label} dphi")
    ax.axhline(0, color=C_BAND, lw=0.8)
    ax.set_title("RollOff 순수 LOS 롤오프(실선) vs L2 명령 dphi(점선)")
    ax.set_xlabel("시간 [s]"); ax.set_ylabel("롤오프 [deg] (+우롤)")
    ax.set_ylim(-185, 185)
    ax.legend(loc="upper right", fontsize=7, ncol=2)

    # (4) L1 노드 간트 — 어떤 전술 노드에서 데미지를 주고받았나
    ax = fig.add_subplot(2, 2, 4)
    rows = [("node", n) for n in sorted({x for s, _ in pair for x in s.node[s.node != ""]})]
    rows += [("pursuit", f"추격:{p}") for p in
             sorted({x for s, _ in pair for x in s.pursuit[s.pursuit != ""]})]
    for yi, (attr, label) in enumerate(rows):
        raw = label.split(":", 1)[-1] if attr == "pursuit" else label
        for s, c, off in ((blue, C_BLUE, 0.05), (red, C_RED, -0.40)):
            spans = [(s.t[a], max(s.t[b] - s.t[a], 0.2))
                     for a, b in _bool_runs(getattr(s, attr) == raw)]
            if spans:
                ax.broken_barh(spans, (yi + off, 0.35), color=c, alpha=0.85)
    for et, _ in events:
        ax.axvline(et, color="k", lw=0.8, ls=":", alpha=0.6)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([lbl for _, lbl in rows], fontsize=8)
    ax.set_title("L1 노드·추격 점유 (행별 위=blue/아래=red, 점선 피격)")
    ax.set_xlabel("시간 [s]")
    ax.set_xlim(blue.t[0], tmax)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_png, dpi=120)
    print(f"  그래프 저장: {out_png}")
    if show:
        plt.show()
    plt.close(fig)


def summarize(sides, opps, gf) -> None:
    """콘솔 요약: WEZ 만족·근접도·데미지 + G 기회 후보 구간.

    WEZ 만족은 파일에 구워진 InWEZ 플래그(그 파일 엔진 규칙의 진실)를 쓴다 —
    현재 상수로 재계산하면 옛 파일에서 어긋난다. 거리·ATA 는 버전 무관(순수 기하).
    """
    blue, red = sides["blue"], sides["red"]
    if blue.t.size < 2:
        print("  (샘플 부족 — log_hz=0 매치이거나 파싱 실패)")
        return
    dt = float(np.median(np.diff(blue.t)))
    total_t = blue.t[-1] - blue.t[0]
    print(f"  총 교전 시간 {total_t:.1f}s  (샘플 {blue.t.size}개, dt≈{dt:.3f}s)")
    if gf is not None:
        print(f"  구조적 G 마진: 명령 G ≈ {gf:.2f}×Gavail (g_fraction 백오프 — "
              f"리미터 상주 회피). 기회 후보는 이보다 더 벌어진 구간만 센다.")

    for shooter, target in ((blue, red), (red, blue)):
        in_rng = (shooter.dist >= WEZ_MIN_FT) & (shooter.dist <= WEZ_MAX_FT)
        wez = shooter.in_wez
        frac = lambda m: 100.0 * np.count_nonzero(m) / m.size

        keys = tuple(f"<{hi:.0f}°(x{coef:.2f})" for hi, coef in WEZ_ATA_TIERS)
        tiers = dict.fromkeys(keys, 0)
        for a in shooter.ata[wez]:
            for (hi, _), name in zip(WEZ_ATA_TIERS, keys):
                if a < hi:
                    tiers[name] += 1
                    break
        tier_time = {k: v * dt for k, v in tiers.items()}
        bursts = int(np.count_nonzero(wez[1:] & ~wez[:-1]) + (1 if wez[0] else 0))
        min_dist = float(np.nanmin(shooter.dist))
        min_ata_in_rng = float(np.nanmin(shooter.ata[in_rng])) if in_rng.any() else float("nan")
        entry = shooter.t[wez]
        first_entry = f"{entry[0]:.1f}s" if entry.size else "없음"
        wez_time = np.count_nonzero(wez) * dt
        hp_dealt = float(target.hp[0] - target.hp[-1])

        print(f"\n  [{shooter.name}] 공격 지표")
        print(f"    WEZ 만족(InWEZ 플래그)   : {frac(wez):5.1f}%  ({wez_time:.1f}s)  "
              f"[참고: 사거리 충족 {frac(in_rng):.1f}%]")
        print(f"    WEZ 버스트 횟수           : {bursts},  최초 진입 {first_entry}")
        print(f"    근접도: 최소거리 {min_dist:6.0f} ft, 사거리내 최소 ATA "
              f"{min_ata_in_rng:5.1f}°")
        print(f"    ATA tier 점유[s]         : " +
              "  ".join(f"{k} {v:.1f}" for k, v in tier_time.items()))
        print(f"    가한 데미지 (상대 HP감소) : {hp_dealt:5.1f} HP")

        ops = opps[shooter.color]
        if not shooter.has_energy:
            print("    G 기회 분석: (이 파일엔 Gavail 로그 없음 — 구엔진)")
        elif not ops:
            print("    G 기회 후보: 없음 (여유 G 를 대체로 활용)")
        else:
            tot = sum(o["dur"] for o in ops)
            print(f"    G 기회 후보: {len(ops)}구간, 총 {tot:.1f}s "
                  f"(Gavail−Gtarget>{SLACK_G}, ATA>{OPP_ATA_LO:.0f}°, 코너속도↑)")
            for o in ops[:6]:
                mg = " maxG" if o["maxg"] else ""
                print(f"      {o['t0']:6.1f}–{o['t1']:5.1f}s ({o['dur']:4.1f}s) | "
                      f"평균ATA {o['ata']:4.1f}° | 여유G {o['slack']:3.1f} | "
                      f"node={o['node']}{mg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gun WEZ 교전 분석 (ACMI → 그래프+통계)")
    ap.add_argument("acmi", nargs="+", help="분석할 .acmi 파일(들)")
    ap.add_argument("--show", action="store_true", help="그래프 창도 표시")
    args = ap.parse_args()

    for path in args.acmi:
        if not os.path.isfile(path):
            print(f"[건너뜀] 파일 없음: {path}")
            continue
        print("=" * 60)
        print(f"파일: {path}")
        sides, events = parse_acmi(path)
        opps = {s.color: detect_opportunities(s) for s in sides.values()}
        gf = estimate_g_fraction(sides)
        summarize(sides, opps, gf)
        base = os.path.splitext(path)[0]
        make_wez_plot(sides, events, base + "_wez.png", args.show)
        if any(s.has_energy for s in sides.values()) or all(s.has_pos for s in sides.values()):
            make_energy_plot(sides, base + "_energy.png", args.show, opps, gf)
        else:
            print("  (에너지 그림 생략 — Gavail·위치 로그 없는 구엔진 파일)")
        if all(s.has_pos for s in sides.values()):
            make_tactics_plot(sides, events, base + "_tactics.png", args.show)
        else:
            print("  (전술 그림 생략 — 위치 샘플 부족)")
        print("=" * 60)
           
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
