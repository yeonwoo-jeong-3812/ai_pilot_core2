"""실험 정의 — 학생이 고칠 곳은 이 파일 하나다.

조건(CONDITIONS)은 INDI에 거는 변화, 실험(EXPERIMENTS)은 (참가자 묶음, 조건, 시나리오, 시드)의 조합이다.
시드 이름의 접두어가 데이터의 쓰임을 정한다. 섞으면 안 된다.
  feas-*  Feasibility (탐색, 가설을 세운 데이터)
  cal-*   E1 보정 (δ를 정하는 데만 쓴다)
  main-*  E2·E3 확증 (판정에만 쓴다)
  gen-*   E4 일반화
"""

# 조건 이름 -> INDI 변화. 키 뜻은 run.py 의 apply_knobs 참조.
#   kappa      제어효과 모델 오차 κ = G_model/G_true (피치 행)
#   kq         피치 각속도 게인 배율
#   filt_hz    동기화 필터 차단주파수 [Hz] (기준 25)
#   sigma_dps  자이로 백색잡음 표준편차 [°/s]
#   delay_async  측정만 N틱 지연 (1틱 = 1/120 s)
#   delay_sync   측정과 조종 입력 되먹임을 함께 N틱 지연
CONDITIONS = {
    "BASE": {},
    "SHAM": {"kappa": 1.000001},
    "FILT10": {"filt_hz": 10.0},
    "FILT50": {"filt_hz": 50.0},
    "NOISE0.3": {"sigma_dps": 0.3},
    "NOISE1.0": {"sigma_dps": 1.0},
    "ASYNC2": {"delay_async": 2},
    "SYNC4": {"delay_sync": 4},
    "SYNC8": {"delay_sync": 8},
    "KAPPA4": {"kappa": 4.0},
    "KAPPA8": {"kappa": 8.0},
    "KAPPA25": {"kappa": 25.0},
    "KQ0.5": {"kq": 0.5},
    # E5 필터 개입: 주엽 계보에서 지연 붕괴를 막은 5 Hz 필터 (RESULTS_REPORT §4.6)
    "FILT5": {"filt_hz": 5.0},
    "ASYNC4": {"delay_async": 4},
    "FILT5+ASYNC2": {"filt_hz": 5.0, "delay_async": 2},
    "FILT5+ASYNC4": {"filt_hz": 5.0, "delay_async": 4},
}

AGENTS_FEAS = {
    "PurePursuer": "agents/main/A1_PurePursuer_00.yaml",
    "GunTracker": "agents/main/A2_GunTracker_00.yaml",
    "LagAngler": "agents/main/A3_LagAngler_00.yaml",
    "EnergyFighter": "agents/main/B1_EnergyFighter_00.yaml",
    "Extender": "agents/main/B2_Extender_00.yaml",
    "RedPrime": "agents/main/red_prime.yaml",
}
AGENTS_MAIN = {**AGENTS_FEAS,
               "TwoCircle": "agents/main/C1_TwoCircleRate_00.yaml",
               "Reactive": "agents/main/D1_Reactive_00.yaml"}
AGENTS_E4 = {
    "PurePursuer5": "agents/e4/A1_PurePursuer_05.yaml",
    "GunTracker6": "agents/e4/A2_GunTracker_06.yaml",
    "LagAngler6": "agents/e4/A3_LagAngler_06.yaml",
    "EnergyFighter6": "agents/e4/B1_EnergyFighter_06.yaml",
    "Extender4": "agents/e4/B2_Extender_04.yaml",
    "TwoCircle3": "agents/e4/C1_TwoCircleRate_03.yaml",
    "OneCircle": "agents/e4/C2_OneCircleRad_00.yaml",
    "Lufbery": "agents/e4/C3_Lufbery_00.yaml",
    "LastDitch": "agents/e4/D2_LastDitch_00.yaml",
    "AdaptiveAce": "agents/e4/E1_AdaptiveAce_00.yaml",
    "RedEnergy": "agents/e4/red_energy.yaml",
    "RedTracker": "agents/e4/red_tracker.yaml",
}

LEAGUE = ("headon", "perch_offense", "neutral")

# 용량-반응: 필터 f_c × 비동기 지연(0.5틱 간격). 이름 "F25_D1.5" = 25 Hz, 1.5틱
DOSE_FILTERS = (25.0, 12.0, 5.0)
DOSE_DELAYS = tuple(x / 2 for x in range(13))           # 0 – 6틱
for _f in DOSE_FILTERS:
    for _d in DOSE_DELAYS:
        CONDITIONS[f"F{_f:g}_D{_d:g}"] = {"filt_hz": _f, **({"delay_async": _d} if _d else {})}
DOSE_CONDS = ["SHAM"] + [f"F{f:g}_D{d:g}" for f in DOSE_FILTERS for d in DOSE_DELAYS]

# 다른 열화 경로: 원인이 달라도 같은 추종 오차–성과 곡선에 오는가
ROUTE = {"kappa": (2, 4, 8, 16, 25), "kq": (0.25, 0.5, 1.5, 2), "sigma_dps": (0.3, 1, 3),
         "delay_sync": (2, 4, 8)}
ROUTE_CONDS = []
for _k, _vals in ROUTE.items():
    for _v in _vals:
        _name = f"R_{_k}_{_v:g}"
        CONDITIONS[_name] = {_k: _v}
        ROUTE_CONDS.append(_name)
# ---------------------------------------------------------------- 본실험 (논문용)
# 제목: 피치 추종 오차를 이용한 공중전 성과 변화 예측
# E2(적합 집합): 필터 × 비동기 지연. 이 조건들로 "추종 오차 → 결과 변화" 곡선을 맞춘다.
# E3(검증 집합): E2 에 없는 원인과 그 조합. E2 곡선으로 미리 예측하고 실제와 비교한다.
FIT_FILTERS = (25.0, 12.0, 5.0)
FIT_DELAYS = (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0)
FIT_CONDS = [f"F{f:g}_D{d:g}" for f in FIT_FILTERS for d in FIT_DELAYS if (f, d) != (25.0, 0.0)]
TEST = {"kappa": (2, 4, 8, 16, 25, 50), "kq": (0.25, 0.5, 1.5, 2), "sigma_dps": (0.3, 1, 3, 6),
        "delay_sync": (2, 4, 8, 16)}
TEST_CONDS = []
for _k, _vals in TEST.items():
    for _v in _vals:
        _name = f"R_{_k}_{_v:g}"
        CONDITIONS.setdefault(_name, {_k: _v})
        TEST_CONDS.append(_name)
COMBOS = {"C_kappa8+async1": {"kappa": 8.0, "delay_async": 1.0},
          "C_sigma1+kq0.5": {"sigma_dps": 1.0, "kq": 0.5},
          "C_kappa4+sync4": {"kappa": 4.0, "delay_sync": 4},
          "C_f12+sigma3": {"filt_hz": 12.0, "sigma_dps": 3.0}}
CONDITIONS.update(COMBOS)
TEST_CONDS += list(COMBOS)
GEN_CONDS = ["BASE", "SHAM", "F25_D1", "F25_D3", "R_kappa_25", "R_kq_2", "R_sigma_dps_3"]

# ref: 결과 변화의 기준 조건. 모든 조건이 같은 시드에서 이 조건과 짝을 이룬다.
EXPERIMENTS = {
    # 탐색 기록 (주제 선정에 쓴 데이터. 논문 판정에 쓰지 않는다)
    "FEAS": dict(agents=AGENTS_FEAS, scenarios=LEAGUE, salt="feas", salts=4,
                 conds=["BASE", "SHAM", "FILT10", "NOISE0.3", "ASYNC2", "KAPPA8", "KAPPA25"]),
    "DOSE": dict(agents=AGENTS_FEAS, scenarios=LEAGUE, salt="feas2", salts=2, conds=DOSE_CONDS),
    "ROUTE": dict(agents=AGENTS_FEAS, scenarios=LEAGUE, salt="feas2", salts=2,
                  conds=["F25_D0"] + ROUTE_CONDS),
    # 본실험
    "E1": dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt="cal", salts=8, conds=["BASE", "SHAM"], ref="BASE"),
    "E2": dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt="main", salts=8, conds=["BASE"] + FIT_CONDS, ref="BASE"),
    "E3": dict(agents=AGENTS_MAIN, scenarios=LEAGUE, salt="main", salts=8, conds=["BASE"] + TEST_CONDS, ref="BASE"),
    "E4": dict(agents=AGENTS_E4, scenarios=LEAGUE, salt="gen", salts=4, conds=GEN_CONDS, ref="BASE"),
}

# 탐침: κ·잡음·동기 지연으로 큰 추종 오차를 만들 수 있는가 (수준 고르기용, 판정 없음)
PROBE = {"kappa": (50, 100, 200, 400), "sigma_dps": (6, 10, 20), "delay_sync": (16, 24, 32), "kq": (0.1, 3)}
PROBE_CONDS = []
for _k, _vals in PROBE.items():
    for _v in _vals:
        _name = f"R_{_k}_{_v:g}"
        CONDITIONS.setdefault(_name, {_k: _v})
        PROBE_CONDS.append(_name)
EXPERIMENTS["PROBE"] = dict(agents=AGENTS_FEAS, scenarios=("neutral",), salt="probe", salts=1,
                            conds=["BASE"] + PROBE_CONDS)

# 유의성 확인 (feas3, 새 탐색 시드 6개): 적합 집합과 검증 집합을 같은 시드에서 짝으로 돌린다
V_FIT = ["F25_D0.5", "F25_D1", "F25_D2", "F25_D4", "F12_D1", "F12_D2", "F12_D4", "F5_D0", "F5_D2", "F5_D4"]
V_TEST = ["R_kappa_25", "R_kappa_100", "R_kappa_400", "R_sigma_dps_3", "R_sigma_dps_10", "R_sigma_dps_20",
          "R_delay_sync_16", "R_delay_sync_24", "R_kq_0.25", "R_kq_3"] + list(COMBOS)
EXPERIMENTS["SIG"] = dict(agents=AGENTS_FEAS, scenarios=LEAGUE, salt="feas3", salts=6,
                          conds=["BASE", "SHAM"] + V_FIT + V_TEST, ref="BASE")
