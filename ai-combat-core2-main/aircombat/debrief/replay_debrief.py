"""L5 ACMI 디브리프·plot — 사후 replay 분석(관찰 전용, 제어경로 위험 0).

`acmi.py`(ACMI writer)가 기록한 풍부한 상태(roll/pitch/yaw·CAS·InWEZ·Gtarget/Gavail·
L1/L2/L3 결정문자열)를 되읽어 **판정 인과연쇄를 시각화**한다. core-live
scripts/{analyze,visualize}_acmi.py(lon/lat/alt+AA/ATA/HCA만) 이식·확장.

`auto_debrief(acmi_path)` 는 `Match.run()` 끝에서 무조건 호출된다 — 교전(ACMI 생성)마다
{stem}_debrief.png(`plot_match_debrief` 8패널) 자동 산출. 웹 워커(bridge)·로컬
run_match 가 같은 훅을 타므로 두 경로의 그림은 항상 동일하다. 완전 가드(예외·
matplotlib 부재는 조용히 무시, 매치 결과 불변).

`plot_debrief`(구 6패널·dict 파서)는 research 의 A/B 통제비교 전용으로 남는다.
CLI 는 `python -m aircombat.debrief.replay_debrief REPLAY.acmi [--compare WIN.acmi]`.
"""
from __future__ import annotations

import argparse
import io
import math
import os

import numpy as np

from ..geometry.units import M_TO_FT, WEZ_ATA_TIERS, HARD_DECK_M

HARD_DECK_FT = HARD_DECK_M * M_TO_FT     # 1,000 ft — 이하 체류는 최우선 판정패
FT_TO_M = 0.3048
LON0, LAT0 = 127.0, 37.0
# 정책 파일럿(측정 러너)의 챔프 name. 일반 매치엔 없으면 Blue(100)를 focus 로.
# (ACMI Name=F-16 고정 이후 라벨은 CallSign 에 있음 — parse_acmi 가 CallSign 을
#  name 으로 승격하므로 여기엔 파일럿 라벨을 나열한다.)
FOCUS_NAMES = {"FloorRec", "Champion", "LedgerGate", "Transcribed"}

_NUM_KEYS = ("HDG", "CAS", "Distance", "ATA", "AA", "HCA", "TAU", "ClosureRate",
             "Health", "Gtarget", "Gavail", "Throttle")


def _lonlat_to_ne_ft(lon, lat):
    n = (lat - LAT0) * 111320.0 / FT_TO_M
    e = (lon - LON0) * 111320.0 * math.cos(math.radians(LAT0)) / FT_TO_M
    return n, e


def _blank():
    d = {k: [] for k in ("t", "n", "e", "alt", "roll", "pitch", "yaw",
                         "InWEZ", "node", "mode", *_NUM_KEYS)}
    d["name"] = ""; d["color"] = ""
    return d


def parse_acmi(filepath):
    """core2 ACMI 파싱 → {oid: {series..., name, color}}. oid=100(Blue)/200(Red)."""
    obj = {100: _blank(), 200: _blank()}
    cur = {100: {}, 200: {}}
    t = 0.0

    def flush():
        for oid in (100, 200):
            if "T" not in cur[oid]:
                continue
            d = obj[oid]
            lon, lat, alt_m, roll, pitch, yaw = cur[oid]["T"]
            n_ft, e_ft = _lonlat_to_ne_ft(lon, lat)
            d["t"].append(t)
            d["n"].append(n_ft); d["e"].append(e_ft); d["alt"].append(alt_m / FT_TO_M)
            d["roll"].append(roll); d["pitch"].append(pitch); d["yaw"].append(yaw)
            for k in _NUM_KEYS:
                d[k].append(cur[oid].get(k, np.nan))
            d["InWEZ"].append(1.0 if cur[oid].get("InWEZ") == "True" else 0.0)
            d["node"].append(cur[oid].get("node", ""))
            d["mode"].append(cur[oid].get("mode", ""))

    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                flush()
                t = float(line[1:])
                cur = {100: {}, 200: {}}
                continue
            head, _, rest = line.partition(",")
            if head not in ("100", "200") or not rest:
                continue
            oid = int(head)
            for attr in rest.split(","):
                key, _, val = attr.partition("=")
                if key == "T":
                    c = val.split("|")
                    cur[oid]["T"] = [float(c[0]), float(c[1]), float(c[2]),
                                     float(c[3]), float(c[4]), float(c[5])]
                elif key == "Name" and not obj[oid]["name"]:
                    obj[oid]["name"] = val           # 기체명(F-16) — CallSign 없을 때 fallback
                elif key == "Color":
                    obj[oid]["color"] = val
                elif key == "CallSign":
                    obj[oid]["name"] = val           # 파일럿 라벨이 정체성(focus 판별) 우선
                elif key in _NUM_KEYS:
                    try:
                        cur[oid][key] = float(val)
                    except ValueError:
                        pass
                elif key == "InWEZ":
                    cur[oid]["InWEZ"] = val
                elif key in ("L1", "L2"):
                    for tok in val.split():
                        kk, _, vv = tok.partition("=")
                        if kk == "node":
                            cur[oid]["node"] = vv
                        elif kk == "mode":
                            cur[oid]["mode"] = vv
        flush()

    for oid in (100, 200):
        d = obj[oid]
        for k in ("t", "n", "e", "alt", "roll", "pitch", "yaw", "InWEZ", *_NUM_KEYS):
            d[k] = np.asarray(d[k], float)
    return obj


def _focus_oid(obj):
    """focus 객체 id(정책 챔프 name 우선, 없으면 Blue 100)."""
    for oid in (100, 200):
        if obj[oid]["name"] in FOCUS_NAMES:
            return oid
    return 100


def debrief_summary(obj, title=""):
    """저에너지 취약창 진단지표 텍스트(focus 관점: 첫머지·재획득 WEZ·조준·에너지·HP)."""
    c = _focus_oid(obj)
    o = 200 if c == 100 else 100
    C, O = obj[c], obj[o]
    t = C["t"]
    if len(t) == 0:
        print(f"[{title}] 빈 트레이스"); return
    hp_c, hp_o = C["Health"], O["Health"]
    print(f"\n{'=' * 72}\n  디브리프: {title or ''}")
    print(f"  focus={C['name']}({C['color']}, id{c})  vs  적={O['name']}({O['color']}, id{o})")
    print(f"{'=' * 72}")
    print(f"  프레임 {len(t)}  |  길이 {t[-1]:.1f}s  |  최종 HP  focus {hp_c[-1]:.1f} : 적 {hp_o[-1]:.1f}"
          f"  (Δ{hp_c[-1] - hp_o[-1]:+.1f})")

    dmg_o = np.where(np.diff(hp_o) < -1e-6)[0]
    fm_end = None
    if len(dmg_o):
        i0 = dmg_o[0]
        print(f"\n  [첫머지] 적 첫 피탄 t={t[i0 + 1]:.1f}s  적 총피해 {hp_o[0] - hp_o[-1]:.1f}"
              f"  (마지막 피탄 t={t[dmg_o[-1] + 1]:.1f}s)")
        gaps = np.where(np.diff(dmg_o) > 30)[0]
        fm_end_idx = dmg_o[gaps[0]] if len(gaps) else dmg_o[-1]
        fm_end = t[fm_end_idx + 1]
        print(f"           첫머지 종료≈t={fm_end:.1f}s  (그때 적HP {hp_o[fm_end_idx + 1]:.1f})")
    else:
        print("\n  [첫머지] 적 무피탄")

    wez = C["InWEZ"]
    print(f"\n  [WEZ 점유] focus 전체 {100 * wez.mean():.1f}%", end="")
    if fm_end is not None and (t > fm_end).any():
        print(f"  |  첫머지後 {100 * wez[t > fm_end].mean():.1f}%  ← 재획득(0%면 저에너지 취약창 basin)")
    else:
        print()
    print(f"  [WEZ 점유] 적    전체 {100 * O['InWEZ'].mean():.1f}%")

    ata = C["ATA"]; rng = C["Distance"]; close = rng < 3000
    print(f"\n  [조준] focus 평균 ATA 전체 {np.nanmean(ata):.1f}°", end="")
    if fm_end is not None and (t > fm_end).any():
        print(f"  |  첫머지後 {np.nanmean(ata[t > fm_end]):.1f}°", end="")
    print(f"  |  근접(<3000ft) {np.nanmean(ata[close]):.1f}°" if close.any() else "")

    print(f"\n  [에너지] focus alt {C['alt'].min():.0f}→{C['alt'].max():.0f}ft "
          f"(Δ{C['alt'].max() - C['alt'].min():.0f})  "
          f"CAS {np.nanmin(C['CAS']):.0f}~{np.nanmax(C['CAS']):.0f}kt")
    imin = int(np.nanargmin(C["CAS"]))
    print(f"           최저 CAS {C['CAS'][imin]:.0f}kt @ t={t[imin]:.1f}s, alt {C['alt'][imin]:.0f}ft"
          f"  (저에너지 perch 정점)")

    nodes = [n for n in C["node"] if n]
    if nodes:
        from collections import Counter
        top = Counter(nodes).most_common(4)
        print(f"\n  [전술] focus node 점유: " +
              "  ".join(f"{k} {100 * v / len(nodes):.0f}%" for k, v in top))
    print(f"{'=' * 72}")


def _panels(axes, obj, suffix=""):
    ax_traj, ax_alt, ax_cas, ax_ata, ax_hp, ax_g = axes
    c = _focus_oid(obj); o = 200 if c == 100 else 100
    C, O = obj[c], obj[o]
    t = C["t"]; cc, oc = "tab:blue", "tab:red"
    ax_traj.plot(C["e"], C["n"], color=cc, lw=1.5, alpha=.8, label=f"focus {C['name']}{suffix}")
    ax_traj.plot(O["e"], O["n"], color=oc, lw=1.5, alpha=.8, label=f"opp {O['name']}{suffix}")
    for D, col in ((C, cc), (O, oc)):
        ax_traj.scatter(D["e"][0], D["n"][0], c=col, marker="o", s=40)
        ax_traj.scatter(D["e"][-1], D["n"][-1], c=col, marker="x", s=60)
    ax_alt.plot(t, C["alt"], color=cc, lw=1.5, label=f"focus{suffix}")
    ax_alt.plot(O["t"], O["alt"], color=oc, lw=1.2, alpha=.7, label=f"opp{suffix}")
    ax_cas.plot(t, C["CAS"], color=cc, lw=1.5, label=f"focus{suffix}")
    ax_cas.plot(O["t"], O["CAS"], color=oc, lw=1.2, alpha=.7, label=f"opp{suffix}")
    ax_ata.plot(t, C["ATA"], color=cc, lw=1.5, label=f"focus ATA{suffix}")
    ax_ata.plot(O["t"], O["ATA"], color=oc, lw=1.0, alpha=.6, label=f"opp ATA{suffix}")
    ax_ata.fill_between(t, 0, 180, where=C["InWEZ"] > 0.5, color=cc, alpha=.12,
                        step="mid", label=f"focus InWEZ{suffix}")
    ax_hp.plot(t, C["Health"], color=cc, lw=1.5, label=f"focus{suffix}")
    ax_hp.plot(O["t"], O["Health"], color=oc, lw=1.2, alpha=.7, label=f"opp{suffix}")
    ax_g.plot(t, C["Gtarget"], color=cc, lw=1.2, label=f"Gtarget{suffix}")
    ax_g.plot(t, C["Gavail"], color="gray", lw=1.0, ls=":", alpha=.7, label=f"Gavail{suffix}")


def _save(fig, out, **kw):
    """디브리프 PNG 저장 — 두 plot 함수의 유일한 저장 경로.

    저장 후 256색 팔레트로 다시 쓴다(실측 1,065 KB → 368 KB). 디브리프는 선 플롯이라
    쓰는 색이 몇 안 되고, 팔레트 변환은 육안으로 구분되지 않는다. 리플레이 스토리지에서
    PNG 가 ACMI 와 맞먹는 용량을 차지하던 것을 여기서 줄인다.

    Pillow 는 matplotlib 전이 의존성(Requires-Dist: pillow>=9)이라 따로 깔 것이 없다.
    실패하거나 오히려 커지면 원본을 그대로 둔다 — 디브리프는 관찰 전용이라 여기서
    매치를 깨선 안 된다.
    """
    fig.savefig(out, dpi=130, **kw)
    try:
        from PIL import Image
        with Image.open(out) as im:
            packed = im.convert("RGB").quantize(colors=256)
        buf = io.BytesIO()
        packed.save(buf, format="PNG", optimize=True)
        if buf.tell() < os.path.getsize(out):
            with open(out, "wb") as f:
                f.write(buf.getvalue())
    except Exception:
        pass


def plot_debrief(obj, out, obj2=None, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axg = plt.subplots(2, 3, figsize=(18, 10))
    axes = (axg[0][0], axg[0][1], axg[0][2], axg[1][0], axg[1][1], axg[1][2])
    _panels(axes, obj, suffix=" (A)" if obj2 else "")
    if obj2 is not None:
        c2 = _focus_oid(obj2); o2 = 200 if c2 == 100 else 100
        C2, O2 = obj2[c2], obj2[o2]
        axes[1].plot(C2["t"], C2["alt"], color="tab:blue", lw=1.2, ls="--", label="focus (B)")
        axes[2].plot(C2["t"], C2["CAS"], color="tab:blue", lw=1.2, ls="--", label="focus (B)")
        axes[3].plot(C2["t"], C2["ATA"], color="tab:blue", lw=1.2, ls="--", label="focus ATA (B)")
        axes[4].plot(C2["t"], C2["Health"], color="tab:blue", lw=1.2, ls="--", label="focus (B)")
        axes[4].plot(O2["t"], O2["Health"], color="tab:red", lw=1.0, ls="--", alpha=.6, label="opp (B)")
        axes[5].plot(C2["t"], C2["Gtarget"], color="tab:blue", lw=1.0, ls="--", label="Gtarget (B)")

    ax_traj, ax_alt, ax_cas, ax_ata, ax_hp, ax_g = axes
    ax_traj.set_title("Top view (N-E, ft)"); ax_traj.set_xlabel("East ft"); ax_traj.set_ylabel("North ft")
    ax_traj.axis("equal"); ax_traj.legend(fontsize=7); ax_traj.grid(alpha=.3)
    ax_alt.set_title("Altitude"); ax_alt.set_xlabel("t (s)"); ax_alt.set_ylabel("ft")
    ax_alt.legend(fontsize=7); ax_alt.grid(alpha=.3)
    ax_cas.set_title("CAS (energy=speed)"); ax_cas.set_xlabel("t (s)"); ax_cas.set_ylabel("kt")
    ax_cas.legend(fontsize=7); ax_cas.grid(alpha=.3)
    ax_ata.set_title("ATA (aim) + focus InWEZ shade"); ax_ata.set_xlabel("t (s)")
    ax_ata.set_ylabel("deg"); ax_ata.set_ylim(0, 180)
    ax_ata.axhline(30, color="g", ls=":", alpha=.5); ax_ata.legend(fontsize=7); ax_ata.grid(alpha=.3)
    ax_hp.set_title("Health"); ax_hp.set_xlabel("t (s)"); ax_hp.set_ylabel("HP")
    ax_hp.legend(fontsize=7); ax_hp.grid(alpha=.3)
    ax_g.set_title("focus G (target vs avail)"); ax_g.set_xlabel("t (s)"); ax_g.set_ylabel("G")
    ax_g.legend(fontsize=7); ax_g.grid(alpha=.3)
    fig.suptitle(title or os.path.basename(out), fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    _save(fig, out, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_match_debrief(acmi_path, out):
    """매치 디브리프 8패널(2×4) — 웹 매치 상세·로컬 run_match 공용(동일 산출물).

    패널 선정 기준: ① 다른 패널에서 유도 불가 ② 승부를 가르는 규칙과 직결
    ③ 참가자가 BT YAML 을 고칠 때 행동으로 이어짐. 여기 없는 패널(도그하우스·
    ATA-AA 상태평면·Es/Ps·접근율 위상·RollOff)은 `scripts/analyze_wez.py --analyze`
    상위집합으로 로컬에만 남긴다. 그림 안 문자는 전부 영어(참가자 배포물).
    """
    from .trace import (parse_trace, set_labels, matchup, init_mpl, bool_runs,
                        shade_runs, detect_opportunities,
                        C_BLUE, C_RED, C_BAND, WEZ_MIN_FT, WEZ_MAX_FT,
                        KCAS_CORNER_LO, KCAS_CORNER_HI)

    plt = init_mpl()
    if plt is None:
        return None
    sides, events = parse_trace(acmi_path)
    blue, red = set_labels(sides)
    if blue.t.size < 2:
        return None      # log_hz=0 매치 등 — 그릴 게 없다
    pair = ((blue, C_BLUE), (red, C_RED))
    tmax = blue.t[-1]

    fig, axg = plt.subplots(2, 4, figsize=(24, 10))
    fig.suptitle(f"Match Debrief ({matchup(blue, red)})", fontsize=14, fontweight="bold")

    # (1) 평면 궤적 — 1/2-circle·오버슈트가 육안으로. 나머지 패널의 해석 앵커.
    ax = axg[0][0]
    step = max(1, int(round(15.0 / max(float(np.median(np.diff(blue.t))), 1e-6))))
    for s, c in pair:
        ax.plot(s.e_ft, s.n_ft, color=c, lw=1.0, alpha=0.8, label=s.label)
        for i0, i1 in bool_runs(s.in_wez):
            ax.plot(s.e_ft[i0:i1 + 1], s.n_ft[i0:i1 + 1], color=c, lw=3.0)
        # 시작 마커를 초기 기수 방향으로 회전 (matplotlib 은 CCW, HDG 는 CW → 부호 반전)
        hdg0 = float(s.hdg[0]) if np.isfinite(s.hdg[0]) else 0.0
        ax.plot(s.e_ft[0], s.n_ft[0], marker=(3, 0, -hdg0), color=c, ms=11)
        ax.plot(s.e_ft[::step], s.n_ft[::step], ".", color=c, ms=3)
    for et, _ in events:
        i = min(int(np.searchsorted(blue.t, et)), blue.t.size - 1)
        for s, _c in pair:
            ax.plot(s.e_ft[i], s.n_ft[i], "x", color="k", ms=7, mew=1.5)
    ax.set_title("Top view (triangle = start/heading, dots = 15 s, bold = InWEZ, x = hit)")
    ax.set_xlabel("East [ft]"); ax.set_ylabel("North [ft]")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="upper right", fontsize=8)

    # (2) 고도 — 하드덱은 최우선 판정(패자 HP 0). 바닥 압박이 지배적 승리 경로다.
    ax = axg[0][1]
    ax.axhspan(0, HARD_DECK_FT, color=C_RED, alpha=0.10)
    ax.axhline(HARD_DECK_FT, color=C_RED, lw=1.3, ls="--",
               label=f"Hard deck {HARD_DECK_FT:.0f} ft (below = loss)")
    for s, c in pair:
        ax.plot(s.t, s.alt_ft, color=c, lw=1.5, label=s.label)
    ax.set_title("Altitude (hard deck margin)")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Altitude [ft]")
    ax.set_ylim(0, None)
    ax.legend(loc="upper right", fontsize=8)

    # (3) 거리 — 사격 조건의 절반. ATA 가 좋아도 사거리 밖이면 총이 안 나간다.
    ax = axg[0][2]
    ax.axhspan(WEZ_MIN_FT, WEZ_MAX_FT, color=C_BAND, alpha=0.18,
               label=f"WEZ range {WEZ_MIN_FT:.0f}-{WEZ_MAX_FT:.0f} ft")
    ax.plot(blue.t, blue.dist, color=C_BLUE, lw=1.5)   # 거리는 상호적 — 한 선
    ax.set_title("Range between aircraft")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Range [ft]")
    ax.set_ylim(0, min(np.nanmax(blue.dist) if blue.dist.size else 1e4, 12000))
    ax.legend(loc="upper right", fontsize=8)

    # (4) ATA — 사격 조건의 나머지 절반. 양측 동시라 누가 먼저 겨눴는지 보인다.
    ax = axg[0][3]
    for s, c in pair:
        ax.plot(s.t, s.ata, color=c, lw=1.5, label=s.label)
        shade_runs(ax, s.t, bool_runs(s.in_wez), c)
    for boundary, _ in WEZ_ATA_TIERS:
        ax.axhline(boundary, color=C_BAND, lw=0.7, ls="--")
    ax.set_title("ATA aim error (shade = InWEZ, dashed = damage tiers)")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("ATA [deg]")
    ax.set_ylim(0, 135)
    ax.legend(loc="upper right", fontsize=8)

    # (5) HP — 승패 그 자체. 피격 시각(점선)과 겹쳐 보면 어느 교환에서 벌어졌는지 보인다.
    ax = axg[1][0]
    for s, c in pair:
        ax.plot(s.t, s.hp, color=c, lw=1.6, label=s.label)
    for et, _ in events:
        ax.axvline(et, color="k", lw=0.8, ls=":", alpha=0.5)
    ax.set_title("Health (dotted = hit events)")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("HP")
    ax.set_ylim(0, 102)
    ax.legend(loc="lower left", fontsize=8)

    # (6) CAS — 속도 = 에너지 잔고. 코너속도 밴드 이탈(저에너지 perch)이 패배
    #     원인일 때가 많아 참가자 가치가 높다.
    ax = axg[1][1]
    ax.axhspan(KCAS_CORNER_LO, KCAS_CORNER_HI, color=C_BAND, alpha=0.15,
               label=f"Corner speed {KCAS_CORNER_LO:.0f}-{KCAS_CORNER_HI:.0f} kt")
    for s, c in pair:
        ax.plot(s.t, s.cas, color=c, lw=1.5, label=s.label)
    ax.set_title("CAS (energy = speed, band = corner speed)")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("CAS [kt]")
    ax.set_ylim(0, None)
    ax.legend(loc="upper right", fontsize=8)

    # (7) G 사용 — 상한(Gavail) 대비 실제로 얼마나 당겼나(Nz). 음영이 "더 당길 수
    #     있었던" 구간을 자동 지목한다. Gtarget(명령)·maxG 러그는 상시 포화라
    #     정보량 대비 화면만 먹어 뺐다 — 명령 대 실측 갭은 --analyze 의 energy 패널에.
    ax = axg[1][2]
    opps = {s.color: detect_opportunities(s) for s in sides.values()}
    has_nz = any(np.isfinite(s.nz).any() for s, _ in pair)
    for s, c in pair:
        ax.plot(s.t, s.gavail, color=c, lw=1.0, ls="--", alpha=0.7,
                label=f"{s.label} Gavail limit")
        ax.plot(s.t, s.nz if has_nz else s.gtgt, color=c, lw=1.6,
                label=f"{s.label} {'Nz measured' if has_nz else 'Gtarget cmd'}")
        shade_runs(ax, s.t, [o["runs"] for o in opps[s.color]], c, alpha=0.14)
    ax.set_title("G usage (dashed = Gavail limit, shade = unused margin)")
    ax.set_xlabel("Time [s]"); ax.set_ylabel("Load factor [g]")
    ax.set_ylim(-2 if has_nz else 0, 9.5)   # 실측 Nz 는 푸시오버에서 음수 가능
    ax.legend(loc="upper right", fontsize=7, ncol=2)

    # (8) L1 노드 간트 — 내가 쓴 트리의 어느 노드가 언제 돌았고 그때 맞았나.
    ax = axg[1][3]
    rows = [("node", n) for n in sorted({x for s, _ in pair for x in s.node[s.node != ""]})]
    rows += [("pursuit", f"pursuit:{p}") for p in
             sorted({x for s, _ in pair for x in s.pursuit[s.pursuit != ""]})]
    for yi, (attr, label) in enumerate(rows):
        raw = label.split(":", 1)[-1] if attr == "pursuit" else label
        for s, c, off in ((blue, C_BLUE, 0.05), (red, C_RED, -0.40)):
            spans = [(s.t[a], max(s.t[b] - s.t[a], 0.2))
                     for a, b in bool_runs(getattr(s, attr) == raw)]
            if spans:
                ax.broken_barh(spans, (yi + off, 0.35), color=c, alpha=0.85)
    for et, _ in events:
        ax.axvline(et, color="k", lw=0.8, ls=":", alpha=0.6)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([lbl for _, lbl in rows], fontsize=8)
    ax.set_title("L1 node / pursuit occupancy (upper = Blue, lower = Red, dotted = hit)")
    ax.set_xlabel("Time [s]")
    ax.set_xlim(blue.t[0], tmax)

    fig.tight_layout(rect=(0, 0, 1, 0.97))
    _save(fig, out)
    plt.close(fig)
    return out


def auto_debrief(acmi_path, *, plot=True, summary=False, quiet=False):
    """Match.run() 종료 훅 — 교전마다 무조건 호출. 완전 가드(매치 결과 불변).

    env CORE2_AUTO_DEBRIEF=0 이면 비활성. plot=True 면 {stem}_debrief.png 산출.
    """
    if os.environ.get("CORE2_AUTO_DEBRIEF", "1") == "0":
        return None
    if not acmi_path or not os.path.isfile(acmi_path):
        return None
    try:
        if summary:
            debrief_summary(parse_acmi(acmi_path), title=os.path.basename(acmi_path))
        out = None
        if plot:
            out = os.path.splitext(acmi_path)[0] + "_debrief.png"
            out = plot_match_debrief(acmi_path, out)
            if out and not quiet:
                print(f"  debrief   : {out}")
        return out
    except Exception as e:   # 디브리프 실패가 매치를 깨선 안 됨(관찰 전용)
        if not quiet:
            print(f"  [debrief 경고] {type(e).__name__}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser(description="core2 ACMI 디브리프·plot")
    ap.add_argument("acmi")
    ap.add_argument("--compare", default=None, help="비교 ACMI(패 vs 승 통제비교)")
    ap.add_argument("--out", "-o", default=None)
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()
    obj = parse_acmi(args.acmi)
    debrief_summary(obj, title=os.path.basename(args.acmi))
    obj2 = None
    if args.compare:
        obj2 = parse_acmi(args.compare)
        debrief_summary(obj2, title=os.path.basename(args.compare))
    if args.no_plot:
        return 0
    out = args.out or os.path.splitext(args.acmi)[0] + ("_compare.png" if obj2 else "_debrief.png")
    ttl = os.path.basename(args.acmi) + (f"  vs  {os.path.basename(args.compare)}" if obj2 else "")
    print(f"  plot 저장: {plot_debrief(obj, out, obj2=obj2, title=ttl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
