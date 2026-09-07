"""L5 ACMI writer — 사후 .acmi (Tacview 2.x 텍스트).

L4 상태를 읽기만 하는 관찰 레이어(D5, 제어경로 위험 0). 속성 키명은 V1 규약을
따라 tacview-addons(Lua Health Bar / Control Position 등)와 호환된다.

좌표: T=경도|위도|고도(m)|Roll|Pitch|Yaw. JSBSim position/long-gc-deg,
lat-geod-deg, h-sl-meters, attitude/phi|theta|psi-deg 를 그대로 넣는다(부록 A).
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field


@dataclass
class ACMIObject:
    id: int                         # 객체 ID (예: 아군 100, 적 200)
    lon: float                      # 경도 [deg]
    lat: float                      # 위도 [deg]
    alt_m: float                    # 고도 [m]
    roll_deg: float
    pitch_deg: float
    yaw_deg: float
    name: str = "F-16"
    color: str = "Blue"             # Tacview 표준: Blue/Red
    type: str = "Air+FixedWing"
    coalition: str = "Allies"       # tacview-addons 팀 구분 (Allies/Enemies)
    callsign: str = ""              # blue_1 / red_1
    attrs: dict = field(default_factory=dict)   # 동적 속성(비행·조종·전투·전술)


KTS_TO_MPS = 0.514444    # ACMI 스펙: CAS 단위는 m/s — kts 로 쓰면 Tacview 가 ×1.944 부풀려 표시


def flight_attrs(hdg_deg, cas_kts) -> dict:
    """비행 상태 — HDG(deg), CAS(입력 kts → 기록 m/s). 애드온이 숫자로 소비."""
    return {"HDG": f"{hdg_deg:.2f}", "CAS": f"{cas_kts * KTS_TO_MPS:.2f}"}


def control_attrs(throttle, ail_cmd, elev_cmd, rud_cmd,
                  ail_pos, elev_pos, rud_pos) -> dict:
    """조종입력 + 서보 실제위치 (Control Position 애드온 호환)."""
    return {
        "Throttle": f"{throttle:.3f}",
        "RollControlInput": f"{ail_cmd:.3f}",
        "PitchControlInput": f"{elev_cmd:.3f}",
        "YawControlInput": f"{rud_cmd:.3f}",
        "RollControlPosition": f"{ail_pos:.4f}",
        "PitchControlPosition": f"{elev_pos:.4f}",
        "YawControlPosition": f"{rud_pos:.4f}",
    }


def _pack(*pairs) -> str:
    """(key, value) 쌍 중 value 가 None 아닌 것만 'key=value' 로 공백 결합."""
    return " ".join(f"{k}={v}" for k, v in pairs if v is not None)


def combat_attrs(distance_ft, ata_deg, aa_deg, hca_deg, rolloff_deg, closure_kts,
                 health, in_wez=False, tactic=None, g_target=None,
                 g_mode=None, power_mode=None, aim_above=None,
                 pursuit=None, g_burst=None, dphi_deg=None, g_avail=None,
                 limited=None, lead_time=None, lag_dist=None, mode=None,
                 nz=None) -> dict:
    """전투 기하·체력(측정=numeric) + 계층 의사결정(L1/L2/L3 문자열 패킹).

    **측정**(관측·상태)은 개별 numeric 속성으로 유지 — Tacview 시계열 그래프 +
    Health Bar/Control Position 애드온 소비. **결정**(범주형)은 계층당 문자열
    하나로 묶어 프레임당 속성 수를 줄이고 애드온 내러티브(설명가능성)에 직결한다.
    계층 매핑(L5 읽기전용 tap, D5):
      측정      : Distance·ATA·AA·HCA·RollOff·ClosureRate·Health·InWEZ·Gtarget·Gavail·Nz
      L1 전술 BT : node(전술명) · pursuit(추격유형) · burst(지속↔순간 봉투 보간)
      L2 가이드  : mode(국면 모드) · gmode(G 조절) · pwr(파워) · aim·dphi·lead·lag(조준 기하)
      L3 오토파일럿: lim(리미터 포화축 P/Q/R — 개입 육안 확인)
    """
    a = {
        "Distance": f"{distance_ft:.1f}",
        "ATA": f"{ata_deg:.1f}",
        "AA": f"{aa_deg:.1f}",
        "HCA": f"{hca_deg:.1f}",
        "RollOff": f"{rolloff_deg:.1f}",   # 표적 롤오프 각 (구 키명 TAU — τ=시간 오독 방지 개명)
        "ClosureRate": f"{closure_kts:.1f}",
        "Health": f"{health:.1f}",
        "InWEZ": "True" if in_wez else "False",
    }
    if g_target is not None:
        a["Gtarget"] = f"{g_target:.2f}"
    if g_avail is not None:
        a["Gavail"] = f"{g_avail:.2f}"    # 리미터 허용 G 상한 (Gtarget 과 대비 = 조절 여유)
    if nz is not None:
        a["Nz"] = f"{nz:.2f}"             # 실측 하중배수 (JSBSim accelerations/Nz, +=당김)
    # ── 계층 결정 문자열 (범주형 → 계층당 하나; None 값은 생략) ──
    l1 = _pack(("node", tactic), ("pursuit", pursuit),
               ("burst", None if g_burst is None else f"{float(g_burst):.2f}"))
    if l1:
        a["L1"] = l1
    l2 = _pack(("mode", None if mode in (None, "-") else mode),
               ("gmode", g_mode), ("pwr", power_mode),
               ("aim", None if aim_above is None else f"{aim_above:.0f}"),
               ("dphi", None if dphi_deg is None else f"{dphi_deg:.1f}"),
               ("lead", None if lead_time is None else f"{lead_time:.2f}"),
               ("lag", None if lag_dist is None else f"{lag_dist:.0f}"))
    if l2:
        a["L2"] = l2
    if limited is not None:
        a["L3"] = f"lim={limited}"        # 포화 축 (P/Q/R, "-" = 한계 여유)
    return a


def format_header(ref_time: datetime.datetime | None = None,
                  title: str = "ai-combat-core2", version: str = "2.2",
                  comments: str | None = None) -> str:
    """ACMI 헤더 문자열 (파일·실시간 공용).

    기본 ReferenceTime = 생성 날짜(로컬)의 정오 12:00:00Z — Reference lon/lat=0
    에서 태양이 남중해 Tacview 3D 조명이 한낮이 되고, 같은 날 재실행 시
    헤더까지 결정론적으로 일치한다. 명시 ref_time 이 항상 우선.

    comments: 이 파일이 어느 교전인지 스스로 증명하는 메타
    ("match=…;scenario=…;seed=…;engine=…"). 파일명은 바뀌거나 겹칠 수 있지만
    내용은 안 그렇다 — 리플레이가 뒤섞였다는 신고를 파일만 열어 판정하기 위한 것.
    """
    ref = ref_time or datetime.datetime.combine(
        datetime.date.today(), datetime.time(12, 0, 0),
        tzinfo=datetime.timezone.utc)
    return (
        "FileType=text/acmi/tacview\n"
        f"FileVersion={version}\n"
        f"0,ReferenceTime={ref.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        "0,ReferenceLongitude=0\n"
        "0,ReferenceLatitude=0\n"
        f"0,Title={title}\n"
        + (f"0,Comments={comments}\n" if comments else "")
    )


def format_frame(sim_time: float, objects: list[ACMIObject],
                 declared: set | None = None) -> str:
    """한 프레임 문자열. declared=set 이면 정적 속성 1회만(파일);
    None 이면 매 프레임 재선언(실시간 — 늦게 접속한 클라 대비)."""
    out = [f"#{sim_time:.2f}\n"]
    for o in objects:
        line = (f"{o.id},T={o.lon:.7f}|{o.lat:.7f}|{o.alt_m:.1f}|"
                f"{o.roll_deg:.1f}|{o.pitch_deg:.1f}|{o.yaw_deg:.1f}")
        first = declared is None or o.id not in declared
        if first:
            line += f",Name={o.name},Type={o.type},Color={o.color},Coalition={o.coalition}"
            if o.callsign:
                line += f",CallSign={o.callsign}"
            if declared is not None:
                declared.add(o.id)
        out.append(line + "\n")
        for k, v in o.attrs.items():
            out.append(f"{o.id},{k}={v}\n")
    return "".join(out)


class GunVisualizer:
    """Tacview 기총 궤적 — WEZ 사격 중 반투명 레이저(Beam) 표시 (core-live replay.py 이식).

    ★ ACMI 객체 ID 는 16진수 파싱 — 빔 ID 에 '_'(비-16진) 금지(core-live 서 항공기 ID
      충돌·유령 부활 버그 실증). 빔 ID = f"{owner}FACE" (예: 100 → 0x100FACE, 불충돌).
    """

    def __init__(self, owner_id: int, color: str):
        self.beam_id = f"{owner_id}FACE"
        self.color = color                     # 0xAARGGBB (반투명)
        self.is_firing = False

    def step(self, f, is_firing: bool, lon: float, lat: float, alt_m: float,
             hdg_deg: float, pitch_deg: float) -> None:
        import math
        if is_firing:
            if not self.is_firing:
                f.write(f"{self.beam_id},Type=Beam,Color={self.color},Length=1000,Radius=10\n")
                self.is_firing = True
            dist = 500.0                       # 기수 앞 500m 중심점
            p, h = math.radians(pitch_deg), math.radians(hdg_deg)
            R = 6378137.0
            b_lat = lat + math.degrees(dist * math.cos(p) * math.cos(h) / R)
            b_lon = lon + math.degrees(dist * math.cos(p) * math.sin(h)
                                       / (R * math.cos(math.radians(lat))))
            b_alt = alt_m + dist * math.sin(p)
            f.write(f"{self.beam_id},T={b_lon:.8f}|{b_lat:.8f}|{b_alt:.2f}"
                    f"|0|{pitch_deg:.2f}|{hdg_deg:.2f}\n")
        elif self.is_firing:
            f.write(f"-{self.beam_id}\n")
            self.is_firing = False


class ACMIWriter:
    """사후 .acmi 파일 writer. with 문 지원."""

    def __init__(self, path: str, ref_time: datetime.datetime | None = None,
                 title: str = "ai-combat-core2", comments: str | None = None):
        self.path = path
        # Tacview 텍스트 acmi 는 UTF-8 BOM.
        self._f = open(path, "w", encoding="utf-8-sig", newline="\n")
        self._f.write(format_header(ref_time, title, comments=comments))
        self._declared: set[int] = set()

    def frame(self, sim_time: float, objects: list[ACMIObject]) -> None:
        self._f.write(format_frame(sim_time, objects, self._declared))

    def event(self, sim_time: float, text: str) -> None:
        """전역 이벤트(HIT, 승패 등) 북마크."""
        self._f.write(f"#{sim_time:.2f}\n0,Event=Bookmark|{text}\n")

    def message(self, obj_id: int, text: str) -> None:
        """객체 이벤트 메시지 — Tacview Event Log 패널(전술 전환·WEZ 진입 등).
        현재 프레임(#t) 안에 이어 쓴다(별도 timestamp 없음)."""
        self._f.write(f"0,Event=Message|{obj_id}|{text}\n")

    def raw(self, text: str) -> None:
        """현재 프레임에 원시 줄 추가(Beam 객체 등 비-ACMIObject 기록용)."""
        self._f.write(text)

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
