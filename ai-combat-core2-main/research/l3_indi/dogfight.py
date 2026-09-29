"""E층 도그파이트 실험 — 개정 A31 (교수 피드백 2026-09-23: 변수를 하나씩 바꾼 OFAT + 전체 결합).

무엇을 재나
  INDI 내부 루프 연구 변수를 **청군에만** 바꿔 놓고, 배터리 1:1 교전의 결과(E층), 경기 중 내부 루프 추종(T층),
  F-16 성능 봉투 사용량이 어떻게 달라지는지 잰다. 변수·수준·배터리는 dogfight_grid.json 이 단일 진실이다.

경기 구성 (개정 A27 §4 의 3 단계 + §7 안전장치)
  청군 = config/tactics.yaml (기본 트리 고정), 적 = 배터리 레드 5 종, 시나리오 = BEM 4 장 국면 4 종
  (headon=HABFM, perch_offense=OBFM, perch_defense=DBFM, neutral), 시드 = derive_seed(솔트, 시나리오, 레드).
  Match(300 s, wall_limit_s 3600, 오버타임 없음, ACMI 없음). 양측 load_policy 는 따로 부른다.

주입 (배치 코드 aircombat/ 무수정)
  청군 Pilot.setup 을 인스턴스 수준에서 감싼다. 배치 setup(트림 상태에서 G0 식별) 뒤에 harness.build 와 같은 방식으로
  ① INDI 재생성(게인 배율·필터·G0 피치 행 배율 λ_q, 동기 지연 변형) ② 플랜트 프록시(자이로 잡음·측정 지연)
  ③ 난류(JSBSim MIL-Spec Dryden) 를 입힌다. 기준 설정의 재생성이 배치 경로와 비트 동일함은 --selfcheck 가 확인한다.

기록 (읽기 전용)
  step_physics·limiter 를 감싸 참 상태를 기록한다. WEZ 는 엔진과 같은 함수·같은 입력으로 틱마다 다시 계산하고,
  그 누적 시간이 엔진 MatchResult.wez_time 과 일치하는지 매 경기 검사한다(wez_recount_ok).

사용
  python research/l3_indi/dogfight.py --selfcheck                 주입·기록 무결성·결정론 점검 (본실행 전 필수)
  python research/l3_indi/dogfight.py --time 2                     기준 설정 2 경기 벽시계 측정 (결과 저장 안 함)
  python research/l3_indi/dogfight.py --run BASE,SHAM --salts 2   지정 설정만 (파일럿·카오스 바닥)
  python research/l3_indi/dogfight.py --run ofat                   기준·가짜 짝·OFAT 전체
출력: results/paper/<이름>/<커밋10>/{runs.csv, jobs.json, manifest.json}
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import dataclasses
import io
import json
import math
import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from l3_indi.harness import (REPO, DT, Params, Uncertainty, PlantProxy,   # noqa: E402  (sys.path·env 설정 포함)
                             SyncDelayINDI, transform_g0, GYRO_PROPS, ACC_PROPS)

GRID_PATH = os.path.join(HERE, "dogfight_grid.json")
WALL_LIMIT_S = 3600.0                  # A27 §7-2 — 벽시계 판정(wall_clock)이 결과를 오염시키지 않게
KT_TO_FPS = 1.6878098571011957
J_FLOOR_DPS = 2.0                      # metrics.J_FLOOR_DPS 와 같은 값 (사전등록 §3.1)
STALL_KTS = 100.0                      # aircombat.engine.match.STALL_KTS 와 같은 값
TURN_RATE_WIN_TICKS = 30               # 선회율 = 0.25 s 동안의 속도벡터 회전각 / 0.25 s
SAT_THRESH = 0.999                     # 조종면 명령 포화 판정 (사전등록 §4 진단)

# MIL-F-8785C / MIL-HDBK-1797 Dryden 난류 — JSBSim turb-type 3 (ttMilspec).
#   severity = 초과확률 곡선 번호 (JSBSim FGWinds, MIL-F-8785C Fig. 7): 3 → 1e-2(약), 4 → 1e-3(중), 6 → 1e-5(강).
#   windspeed_at_20ft 는 저고도(≤ 1,000 ft) 강도 기준으로 MIL-F-8785C 의 약·중·강 15/30/45 kt 를 쓴다.
#   15 kft 실측 RMS 돌풍(프로브): 약 4.1~5.5, 중 7.2~9.6, 강 19.8~26.4 ft/s — 표 값 4.6 / 8.0 / 22.1 ft/s 와 부합.
TURB_TYPE_MILSPEC = 3
TURB_LEVELS = {"none": None,
               "light": {"severity": 3, "w20_kt": 15.0},
               "moderate": {"severity": 4, "w20_kt": 30.0},
               "severe": {"severity": 6, "w20_kt": 45.0}}

REC_COLS = ("pn", "pe", "pd", "vn", "ve", "vd", "phi", "theta", "psi", "kcas", "vt", "alt",
            "nz", "alpha", "p", "q", "r")
BLUE_EXTRA = ("sp_p", "sp_q", "u_ele")
C = {name: i for i, name in enumerate(REC_COLS + BLUE_EXTRA)}


# ======================================================================================
# 설정
# ======================================================================================
@dataclass(frozen=True)
class Setting:
    """연구 변수 한 벌. 기본값 = 배치된 INDI (pilot.py:53, k_rate (9,9,6), 25 Hz) + 교란 없음."""
    k_scale: tuple = (1.0, 1.0, 1.0)      # (p, q, r) 게인 배율
    filt_hz: float = 25.0                 # 동기화 필터 차단주파수
    lam_q: float = 1.0                    # λ_q = G_model / G_true (피치 행만)
    delay_ticks: int = 0                  # 자이로·각가속도 읽기 지연 [틱]
    delay_sync: bool = True               # True: INDI 액추에이터 되먹임도 같은 틱 지연 (A10-4 동기 변형)
    gyro_sigma: float = 0.0               # 120 Hz 샘플당 자이로 백색잡음 σ [deg/s]
    turb: str = "none"                    # TURB_LEVELS 키
    turb_side: str = "blue"               # "blue": 청군만, "both": 양측
    indi_side: str = "blue"               # "blue": 청군만 주입, "both": 적군에도 같은 설정 (A35 §7 대칭 칸)

    @classmethod
    def from_dict(cls, d: dict) -> "Setting":
        d = dict(d)
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"모르는 설정 항목: {sorted(unknown)}")
        if "k_scale" in d:
            d["k_scale"] = tuple(float(x) for x in d["k_scale"])
        for key in ("filt_hz", "lam_q", "gyro_sigma"):
            if key in d:
                d[key] = float(d[key])
        if "delay_ticks" in d:
            if int(d["delay_ticks"]) != d["delay_ticks"]:
                raise ValueError(f"delay_ticks 는 정수여야 함: {d['delay_ticks']}")
            d["delay_ticks"] = int(d["delay_ticks"])
        s = cls(**d)
        s.validate()
        return s

    def validate(self) -> None:
        if len(self.k_scale) != 3 or min(self.k_scale) <= 0:
            raise ValueError(f"k_scale: {self.k_scale}")
        if self.filt_hz <= 0 or self.lam_q <= 0 or self.gyro_sigma < 0 or self.delay_ticks < 0:
            raise ValueError(f"범위 밖 설정: {self}")
        if self.turb not in TURB_LEVELS:
            raise ValueError(f"turb: {self.turb}")
        if self.turb_side not in ("blue", "both"):
            raise ValueError(f"turb_side: {self.turb_side}")
        if self.indi_side not in ("blue", "both"):
            raise ValueError(f"indi_side: {self.indi_side}")

    def params(self) -> Params:
        return Params(k_scale=tuple(self.k_scale), filt_hz=float(self.filt_hz))

    def uncertainty(self, noise_seed: int) -> Uncertainty:
        return Uncertainty(g0_row_scale=(1.0, float(self.lam_q), 1.0),
                           gyro_sigma_dps=float(self.gyro_sigma), seed=int(noise_seed),
                           meas_delay_steps=int(self.delay_ticks),
                           sync_act_delay=bool(self.delay_sync and self.delay_ticks > 0))

    def to_json(self) -> dict:
        d = dataclasses.asdict(self)
        d["k_scale"] = list(self.k_scale)
        return d


FACTORS = "ABCDEF"


def combined_design(grid: dict) -> list[dict]:
    """격자의 'combined' 사양을 16 칸으로 펼친다 (개정 A31 §6). A 가 가장 빨리 바뀌는 표준 순서.

    반환 원소: {name, family, variable, level, set, _code}. 전부 낮음인 X01 은 BASE 와 같은 설정이다.
    """
    spec = grid.get("combined")
    if not spec:
        return []
    fac, gens = spec["factors"], spec["generators"]
    free = [f for f in FACTORS if f not in gens]
    if sorted(fac) != sorted(FACTORS) or len(free) != 4:
        raise ValueError(f"결합 설계 인자 정의 오류: 인자 {sorted(fac)}, 생성자 {gens}")
    out = []
    for i in range(2 ** len(free)):
        code = {f: (1 if (i >> k) & 1 else -1) for k, f in enumerate(free)}
        for g, word in gens.items():
            code[g] = int(np.prod([code[c] for c in word]))
        over = {}
        for f in FACTORS:
            if code[f] > 0:
                for key, val in fac[f]["high"].items():
                    if key in over:
                        raise ValueError(f"인자 {f} 가 다른 인자와 같은 항목 {key} 를 바꾼다")
                    over[key] = val
        level = "".join(f"{f}{'+' if code[f] > 0 else '-'}" for f in FACTORS)
        out.append({"name": f"X{i + 1:02d}", "family": "combined", "variable": "combined",
                    "level": level, "set": over, "_code": code})
    return out


def design_check(design: list[dict]) -> tuple[bool, str]:
    """균형·주효과 직교·해상도 IV(주효과가 어떤 2 원 교호작용과도 별칭이 아님)를 확인하고 관심 별칭을 돌려준다."""
    M = np.array([[d["_code"][f] for f in FACTORS] for d in design])
    n = len(M)
    balanced = bool(np.all(M.sum(axis=0) == 0))
    orth = bool(np.array_equal(M.T @ M, n * np.eye(len(FACTORS), dtype=int)))
    two = {f"{a}{b}": M[:, i] * M[:, j] for i, a in enumerate(FACTORS)
           for j, b in enumerate(FACTORS) if j > i}
    res4 = all(abs(int(M[:, i] @ col)) != n for i in range(len(FACTORS)) for col in two.values())
    alias = {k: [o for o, v in two.items() if o != k and np.array_equal(v, two[k])] for k in ("AC", "AD")}
    ok = n == 16 and balanced and orth and res4
    return ok, (f"칸 {n}, 균형={balanced}, 주효과 직교={orth}, 해상도 IV={res4}, "
                f"A×C 별칭 {alias['AC']}, A×D 별칭 {alias['AD']}")


def load_grid(path: str = GRID_PATH) -> dict:
    """격자 파일을 읽고 설정마다 baseline 과 합친 Setting 을 검증해 붙인다.

    결합 설계 칸은 settings 뒤에 붙인다. 전부 낮음인 칸(BASE 와 같은 설정)은 새로 돌리지 않으므로 넣지 않고,
    펼친 16 칸 전체는 g["_combined_design"] 에 둔다 (분석에서 X01 = BASE).
    """
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    base = g["baseline"]
    Setting.from_dict(base)
    design = combined_design(g)
    g["_combined_design"] = design
    g["settings"] += [d for d in design if d["set"]]
    seen = set()
    for s in g["settings"]:
        if s["name"] in seen:
            raise ValueError(f"설정 이름 중복: {s['name']}")
        seen.add(s["name"])
        unknown = set(s["set"]) - set(base)
        if unknown:
            raise ValueError(f"{s['name']}: baseline 에 없는 항목 {sorted(unknown)}")
        merged = dict(base)
        merged.update(s["set"])
        s["_setting"] = Setting.from_dict(merged)
    b = g["battery"]
    if len(set(b["salts"])) != len(b["salts"]):
        raise ValueError("솔트 중복")
    return g


def sub_seed(*parts) -> int:
    """경기 시드에서 파생한 보조 난수 시드 (잡음·난류). JSBSim randomseed 가 받는 양의 32 비트 정수."""
    from aircombat.bridge import derive_seed
    return derive_seed("l3dog", *parts) & 0x7FFFFFFF


def build_jobs(grid: dict, names, n_salts: int | None = None, salt_offset: int = 0) -> list[dict]:
    from aircombat.bridge import derive_seed
    b = grid["battery"]
    salts = b["salts"][salt_offset:]                       # A35 §7: 확증은 탐색에 안 쓴 솔트로
    salts = salts[:n_salts] if n_salts else salts
    if not salts:
        raise ValueError(f"솔트가 비었다: offset={salt_offset}, 전체 {len(b['salts'])}")
    by_name = {s["name"]: s for s in grid["settings"]}
    jobs = []
    for name in names:
        s = by_name[name]
        for red in b["reds"]:
            for sc in b["scenarios"]:
                for salt in salts:
                    seed = derive_seed(salt, sc, red)               # tournament.run_gauntlet 과 같은 규칙
                    jobs.append({
                        "match_id": f"{name}__{red}__{sc}__{salt}",
                        "setting_name": name, "family": s["family"], "variable": s["variable"],
                        "level": str(s["level"]),
                        "red": red, "red_path": f"redteams/{red}.yaml", "blue_policy": b["blue_policy"],
                        "scenario": sc, "salt": salt, "seed": seed,
                        "noise_seed": sub_seed("gyro", seed),
                        "turb_seed_blue": sub_seed("turb", "blue", seed),
                        "turb_seed_red": sub_seed("turb", "red", seed),
                        "duration_s": float(b["duration_s"]),
                        "setting": s["_setting"].to_json(),
                    })
    return jobs


def select_settings(grid: dict, spec: str) -> list[str]:
    names = [s["name"] for s in grid["settings"]]
    if spec == "ofat":
        return [s["name"] for s in grid["settings"] if s["family"] in ("baseline", "sham", "ofat")]
    if spec == "speed":                                  # A35 §7 확증 = OFAT + 대칭 칸
        return [s["name"] for s in grid["settings"]
                if s["family"] in ("baseline", "sham", "ofat", "sym")]
    if spec == "combined":
        return [s["name"] for s in grid["settings"] if s["family"] == "combined"]
    if spec == "all":
        return names
    picked = [x.strip() for x in spec.split(",") if x.strip()]
    missing = [x for x in picked if x not in names]
    if missing:
        raise ValueError(f"격자에 없는 설정: {missing}")
    return picked


# ======================================================================================
# 주입 — 프록시·난류·INDI 재생성
# ======================================================================================
class NoisyDelayProxy(PlantProxy):
    """PlantProxy 에 '자이로 잡음 + 측정 지연' 동시 적용을 더한 변형 (A31 결합 설계용).

    PlantProxy 는 지연이 있으면 잡음 없는 과거 참 값을 돌려준다(A10-4 설계: 둘을 함께 쓰지 않음).
    결합 설계에는 둘이 함께 켜지는 칸이 있으므로, 이 클래스는 지연 이력에 **잡음이 섞인 측정값**을 넣는다.
    잡음 수열(시드·추첨 순서)은 PlantProxy 와 같다. σ = 0 또는 N = 0 이면 부모 경로를 그대로 탄다.
    """

    def __init__(self, true_plant, dt: float, gyro_sigma_dps: float = 0.0,
                 input_delay_ms: float = 0.0, seed: int = 0, meas_delay_steps: int = 0):
        super().__init__(true_plant, dt, gyro_sigma_dps, input_delay_ms, seed, meas_delay_steps)
        self._both = self.sigma > 0 and self.meas_delay_steps > 0
        if self._both:
            snap = self._noisy_snapshot()
            self.meas_hist = collections.deque([snap] * (self.meas_delay_steps + 1),
                                               maxlen=self.meas_delay_steps + 1)

    def _noisy_snapshot(self) -> dict:
        snap = {}
        for i, prop in enumerate(GYRO_PROPS):
            snap[prop] = self.true[prop] + self.n[i]
        for i, prop in enumerate(ACC_PROPS):
            snap[prop] = self.true[prop] + (self.n[i] - self.n_prev[i]) / self.dt
        return snap

    def step(self, n: int = 1):
        if not self._both:
            return super().step(n)
        for _ in range(n):
            self.true.step(1)
            self.n_prev = self.n
            self.n = self.rng.normal(0.0, self.sigma, 3)
            self.meas_hist.append(self._noisy_snapshot())
        return self


def make_proxy(true_plant, dt: float, unc: Uncertainty):
    """harness.build 와 같은 인자로 프록시를 만든다. 잡음·지연이 함께 켜질 때만 NoisyDelayProxy."""
    cls = NoisyDelayProxy if (unc.gyro_sigma_dps > 0 and unc.meas_delay_steps > 0) else PlantProxy
    return cls(true_plant, dt, unc.gyro_sigma_dps, unc.input_delay_ms, unc.seed, unc.meas_delay_steps)


def enable_turbulence(true_plant, level: str, seed: int) -> None:
    """JSBSim MIL-Spec(Dryden) 난류를 켠다. 'none' 이면 아무 속성도 건드리지 않는다(기준과 비트 동일)."""
    spec = TURB_LEVELS[level]
    if spec is None:
        return
    true_plant["atmosphere/randomseed"] = int(seed)
    true_plant["atmosphere/turb-type"] = TURB_TYPE_MILSPEC
    true_plant["atmosphere/turbulence/milspec/windspeed_at_20ft_AGL-fps"] = float(spec["w20_kt"]) * KT_TO_FPS
    true_plant["atmosphere/turbulence/milspec/severity"] = int(spec["severity"])


def rebuild_indi(pilot, st: Setting, noise_seed: int):
    """배치 setup 직후 호출 — harness.build 와 같은 순서로 INDI 와 프록시를 바꾼다. 참 플랜트를 돌려준다."""
    from aircombat.control.indi import INDIRateController
    true_plant = pilot.plant
    G0_true = np.array(pilot.indi.G0, copy=True)
    qbar_ref = float(pilot.indi.qbar_ref)
    unc = st.uncertainty(noise_seed)
    prm = st.params()
    G0_model = transform_g0(G0_true, unc)
    if unc.sync_act_delay:
        indi = SyncDelayINDI(pilot.dt_phys, G0_model, qbar_ref, k_rate=prm.k_rate,
                             filt_hz=prm.filt_hz, sync_delay_steps=unc.meas_delay_steps)
    else:
        indi = INDIRateController(pilot.dt_phys, G0_model, qbar_ref, k_rate=prm.k_rate,
                                  filt_hz=prm.filt_hz)
    indi.reset(u0=[true_plant["fcs/aileron-cmd-norm"],       # Pilot.setup 과 같은 u0
                   true_plant["fcs/elevator-cmd-norm"],
                   true_plant["fcs/rudder-cmd-norm"]])
    pilot.indi = indi
    pilot.plant = make_proxy(true_plant, pilot.dt_phys, unc)
    return true_plant


# ======================================================================================
# 기록 — 읽기 전용
# ======================================================================================
class Recorder:
    """한 기체의 참 상태 기록. 행 0 = setup 직후(첫 틱 시작 상태), 행 k+1 = k 번째 물리 스텝 직후.

    행 j 는 엔진이 j 번째 틱 시작에 state() 로 읽는 값과 같다(위치 = Pilot._pos, 나머지 = 참 플랜트).
    청군은 같은 틱의 리미터 통과 지령(sp_p, sp_q)과 INDI 엘리베이터 명령도 남긴다.
    """

    def __init__(self, pilot, true_plant, blue: bool, n_max: int):
        self.p = pilot
        self.P = true_plant
        self.blue = blue
        self.buf = np.full((n_max + 2, len(REC_COLS) + (len(BLUE_EXTRA) if blue else 0)), np.nan)
        self.k = 0
        self.sp = (float("nan"), float("nan"))

    def snap(self) -> None:
        p, P = self.p, self.P
        row = [p._pos[0], p._pos[1], p._pos[2],
               P["velocities/v-north-fps"], P["velocities/v-east-fps"], P["velocities/v-down-fps"],
               P["attitude/phi-rad"], P["attitude/theta-rad"], P["attitude/psi-rad"],
               P["velocities/vc-kts"], P["velocities/vt-fps"], P["position/h-sl-ft"],
               P["accelerations/Nz"], P["aero/alpha-rad"],
               P["velocities/p-rad_sec"], P["velocities/q-rad_sec"], P["velocities/r-rad_sec"]]
        if self.blue:
            row += [self.sp[0], self.sp[1], float(p.indi.u_prev[1])]
        self.buf[self.k] = row
        self.k += 1

    def rows(self) -> np.ndarray:
        return self.buf[:self.k]


def _wrap_limiter(pilot, rec: Recorder) -> None:
    lim = pilot.limiter
    orig = lim.limit_omega_sp

    def limit(omega_sp, v_fps, kcas, g_lift=0.0, _o=orig, _r=rec):
        out, flags = _o(omega_sp, v_fps, kcas, g_lift=g_lift)
        _r.sp = (float(out[0]), float(out[1]))
        return out, flags
    lim.limit_omega_sp = limit


def _wrap_step(pilot, rec: Recorder) -> None:
    orig = pilot.step_physics

    def step(_o=orig, _r=rec):
        _o()
        _r.snap()
    pilot.step_physics = step


def _wrap_setup(pilot, rec: Recorder, st: Setting | None, noise_seed: int,
                turb_level: str, turb_seed: int) -> None:
    """배치 setup → (청군이면 INDI·프록시 재생성) → (난류) → 시작 상태 기록."""
    orig = pilot.setup

    def setup(_o=orig, _p=pilot):
        _o()
        true_plant = rebuild_indi(_p, st, noise_seed) if st is not None else _p.plant
        enable_turbulence(true_plant, turb_level, turb_seed)
        rec.snap()
        return _p
    pilot.setup = setup


# ======================================================================================
# 한 경기
# ======================================================================================
def blue_points(winner: str, condition: str) -> int:
    """aircombat.engine.tournament._record 와 같은 승점 규칙 (청군 기준)."""
    if condition == "no_contact":
        return 0
    if winner == "draw":
        return 1
    return 3 if winner == "blue" else 0


def play(job: dict, instrument: bool = True):
    """배터리 1 경기. instrument=False 는 selfcheck 전용 — 주입·기록 없이 배치 그대로 돌린다."""
    from aircombat.engine.factory import load_policy, make_pilot
    from aircombat.engine.match import Match
    from aircombat.engine.scenarios import initial_conditions
    st = Setting.from_dict(job["setting"])
    dur = float(job["duration_s"])
    n_max = int(round(dur / DT)) + 2
    cwd = os.getcwd()
    os.chdir(REPO)
    t0 = time.perf_counter()
    recs = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            blue_side = load_policy(job["blue_policy"])          # A27 §7-3: 양측 따로
            red_side = load_policy(job["red_path"])
            ic = initial_conditions(job["scenario"], seed=job["seed"])
            blue = make_pilot("Blue", ic["blue"], *blue_side, name="tactics")
            red = make_pilot("Red", ic["red"], *red_side, name=job["red"])
        if instrument:
            rb = Recorder(blue, blue.plant, True, n_max)
            rr = Recorder(red, red.plant, False, n_max)
            _wrap_limiter(blue, rb)
            _wrap_setup(blue, rb, st, job["noise_seed"], st.turb, job["turb_seed_blue"])
            red_st = st if st.indi_side == "both" else None
            _wrap_setup(red, rr, red_st, job["noise_seed"] ^ 0x5F5E0FF,
                        st.turb if st.turb_side == "both" else "none", job["turb_seed_red"])
            _wrap_step(blue, rb)
            _wrap_step(red, rr)
            recs = (rb, rr)
        elif st != Setting():
            raise ValueError("instrument=False 는 기준 설정에서만 쓴다")
        with contextlib.redirect_stdout(io.StringIO()):
            res = Match(blue, red, duration_s=dur, log_hz=0, wall_limit_s=WALL_LIMIT_S,
                        overtime_s=0.0).run()
    finally:
        os.chdir(cwd)
    wall = time.perf_counter() - t0
    row = result_row(job, res)
    if recs is not None:
        row.update(recorded_metrics(recs[0], recs[1], res))
    row["wall_s"] = round(wall, 2)
    return row


def result_row(job: dict, res) -> dict:
    """엔진 판정 그대로 (E층 주 지표의 원천)."""
    from aircombat.bridge import _ranked_healths, _WINNER_MAP
    row = {k: v for k, v in job.items() if not k.startswith("_") and k != "setting"}
    st = job["setting"]
    row.update({"k_p": st["k_scale"][0], "k_q": st["k_scale"][1], "k_r": st["k_scale"][2],
                "filt_hz": st["filt_hz"], "lam_q": st["lam_q"], "delay_ticks": st["delay_ticks"],
                "delay_sync": int(bool(st["delay_sync"])), "gyro_sigma": st["gyro_sigma"],
                "turb": st["turb"], "turb_side": st["turb_side"],
                "indi_side": st.get("indi_side", "blue")})
    wez = res.wez_time or {"blue": 0.0, "red": 0.0}
    ata = res.ata_mean or {"blue": float("nan"), "red": float("nan")}
    # D8 득실 규약(bridge 와 같은 함수): 판정패(hard_deck/stall/disqualified)의 패자 HP → 0
    hb, hr = _ranked_healths(_WINNER_MAP[res.winner], res.condition, res.hp_blue, res.hp_red)
    row.update({"winner": res.winner, "condition": res.condition, "time_s": res.time_s,
                "hp_blue": res.hp_blue, "hp_red": res.hp_red,
                "hp_blue_d8": hb, "hp_red_d8": hr, "hp_diff_d8": hb - hr,
                "blue_pts": blue_points(res.winner, res.condition),
                "wez_time_blue": wez["blue"], "wez_time_red": wez["red"],
                "net_wez": wez["blue"] - wez["red"],
                "ata_mean_blue": ata["blue"], "ata_mean_red": ata["red"]})
    return row


def _kin(rows: np.ndarray, j: int):
    from aircombat.engine.state import KinState
    r = rows[j]
    return KinState(pos_ned=np.array([r[C["pn"]], r[C["pe"]], r[C["pd"]]]),
                    vel_ned=np.array([r[C["vn"]], r[C["ve"]], r[C["vd"]]]),
                    phi=float(r[C["phi"]]), theta=float(r[C["theta"]]), psi=float(r[C["psi"]]),
                    v_fps=float(r[C["vt"]]), kcas=float(r[C["kcas"]]), alt_ft=float(r[C["alt"]]))


def _wez_series(B: np.ndarray, R: np.ndarray, n_ticks: int):
    """엔진 match._wez_damage 와 같은 계산을 틱마다 다시 한다 (같은 함수·같은 입력)."""
    from aircombat.engine.state import FT_TO_M
    from aircombat.geometry.combat_geometry import CombatGeometry
    from aircombat.geometry.wez import WeaponEngagementZone
    out = np.zeros((n_ticks, 5))                       # dmg_b, ata_b, dmg_r, ata_r, range_ft
    for j in range(n_ticks):
        bs, rs = _kin(B, j), _kin(R, j)
        for col, (s, t) in ((0, (bs, rs)), (2, (rs, bs))):
            geom = CombatGeometry(s.pos_ned * FT_TO_M, t.pos_ned * FT_TO_M,
                                  s.vel_ned * FT_TO_M, t.vel_ned * FT_TO_M,
                                  s.phi, s.theta, s.psi, t.theta, t.psi)
            out[j, col] = WeaponEngagementZone.calculate_damage(geom, DT, False)
            out[j, col + 1] = geom.ata_deg()
        out[j, 4] = float(np.linalg.norm(rs.pos_ned - bs.pos_ned))
    return out


def _turn_rate_max_dps(rows: np.ndarray) -> float:
    """속도벡터가 0.25 s 동안 돈 각도 / 0.25 s 의 최댓값 [deg/s] (수직·수평 구분 없는 3 차원 선회율)."""
    v = rows[:, [C["vn"], C["ve"], C["vd"]]]
    w = TURN_RATE_WIN_TICKS
    if len(v) <= w:
        return float("nan")
    a, b = v[:-w], v[w:]
    cosang = np.sum(a * b, axis=1) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
    return float(np.degrees(np.max(np.arccos(np.clip(cosang, -1.0, 1.0)))) / (w * DT))


# ======================================================================================
# 명령 실현 충실도 (개정 A35 §2) — 반응 속도와 정상상태 도달률
# ======================================================================================
STEP_MIN_DPS = 3.0        # 계단 이벤트로 인정하는 최소 명령 변화 (민감도 2 / 5)
STEP_HOLD_S = 0.5         # 새 수준 유지 요건
STEP_HOLD_TOL = 0.20      # 유지 판정: 새 수준에서 벗어나도 되는 폭 (계단 크기 대비)
SS_WIN_S = 0.2            # 정상상태 창 = 유지 구간의 마지막 이 길이
XCORR_MAX_LAG_S = 0.5     # tau_eq 탐색 상한


def _step_response(sp: np.ndarray, w: np.ndarray) -> dict:
    """이벤트 기반 상승시간과 정상상태 도달률 (A35 §2-1, §2-2).

    sp, w 는 같은 길이의 deg/s 배열이다. 계단 이벤트는 |dsp| >= STEP_MIN_DPS 이고
    이어지는 STEP_HOLD_S 동안 sp 가 새 수준의 +-STEP_HOLD_TOL*|dsp| 안에 머무는 곳이다.
    t63/t90 은 응답이 명령 변화량의 63% / 90% 에 처음 닿는 시각이며,
    유지 구간 안에 닿지 못하면 STEP_HOLD_S 로 검열하고 개수를 센다.
    정상상태 도달률은 유지 구간 마지막 SS_WIN_S 의 mean(w)/유지 수준이다.
    """
    hold = int(round(STEP_HOLD_S / DT))
    ssw = max(1, int(round(SS_WIN_S / DT)))
    n = len(sp)
    t63, t90, ss = [], [], []
    ncens = 0
    k = 1
    while k < n - hold:
        d = float(sp[k] - sp[k - 1])
        if abs(d) < STEP_MIN_DPS:
            k += 1
            continue
        lvl = float(sp[k])
        seg = sp[k:k + hold]
        if float(np.max(np.abs(seg - lvl))) > STEP_HOLD_TOL * abs(d):
            k += 1
            continue
        start = float(w[k - 1])
        target = lvl - start
        if abs(target) < 1e-9:
            k += 1
            continue
        resp = (w[k:k + hold] - start) / target
        i63 = np.flatnonzero(resp >= 0.63)
        i90 = np.flatnonzero(resp >= 0.90)
        t63.append(float(i63[0] + 1) * DT if len(i63) else STEP_HOLD_S)
        t90.append(float(i90[0] + 1) * DT if len(i90) else STEP_HOLD_S)
        if not len(i63):
            ncens += 1
        if abs(lvl) >= STEP_MIN_DPS:        # 유지 수준이 0 근처면 비가 발산하므로 제외
            ss.append(float(np.mean(w[k + hold - ssw:k + hold]) / lvl))
        k += hold                            # 이벤트끼리 겹치지 않게 유지 구간만큼 건너뛴다
    med = lambda v: float(np.median(v)) if v else float("nan")
    # reach63 = 유지 구간 안에 63% 에 닿은 이벤트 비율. t63 이 상한에 붙는 설정(검열)에서도
    # 변별력이 남는 연속값이라 1 순위 후보로 함께 기록한다 (A35 §2-1 보완).
    reach = (1.0 - ncens / len(t63)) if t63 else float("nan")
    return {"t63": med(t63), "t90": med(t90), "ss_ratio": med(ss), "reach63": reach,
            "n_event": len(t63), "n_censor": ncens, "n_ss": len(ss)}


def _xcorr_lag(sp: np.ndarray, w: np.ndarray) -> dict:
    """창 전체 교차상관이 최대가 되는 지연 tau_eq [s] (A35 §2-3, 보조 지표).

    폐루프에서는 유도가 기체 상태를 보고 명령을 만들므로 sp 자체가 w 에 의존한다.
    따라서 이 값은 순수한 내부 루프 지연이 아니라 유도 되먹임이 섞인 값이며,
    RQ1 의 개루프 등가 지연과 직접 비교할 수 없다.
    """
    m = int(round(XCORR_MAX_LAG_S / DT))
    a = sp - float(np.mean(sp))
    b = w - float(np.mean(w))
    den = math.sqrt(float(np.sum(a * a)) * float(np.sum(b * b)))
    if den < 1e-12 or len(a) <= m + 1:
        return {"tau_eq": float("nan"), "xcorr_peak": float("nan")}
    best, blag = -2.0, 0
    for L in range(m + 1):
        c = float(np.dot(a[:len(a) - L], b[L:])) / den
        if c > best:
            best, blag = c, L
    return {"tau_eq": blag * DT, "xcorr_peak": best}


def _envelope(rows: np.ndarray, prefix: str) -> dict:
    return {f"{prefix}nz_max": float(np.max(rows[:, C["nz"]])),
            f"{prefix}nz_min": float(np.min(rows[:, C["nz"]])),
            f"{prefix}alpha_max_deg": float(np.degrees(np.max(rows[:, C["alpha"]]))),
            f"{prefix}alpha_min_deg": float(np.degrees(np.min(rows[:, C["alpha"]]))),
            f"{prefix}p_max_dps": float(np.degrees(np.max(np.abs(rows[:, C["p"]])))),
            f"{prefix}q_max_dps": float(np.degrees(np.max(np.abs(rows[:, C["q"]])))),
            f"{prefix}turn_rate_max_dps": _turn_rate_max_dps(rows),
            f"{prefix}kcas_min": float(np.min(rows[:, C["kcas"]])),
            f"{prefix}kcas_max": float(np.max(rows[:, C["kcas"]])),
            f"{prefix}alt_min_ft": float(np.min(rows[:, C["alt"]]))}


def recorded_metrics(rb: Recorder, rr: Recorder, res) -> dict:
    from aircombat.guidance.doctrine import Doctrine
    B, R = rb.rows(), rr.rows()
    n_ticks = len(B) - 1                    # 물리 스텝 수 = 엔진이 WEZ 를 계산한 틱 수
    if len(R) - 1 != n_ticks or n_ticks < 1:
        raise RuntimeError(f"기록 길이 불일치: blue {len(B)} / red {len(R)}")
    W = _wez_series(B, R, n_ticks)
    in_b, in_r = W[:, 0] > 0, W[:, 2] > 0
    ata_b, rng = W[:, 1], W[:, 4]
    t = np.arange(n_ticks) * DT
    m = {}
    # --- 기록 무결성: 엔진 판정과 같은 값인가 -------------------------------------------
    wez = res.wez_time or {"blue": 0.0, "red": 0.0}
    d_b = abs(np.count_nonzero(in_b) * DT - wez["blue"])
    d_r = abs(np.count_nonzero(in_r) * DT - wez["red"])
    ata_eng = res.ata_mean or {"blue": float("nan"), "red": float("nan")}
    d_ata = max(abs(float(np.mean(ata_b)) - ata_eng["blue"]), abs(float(np.mean(W[:, 3])) - ata_eng["red"]))
    m["n_ticks"] = n_ticks
    m["wez_recount_diff_s"] = float(max(d_b, d_r))
    m["ata_recount_diff_deg"] = float(d_ata)
    m["wez_recount_ok"] = int(d_b < 1e-6 and d_r < 1e-6 and d_ata < 1e-6)
    # --- E층 보조 지표 --------------------------------------------------------------------
    for side, mask in (("blue", in_b), ("red", in_r)):
        idx = np.flatnonzero(mask)
        m[f"t_first_wez_{side}"] = float(t[idx[0]]) if len(idx) else float(res.time_s)
        m[f"wez_censored_{side}"] = int(len(idx) == 0)
        m[f"dmg_dealt_{side}"] = float(np.sum(W[:, 0 if side == "blue" else 2]))
    m["frac_ata30_blue"] = float(np.mean(ata_b < 30.0))
    doc = Doctrine()
    kcas_b = B[:n_ticks, C["kcas"]]
    m["frac_slant_band"] = float(np.mean((rng >= doc.slant_ft_lo) & (rng <= doc.slant_ft_hi)))
    m["frac_ata_band_blue"] = float(np.mean((ata_b >= doc.ata_target_lo) & (ata_b <= doc.ata_target_hi)))
    m["frac_fight_speed_blue"] = float(np.mean((kcas_b >= doc.fighting_kts_lo) & (kcas_b <= doc.fighting_kts_hi)))
    m["frac_corner_blue"] = float(np.mean((kcas_b >= doc.corner_kcas_lo) & (kcas_b <= doc.corner_kcas_hi)))
    m["kcas_mean_blue"] = float(np.mean(kcas_b))
    m["dalt_blue_ft"] = float(B[n_ticks, C["alt"]] - B[0, C["alt"]])
    m["range_min_ft"] = float(np.min(rng))
    m["range_mean_ft"] = float(np.mean(rng))
    m["stall_s_blue"] = float(np.count_nonzero(kcas_b < STALL_KTS) * DT)
    # --- T층 (경기 중 청군 내부 루프; 지령 = 리미터 통과값, 응답 = 같은 틱 물리 스텝 직후 참값) -------
    Bp = B[1:]
    sp_q, q = np.degrees(Bp[:, C["sp_q"]]), np.degrees(Bp[:, C["q"]])
    sp_p, p = np.degrees(Bp[:, C["sp_p"]]), np.degrees(Bp[:, C["p"]])
    for ax, sp, w in (("q", sp_q, q), ("p", sp_p, p)):
        m[f"J_{ax}"] = float(np.sqrt(np.mean((sp - w) ** 2)) / max(np.sqrt(np.mean(sp ** 2)), J_FLOOR_DPS))
    ok = np.std(sp_q) > 1e-9 and np.std(q) > 1e-9
    m["corr_q"] = float(np.corrcoef(sp_q, q)[0, 1]) if ok else float("nan")
    # 명령 실현 충실도 (A35 §2) — 1 순위 지표
    for ax, sp, w in (("q", sp_q, q), ("p", sp_p, p)):
        for key, val in _step_response(sp, w).items():
            m[f"{key}_{ax}"] = val
        for key, val in _xcorr_lag(sp, w).items():
            m[f"{key}_{ax}"] = val
    m["q_gain"] = float(np.mean(np.abs(q)) / max(np.mean(np.abs(sp_q)), 1e-9))
    m["sat_ele"] = float(np.mean(np.abs(Bp[:, C["u_ele"]]) >= SAT_THRESH))
    # --- F-16 성능 봉투 사용량 (판정은 분석 단계에서 임계를 적용) ---------------------------
    m.update(_envelope(Bp, ""))
    m.update(_envelope(R[1:], "red_"))
    return m


def job_fn(job: dict) -> dict:
    return play(job, instrument=True)


# ======================================================================================
# 자체 점검 (본실행 전 필수)
# ======================================================================================
_E_KEYS = ("winner", "condition", "time_s", "hp_blue", "hp_red", "wez_time_blue", "wez_time_red",
           "ata_mean_blue", "ata_mean_red")


def _sc_play(args):
    job, instrument = args
    return play(job, instrument=instrument)


def _proxy_unit_checks() -> list:
    """NoisyDelayProxy 가 PlantProxy 와 같은 경우 같고, 결합 경우 '지연된 잡음 측정값' 인지."""
    from aircombat.fdm.plant import F16Plant
    out = []

    def plant():
        with contextlib.redirect_stdout(io.StringIO()):
            P = F16Plant(dt=DT)
            P.set_ic(alt_ft=15000.0, vc_kts=350.0)
            P["fcs/throttle-cmd-norm"] = 0.85
            P.trim()
        return P

    def series(proxy, n=240):
        vals = []
        for _ in range(n):
            proxy.step(1)
            vals.append([proxy[p] for p in GYRO_PROPS + ACC_PROPS])
        return np.array(vals)

    a = series(NoisyDelayProxy(plant(), DT, 0.03, 0.0, 7, 0))
    b = series(PlantProxy(plant(), DT, 0.03, 0.0, 7, 0))
    out.append(("프록시: 잡음만(N=0) → PlantProxy 와 비트 동일", bool(np.array_equal(a, b)),
                f"최대차 {np.max(np.abs(a - b)):.3g}"))
    a = series(NoisyDelayProxy(plant(), DT, 0.0, 0.0, 7, 4))
    b = series(PlantProxy(plant(), DT, 0.0, 0.0, 7, 4))
    out.append(("프록시: 지연만(σ=0) → PlantProxy 와 비트 동일", bool(np.array_equal(a, b)),
                f"최대차 {np.max(np.abs(a - b)):.3g}"))
    a = series(NoisyDelayProxy(plant(), DT, 0.03, 0.0, 7, 0))
    c = series(NoisyDelayProxy(plant(), DT, 0.03, 0.0, 7, 4))
    ok = bool(np.array_equal(c[4:], a[:-4]))
    out.append(("프록시: 잡음+지연 N=4 → 잡음 측정값을 4 틱 늦게 돌려줌", ok,
                f"대조 {len(a) - 4} 틱, 최대차 {np.max(np.abs(c[4:] - a[:-4])):.3g}"))
    return out


def selfcheck(processes: int = 8) -> int:
    from l3_indi.runner import git_state
    grid = load_grid()
    base_all = build_jobs(grid, ["BASE"], n_salts=1)
    pick = {j["scenario"]: j for j in base_all if j["red"] == "red_adaptive"}
    scen = sorted(pick)
    head = pick["headon"]

    def variant(job, **setting_over):
        j = json.loads(json.dumps(job))
        st = Setting.from_dict(dict(j["setting"], **setting_over))
        j["setting"] = st.to_json()
        j["setting_name"] = "selfcheck:" + ",".join(f"{k}={v}" for k, v in setting_over.items())
        return j

    tasks = [(pick[s], False) for s in scen] + [(pick[s], True) for s in scen]
    tasks += [(head, True),                                              # 결정론 (같은 경기 두 번째)
              (variant(head, lam_q=25.0), True),                         # 주입 효과 (A27 §7-1)
              (variant(head, turb="moderate"), True), (variant(head, turb="moderate"), True),
              (variant(head, gyro_sigma=0.03, delay_ticks=4), True),
              (variant(head, gyro_sigma=0.03, delay_ticks=4), True),
              (variant(head, lam_q=1.000001), True)]                     # 가짜 짝 (정보용)
    t0 = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(processes, len(tasks))) as pool:
        rows = pool.map(_sc_play, tasks, chunksize=1)
    wall = time.perf_counter() - t0
    n = len(scen)
    van, ins = rows[:n], rows[n:2 * n]
    det, lam25, tb1, tb2, nd1, nd2, sham = rows[2 * n:]
    checks = []
    for s, a, b in zip(scen, van, ins):
        same = all(a[k] == b[k] for k in _E_KEYS)
        checks.append((f"기준 주입+기록 = 배치 그대로 ({s})", same,
                       " / ".join(f"{k} {a[k]} vs {b[k]}" for k in ("winner", "condition", "time_s", "hp_blue", "hp_red"))))
    for s, b in zip(scen, ins):
        checks.append((f"WEZ·ATA 재계산 = 엔진 판정 ({s})", b["wez_recount_ok"] == 1,
                       f"WEZ 차 {b['wez_recount_diff_s']:.2e} s, ATA 차 {b['ata_recount_diff_deg']:.2e}°, 틱 {b['n_ticks']}"))

    def same_rows(x, y):
        keys = [k for k in x if k != "wall_s"]
        diff = [k for k in keys if not (x[k] == y[k] or (isinstance(x[k], float) and math.isnan(x[k]) and math.isnan(y[k])))]
        return not diff, diff

    ok, diff = same_rows(ins[scen.index("headon")], det)
    checks.append(("결정론: 같은 경기 두 번 → 모든 지표 동일", ok, f"다른 열 {diff[:5]}"))
    base_h = ins[scen.index("headon")]
    checks.append(("주입 효과: λ_q 25 → 경기 중 J_q 가 기준과 다름 (A27 §7-1)",
                   abs(lam25["J_q"] - base_h["J_q"]) > 1e-6,
                   f"J_q 기준 {base_h['J_q']:.4f} → λ25 {lam25['J_q']:.4f}; 결과 {base_h['winner']}/{base_h['condition']} → {lam25['winner']}/{lam25['condition']}"))
    ok, diff = same_rows(tb1, tb2)
    checks.append(("난류(중) 결정론: 두 번 → 동일", ok, f"다른 열 {diff[:5]}"))
    checks.append(("난류(중) 효과: 기준과 다름", abs(tb1["J_q"] - base_h["J_q"]) > 1e-6,
                   f"J_q 기준 {base_h['J_q']:.4f} → 난류 {tb1['J_q']:.4f}"))
    ok, diff = same_rows(nd1, nd2)
    checks.append(("잡음 0.03 + 지연 4 틱 결정론: 두 번 → 동일", ok, f"다른 열 {diff[:5]}"))
    for name, row in (("λ25", lam25), ("난류", tb1), ("잡음+지연", nd1), ("가짜 짝", sham)):
        checks.append((f"WEZ·ATA 재계산 = 엔진 판정 ({name})", row["wez_recount_ok"] == 1,
                       f"WEZ 차 {row['wez_recount_diff_s']:.2e} s"))
    checks += _proxy_unit_checks()
    ok, ev = design_check(grid["_combined_design"])
    checks.append(("결합 설계: 2^(6-2) 해상도 IV·주효과 직교 (A31 §6)", ok, ev))
    info = (f"가짜 짝(λ_q 1+1e-6, headon): {base_h['winner']}/{base_h['condition']}/{base_h['time_s']:.2f}s "
            f"HP {base_h['hp_blue']:.1f}-{base_h['hp_red']:.1f} → {sham['winner']}/{sham['condition']}/"
            f"{sham['time_s']:.2f}s HP {sham['hp_blue']:.1f}-{sham['hp_red']:.1f}")
    st = git_state()
    passed = all(c[1] for c in checks)
    path = os.path.join(HERE, "reports", f"DOGFIGHT_SELFCHECK_{st['commit'][:10]}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 도그파이트 러너 자체 점검 — commit {st['commit']}\n\n")
        f.write(f"- 실행: {time.strftime('%Y-%m-%d %H:%M:%S')}, 벽시계 {wall:.0f} s, 경기 {len(tasks)}, "
                f"트리 깨끗함={st['clean']}\n")
        f.write(f"- Python {sys.version.split()[0]}\n")
        f.write(f"- 결과: **{'전체 통과' if passed else '실패 있음'}** ({sum(c[1] for c in checks)}/{len(checks)})\n\n")
        f.write("| 검사 | 결과 | 근거 |\n|---|---|---|\n")
        for name, ok, ev in checks:
            f.write(f"| {name} | {'PASS' if ok else '**FAIL**'} | {str(ev).replace('|', '/')} |\n")
        f.write(f"\n정보(판정 아님): {info}\n")
        f.write("\n경기당 벽시계 [s]: " + ", ".join(f"{r['wall_s']:.1f}" for r in rows) + "\n")
    for name, ok, ev in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {ev}")
    print(f"  정보: {info}")
    print(f"[selfcheck] {sum(c[1] for c in checks)}/{len(checks)} pass, {wall:.0f}s -> {path}")
    return 0 if passed else 1


# ======================================================================================
# 체크포인트 실행 — 경기마다 즉시 저장하고, 다시 부르면 끝난 경기를 건너뛴다
# ======================================================================================
def _keep_awake(on: bool) -> None:
    """실행 중 Windows 절전 진입을 막는다(ES_CONTINUOUS | ES_SYSTEM_REQUIRED). 끝나면 해제. 설정은 바꾸지 않는다."""
    if os.name != "nt":
        return
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001 if on else 0x80000000)


def run_checkpointed(name: str, jobs: list, processes: int) -> str:
    """runner.run_experiment 와 같은 산출물(runs.csv·jobs.json·manifest.json)을 만들되,
    끝난 경기를 partial.jsonl 에 한 줄씩 덧붙여 중단에도 살아남게 한다.

    같은 커밋·같은 이름으로 다시 부르면 partial.jsonl 에 있는 match_id 는 건너뛴다(결정론이므로 다시 돌려도 같은 값).
    커밋 안 된 변경이 있으면 거부한다(runner 와 같은 규칙).
    """
    import csv
    import platform
    from l3_indi.runner import git_state, DirtyTreeError, _init_worker
    st = git_state()
    if not st["clean"]:
        raise DirtyTreeError("커밋 안 된 변경이 있어 실행을 거부함:\n  " + "\n  ".join(st["dirty_files"]))
    out_dir = os.path.join(REPO, "results", "paper", name, st["commit"][:10])
    os.makedirs(out_dir, exist_ok=True)
    part = os.path.join(out_dir, "partial.jsonl")
    done = {}
    if os.path.isfile(part):
        with open(part, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:                                     # 중단 순간의 잘린 마지막 줄은 버린다
                    try:
                        r = json.loads(line)
                        done[r["match_id"]] = r
                    except json.JSONDecodeError:
                        pass
    ids = {j["match_id"] for j in jobs}
    todo = [j for j in jobs if j["match_id"] not in done]
    print(f"[dogfight] {out_dir}: 완료 {sum(1 for k in done if k in ids)} / {len(jobs)}, "
          f"남은 경기 {len(todo)}", flush=True)
    t0 = time.time()
    _keep_awake(True)
    try:
        if todo:
            with mp.get_context("spawn").Pool(processes, initializer=_init_worker) as pool, \
                    open(part, "a", encoding="utf-8") as f:
                for k, r in enumerate(pool.imap_unordered(job_fn, todo, chunksize=1), 1):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                    done[r["match_id"]] = r
                    if k % 20 == 0 or k == len(todo):
                        el = time.time() - t0
                        print(f"  {time.strftime('%H:%M:%S')} {k}/{len(todo)} "
                              f"(경기당 {el / k:.1f}s, 남은 약 {el / k * (len(todo) - k) / 60:.0f} 분)", flush=True)
    finally:
        _keep_awake(False)
    rows = [done[j["match_id"]] for j in jobs]                # jobs 순서로 정렬
    keys = sorted({k for r in rows for k in r})
    with open(os.path.join(out_dir, "runs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    manifest = {"experiment": name, "git": st, "allow_dirty": False, "n_jobs": len(jobs),
                "wall_s_last_session": round(time.time() - t0, 1), "processes": processes,
                "checkpointed": True, "python": sys.version, "platform": platform.platform(),
                "created": time.strftime("%Y-%m-%d %H:%M:%S"), "preregistration": "docs/PREREGISTRATION.md"}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "jobs.json"), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False)
    return out_dir


# ======================================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--time", type=int, default=0, help="기준 설정 N 경기 벽시계만 측정")
    ap.add_argument("--run", default=None, help="설정 이름 목록(쉼표) 또는 ofat / combined / speed / all")
    ap.add_argument("--salts", type=int, default=None, help="앞에서부터 N 개 솔트만 (기본: 격자 전체)")
    ap.add_argument("--salt-offset", type=int, default=0, help="앞의 N 개 솔트를 건너뛴다 (A35 확증)")
    ap.add_argument("--processes", type=int, default=8)
    ap.add_argument("--name", default="dogfight", help="결과 폴더 이름")
    args = ap.parse_args()
    if args.selfcheck:
        return selfcheck(args.processes)
    grid = load_grid()
    if args.time:
        jobs = build_jobs(grid, ["BASE"], n_salts=1)[:args.time]
        for j in jobs:
            r = play(j)
            print(f"  {j['match_id']}: {r['winner']}/{r['condition']} {r['time_s']:.1f}s "
                  f"벽시계 {r['wall_s']:.1f}s, WEZ 재계산 {'OK' if r['wez_recount_ok'] else 'FAIL'}")
        return 0
    if args.run:
        names = select_settings(grid, args.run)
        jobs = build_jobs(grid, names, n_salts=args.salts, salt_offset=args.salt_offset)
        print(f"[dogfight] 설정 {len(names)} × 경기 {len(jobs) // max(len(names), 1)} = {len(jobs)} 경기, "
              f"프로세스 {args.processes}", flush=True)
        out = run_checkpointed(args.name, jobs, args.processes)
        print("->", out)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
