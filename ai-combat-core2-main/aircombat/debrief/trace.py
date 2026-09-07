"""ACMI 시계열 파서 + 공유 plot 부트스트랩 — `scripts/analyze_wez.py` 와
`replay_debrief.plot_match_debrief` 가 공유한다(로직 정본은 여기, analyze_wez 는 import 만).

`replay_debrief.parse_acmi`(dict 기반) 와 별개다 — 그쪽은 research/*, sdk2 run_match
가 쓰는 구 포맷이라 유지한다. 이 모듈의 `Side` 는 Nz·HIT events·pursuit/maxG/dphi·
유도 에너지(Es)까지 담아 디브리프 6패널이 요구하는 필드를 전부 채운다.
"""
from __future__ import annotations

import math
import warnings

import numpy as np

from ..geometry.units import M_TO_FT, WEZ_MIN_RANGE_M, WEZ_MAX_RANGE_M
from ..control.limiter import LimiterConfig, G_FT_S2

WEZ_MIN_FT = WEZ_MIN_RANGE_M * M_TO_FT   # 500 ft
WEZ_MAX_FT = WEZ_MAX_RANGE_M * M_TO_FT   # 3,000 ft

_LIM = LimiterConfig()
G_STRUCT_MAX = _LIM.g_struct_max         # 9.0 (구조 한계)
KCAS_CORNER_LO = _LIM.kcas_corner_lo     # 330 (여기서 구조한계 G 도달)
KCAS_CORNER_HI = _LIM.kcas_corner_hi     # 440 (코너 플래토 상한)

# ned_to_lonlat(state.py) 평면근사 원점 — T= 위경도에서 NED(ft) 역복원용.
LAT0, LON0 = 37.0, 127.0
M_PER_DEG = 111320.0
MPS_TO_KT = 1.94384      # ACMI CAS 는 m/s (스펙) — 분석은 kt 기준

# 기회 후보 검출 임계 (참가자가 조정 가능한 판정선)
SLACK_G = 1.5           # Gavail − Gtarget 이 이 이상이면 "여유 있음"
OPP_ATA_LO = 5.0        # 이보다 작으면 백오프가 교리상 정상(오버슈트 방지) → 제외
OPP_ATA_HI = 90.0       # 전방 반구만
OPP_DIST_FT = 6000.0    # 교전권 (원거리 순항 제외)
OPP_CAS = KCAS_CORNER_LO  # 코너속도 이상 = 당겨도 코너 유지할 속도 이점
OPP_MIN_S = 1.0         # 이보다 짧은 구간은 플리커로 무시

# colorblind-safe 2색 (blue/red 진영) — dataviz categorical, 인쇄·CVD 구분 가능.
C_BLUE = "#1f6fb2"
C_RED = "#c1442e"
C_BAND = "#8a8a8a"   # WEZ 밴드/박스 음영 (중립 회색)

IDS = {"100": "blue", "200": "red"}


class Side:
    """한 진영의 시계열. 리스트로 모은 뒤 finalize 에서 numpy 로 굳힌다."""

    # (ACMI 키, Side 속성) — numeric 수집 대상. 없으면 nan 으로 정렬 유지(구파일 호환).
    _NUM = (("Distance", "dist"), ("ATA", "ata"), ("Health", "hp"),
            ("CAS", "cas"), ("Gtarget", "gtgt"), ("Gavail", "gavail"),
            ("Nz", "nz"), ("AA", "aa"), ("HCA", "hca"), ("RollOff", "rolloff"),
            ("ClosureRate", "clo"), ("HDG", "hdg"),
            ("_lon", "lon"), ("_lat", "lat"), ("_alt_m", "alt_m"))

    def __init__(self, color: str):
        self.color = color
        self.name = color            # CallSign 있으면 덮어씀
        self.label = color
        self.t: list = []
        self.in_wez: list = []
        self.node: list = []         # L1 활성 전술 노드명
        self.maxg: list = []         # L1 maxG 트리거 여부
        self.pursuit: list = []      # L1 추격 유형 (lead/pure/lag)
        self.dphi: list = []         # L2 명령 롤오프 [deg]
        for _, attr in self._NUM:
            setattr(self, attr, [])
        self._cur: dict = {}

    def push(self, t: float) -> None:
        """직전 프레임의 _cur 를 한 샘플로 확정. 기본 4개(Distance/ATA/Health/InWEZ)
        가 있어야 유효 프레임. 나머지는 없으면 nan/기본값으로 채워 배열 정렬 유지."""
        c = self._cur
        if {"Distance", "ATA", "Health", "InWEZ"} <= c.keys():
            if self.t and t == self.t[-1]:
                # 종료 시 같은 #t 재기록(최종 데미지 반영 프레임) — 최신으로 교체.
                # 중복 t 를 남기면 np.gradient 가 dt=0 으로 0-나눗셈 경고를 낸다.
                for lst in (self.t, self.in_wez, self.node, self.maxg,
                            self.pursuit, self.dphi,
                            *(getattr(self, attr) for _, attr in self._NUM)):
                    lst.pop()
            self.t.append(t)
            self.in_wez.append(c["InWEZ"])
            self.node.append(c.get("_node", ""))
            self.maxg.append(c.get("_maxg", False))
            self.pursuit.append(c.get("_pursuit", ""))
            self.dphi.append(c.get("_dphi", float("nan")))
            for key, attr in self._NUM:
                getattr(self, attr).append(c.get(key, float("nan")))
        self._cur = {}

    def finalize(self) -> None:
        self.t = np.asarray(self.t, float)
        self.in_wez = np.asarray(self.in_wez, dtype=bool)
        self.maxg = np.asarray(self.maxg, dtype=bool)
        self.node = np.asarray(self.node, dtype=object)
        self.pursuit = np.asarray(self.pursuit, dtype=object)
        self.dphi = np.asarray(self.dphi, float)
        for _, attr in self._NUM:
            setattr(self, attr, np.asarray(getattr(self, attr), float))
        self.alt_ft = self.alt_m * M_TO_FT
        self.slack = self.gavail - self.gtgt          # 안 쓴 G 여유
        self.has_energy = bool(np.isfinite(self.gavail).any())
        self.has_pos = bool(np.isfinite(self.lat).any()) and self.t.size >= 2
        # TAS·에너지 복원: 위경도·고도 → NED(ft) → 시간미분 속도(무풍=TAS).
        if self.has_pos:
            self.n_ft = (self.lat - LAT0) * M_PER_DEG * M_TO_FT
            self.e_ft = (self.lon - LON0) * M_PER_DEG * math.cos(math.radians(LAT0)) * M_TO_FT
            vn, ve, vu = (np.gradient(x, self.t) for x in (self.n_ft, self.e_ft, self.alt_ft))
            self.v_fps = np.sqrt(vn**2 + ve**2 + vu**2)
            self.es_ft = self.alt_ft + self.v_fps**2 / (2.0 * G_FT_S2)   # 비에너지
        else:
            self.n_ft = self.e_ft = np.full(self.t.shape, np.nan)
            self.v_fps = np.full(self.t.shape, np.nan)
            self.es_ft = np.full(self.t.shape, np.nan)


def parse_trace(path: str):
    """ACMI 텍스트 → (sides, events). events = [(t, text)] (HIT 등 북마크)."""
    sides = {"blue": Side("blue"), "red": Side("red")}
    events: list = []
    t = 0.0
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("FileType") or line.startswith("FileVersion"):
                continue
            if line.startswith("#"):
                for s in sides.values():
                    s.push(t)
                t = float(line[1:])
                continue
            if line.startswith("0,"):
                if line.startswith("0,Event="):
                    events.append((t, line.split("|", 1)[-1]))   # "HIT A→B HP x"
                continue
            oid, _, rest = line.partition(",")
            s = sides.get(IDS.get(oid, ""))
            if s is None:
                continue
            for field in rest.split(","):
                k, _, v = field.partition("=")
                if k == "CallSign":
                    s.name = v
                elif k == "InWEZ":
                    s._cur["InWEZ"] = (v == "True")
                elif k == "T":                    # lon|lat|alt_m|roll|pitch|yaw
                    p = v.split("|")
                    if len(p) >= 3 and p[0] and p[1] and p[2]:
                        s._cur["_lon"], s._cur["_lat"], s._cur["_alt_m"] = (
                            float(p[0]), float(p[1]), float(p[2]))
                elif k == "L1":                   # "node=... pursuit=... maxG=0/1"
                    for tok in v.split():
                        kk, _, vv = tok.partition("=")
                        if kk == "node":
                            s._cur["_node"] = vv
                        elif kk == "pursuit":
                            s._cur["_pursuit"] = vv
                        elif kk == "maxG":
                            s._cur["_maxg"] = (vv == "1")
                elif k == "L2":                   # "mode=... dphi=... lead=... lag=..."
                    for tok in v.split():
                        kk, _, vv = tok.partition("=")
                        if kk == "dphi":
                            s._cur["_dphi"] = float(vv)
                elif k in ("Distance", "ATA", "Health", "CAS", "Gtarget", "Gavail",
                           "Nz", "AA", "HCA", "RollOff", "ClosureRate", "HDG"):
                    s._cur[k] = float(v) * (MPS_TO_KT if k == "CAS" else 1.0)
    for s in sides.values():
        s.push(t)
        s.finalize()
    return sides, events


# 한글 라벨용 폰트 후보 — 앞에서부터 설치된 것을 쓴다.
#   로컬(Windows) = Malgun Gothic
#   EC2 워커      = NanumGothic          (server/Dockerfile 의 fonts-nanum)
#   Lambda        = Noto Sans CJK        (server/Dockerfile.lambda 의 google-noto-sans-cjk-fonts)
# .ttc 컬렉션은 matplotlib 이 첫 face 만 등록하므로 KR/JP 를 모두 적는다(글리프는 공유).
_FONT_CANDIDATES = ["Malgun Gothic", "NanumGothic", "NanumBarunGothic",
                    "Noto Sans CJK KR", "Noto Sans CJK JP", "Noto Sans KR"]


def _has_hangul(path):
    """이 폰트 파일에 한글 글리프가 있는가."""
    try:
        from matplotlib.ft2font import FT2Font
        return FT2Font(path).get_char_index(ord("한")) != 0
    except Exception:
        return False


def korean_family():
    """실제로 한글이 찍히는 폰트 이름 (없으면 None).

    **이름 목록만 믿지 않는다.** Lambda 이미지에는 Noto CJK 가 깔려 있었는데
    후보 목록에 그 이름이 없어서 DejaVu 로 떨어졌고, 디브리프 PNG 의 한글이
    전부 두부(□)로 나갔다(2026-08). 후보를 우선 보되 하나도 안 맞으면 설치
    폰트를 훑어 글리프 보유로 고른다 — 배포판이 폰트를 바꿔도 안 깨진다.
    """
    from matplotlib import font_manager as fm
    for name in _FONT_CANDIDATES:
        try:
            path = fm.findfont(name, fallback_to_default=False)
        except Exception:
            continue
        if _has_hangul(path):
            return name
    for f in fm.fontManager.ttflist:            # 후보 밖 — 글리프로 직접 찾는다
        if _has_hangul(f.fname):
            return f.name
    return None


def init_mpl(show=False):
    """matplotlib 부트스트랩 → pyplot (미설치면 None). Agg 고정은 show=False 일 때만."""
    try:
        import matplotlib
    except ModuleNotFoundError:
        return None
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fam = korean_family()
    if fam is None:
        warnings.warn("한글 폰트가 없다 — 디브리프 라벨이 두부(□)로 렌더된다. "
                      "Windows=Malgun Gothic, Linux=fonts-nanum 또는 Noto CJK 설치")
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ([fam] if fam else []) + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────
def bool_runs(mask: np.ndarray):
    """mask=True 연속 구간을 (i0, i1_inclusive) 리스트로."""
    runs = []
    i = 0
    n = mask.size
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def shade_runs(ax, t, runs, color, alpha=0.15, label=None):
    for k, (i0, i1) in enumerate(runs):
        ax.axvspan(t[i0], t[i1], color=color, alpha=alpha, lw=0,
                   label=(label if k == 0 else None))


def mask_to_runs(t, mask, min_s):
    """min_s 이상 지속하는 구간만."""
    return [(a, b) for a, b in bool_runs(mask) if t[b] - t[a] >= min_s]


def smooth(y, t, win_s=1.0):
    """~win_s 이동평균 (미분 노이즈 억제)."""
    n = int(round(win_s / max(float(np.median(np.diff(t))), 1e-6))) if t.size >= 3 else 1
    if n <= 1:
        return y
    return np.convolve(y, np.ones(n) / n, mode="same")


def turn_rate(s: Side):
    """HDG 시간미분 → 실제 선회율 [deg/s] (HDG 로그 없는 구파일은 nan)."""
    if not np.isfinite(s.hdg).all() or s.t.size < 3:
        return np.full(s.t.shape, np.nan)
    w = np.degrees(np.gradient(np.unwrap(np.radians(s.hdg)), s.t))
    return np.abs(smooth(w, s.t))


def detect_opportunities(s: Side):
    """G 여유가 있는데 ATA 가 남은 '더 당길 수 있었던' 후보 구간."""
    if not s.has_energy:
        return []
    mask = ((s.slack > SLACK_G) & (s.ata > OPP_ATA_LO) & (s.ata < OPP_ATA_HI)
            & (s.dist < OPP_DIST_FT) & (s.cas >= OPP_CAS))
    mask = np.nan_to_num(mask, nan=0.0).astype(bool)
    out = []
    for i0, i1 in mask_to_runs(s.t, mask, OPP_MIN_S):
        sl = slice(i0, i1 + 1)
        nodes = s.node[sl]
        node = max(set(nodes), key=list(nodes).count) if len(nodes) else ""
        out.append({
            "t0": s.t[i0], "t1": s.t[i1], "dur": s.t[i1] - s.t[i0],
            "ata": float(np.nanmean(s.ata[sl])), "slack": float(np.nanmean(s.slack[sl])),
            "node": node, "maxg": bool(s.maxg[sl].any()), "runs": (i0, i1),
        })
    return out


def estimate_g_fraction(sides):
    """명령 G / 가용 G 상한 비의 상위 분위 = 교리 g_fraction 근사 (없으면 None).

    교전(ATA>임계) 프레임에서 Gtarget/Gavail 은 대개 g_fraction 에 붙어 있다
    (리미터 상주 회피). g_burst 가 높은 프레임만 1.0 까지 오르므로 p90 로 추정한다.
    """
    r = []
    for s in sides.values():
        if not s.has_energy:
            continue
        ok = np.isfinite(s.gavail) & (s.gavail > 0.5) & (s.ata > OPP_ATA_LO)
        r.append(s.gtgt[ok] / s.gavail[ok])
    if not r:
        return None
    return float(np.nanpercentile(np.concatenate(r), 90))


def set_labels(sides):
    """(blue, red) 반환 + 동명이인(자가대전)일 때 진영 접미사로 구분."""
    blue, red = sides["blue"], sides["red"]
    if blue.name == red.name:
        blue.label, red.label = f"{blue.name} (Blue)", f"{red.name} (Red)"
    else:
        blue.label, red.label = blue.name, red.name
    return blue, red


def matchup(blue, red) -> str:
    """suptitle 용 대진 문자열 (괄호 중첩 없이)."""
    if blue.name == red.name:
        return f"Blue {blue.name} vs Red {red.name}"
    return f"{blue.name} vs {red.name}"
