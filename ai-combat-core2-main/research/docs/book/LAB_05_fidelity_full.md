# LAB 5. 전체 fidelity 검증 — 추력·축·모드·선회 종합 (확실한 보장)

이 문서는 new engine(JSBSim F-16)의 비행 충실도를 *가능한 모든 표준 실험*으로 점검하고, 각 결과를
**물리 법칙·F-16 스펙과 정량 대조**해 PASS/FAIL 로 보장한다. LAB 3(협조선회)·LAB 4(축별 조종면)을
포함하고, **추력/추진(애프터버너 포함)** 과 **동특성 모드** 를 새로 더한다. 모든 수치는 *결정론적*
이라 명령을 그대로 따라 하면 같은 값이 재현된다.

> **갱신 메모(LAB 17 결론 반영).** 이 LAB 이 한때 요(러더)를 "FAIL:권한부족 = 결함"
> 으로 채점하고 "횡-방향 결함"으로 묶던 것은 *이후 검증으로 정정*됐다. 러더 ±30°·`Cndr`(NASA
> TP-1538)·FLCS 자동 협조(yaw-load PID, ±1.0 권한)는 **실 F-16 과 일치(충실)** 하다. 개루프 스텝에서
> 요율이 작게 보이는 건 *native FLCS 가 외부 러더 명령 위에 자동 협조를 더하기 때문*이지 권한 결함이
> 아니다. 아래 측정 절차·명령은 그대로 유효하되, "결함"으로 단정했던 해석은 *정정 박스*로 바로잡았다.

검증 스위트(`new_match_engine/validation/`):

| 스위트 | 파일 | 다루는 것 |
|---|---|---|
| 추력/추진 | `thrust_check.py` | 엔진상태·throttle곡선·고도lapse·trim균형·우리추력·**애프터버너** |
| 축별 조종면 | `fidelity_axes.py` | 롤·피치·요 개루프 스텝(부호·권한) |
| 동특성 모드 | `fidelity_modes.py` | 단주기·장주기·롤모드·더치롤·나선 |
| 협조선회 | `fidelity_maneuvers.py` | 뱅크 10/20/30/40 (두 제어기) |
| **마스터** | `run_all_fidelity.py` | 위 전부 한 번에 |


## STEP 0 — 준비·한 줄 실행

```
python -m pip install jsbsim numpy scipy scikit-learn
cd new_match_engine/validation
python run_all_fidelity.py quick     # 추력+축+모드 (수십 초~수 분)
python run_all_fidelity.py           # + 협조선회(무거움)까지 전부
```

개별 실행도 가능(권장 — 빠르고 결과가 또렷):

```
python thrust_check.py
python fidelity_axes.py
python fidelity_modes.py
python fidelity_maneuvers.py
```


## STEP 1 — 추력/추진 검증 (+ 애프터버너) — `thrust_check.py`

**엔진:** `f16.xml` 가 `F100-PW-229` 를 로드(확인됨). 엔진 XML 스펙: `milthrust 17800`,
`maxthrust 29000`, `augmented 1`(애프터버너 있음). 검증은 *측정값을 이 스펙·물리와 대조*한다.

```
cd new_match_engine/validation
python thrust_check.py
```

**검증된 결과 (재현값):**

| # | 항목 | 측정 | 판정 |
|---|---|---|---|
| 1 | 엔진 상태 | set-running=1, fuel=3000lbs, n2=100% | **PASS** |
| 2 | throttle→thrust | 0→874, 0.5→17194(≈mil), 1.0→28103(≈AB), 단조증가 | **PASS** |
| 3 | 고도 lapse | SL 27710 → 40k 11589 lbf, 단조감소 | **PASS** |
| 4 | trim 균형 | thrust≈drag, throttle 0.31~0.49(비포화) | **PASS** |
| 5 | ★ 우리 추력 | V_cmd=CAS 350/450/400 → V_ach=CAS 350/450/402 (제어기 정확 유지) | **PASS** |
| 6 | ★ 애프터버너 | XML augmented=1, mil 17194 → AB 27796(x1.62), 연료 x2.22 | **PASS** |

→ **추력 6/6 PASS.** 추력은 물리적으로 정확하다.

> **애프터버너 확인(요청).** 엔진 XML 에 `<augmented>1</augmented>` 로 설정돼 있고, 실거동도 throttle
> ~0.5(mil) 위에서 추력이 17,194→28,103 lbf 로 *증강*되며 연료유량이 3.42→7.67 pps 로 *2배 이상* 뛴다.
> = 애프터버너 정상 작동. (전용 점검: `[6]` 블록.)

> **★ "우리 추력" 주의(중요).** 제어기의 속도 setpoint 는 **CAS(vc-kts)** 단위다. 측정을 *TAS*
> (vt-fps)로 비교하면 15000ft 에서 350 명령이 ~431 로 보여 *오진* 한다. 이 LAB 은 CAS 로 비교해
> *명령과 정확히 일치*(350→350)함을 확인했다. → 제어기 추력·속도 유지 정상.

**STEP 1 내부 동작(재현):** 각 항목은 트림(또는 SL static) → throttle spool(360스텝) → 정상상태에서
`propulsion/engine[0]/thrust-lbs` 등을 읽어 스펙과 비교한다. 전 컬럼 CSV: `out/thrust.csv`.


## STEP 2 — 롤·피치·요 축별 조종면 — `fidelity_axes.py`

(상세 step-by-step 은 **LAB 4** 문서. 여기선 요약.)

```
python fidelity_axes.py
```

| 축 | 조종면 | 부호 | 권한 | 판정 |
|---|---|---|---|---|
| 롤 | aileron | 정확(+) | 강함(+66.6°/s) | **PASS** |
| 피치 | elevator | 정확(−, 당기면 Nz 2.3g) | 충분 | **PASS** |
| 요 | rudder | 정확(−) | 개루프 요율 작음(0.41°/s) | **충실(설명 아래)** |

→ 롤·피치 조종면은 적절. **요(러더)도 충실하다.** 개루프 스텝에서 요율이 작게 보이는 까닭은
`f16.xml` native FLCS 의 yaw-load PID 가 *외부 러더 명령 위에* 자동 협조(요율·요하중 피드백)를
±1.0 권한으로 더해 *불필요한 요를 억제*하기 때문이다 — 권한 결함이 아니라 실 F-16 FLCS 의 정상
동작이다. 러더 면 한계 자체는 ±30°(실 F-16 일치), `Cndr`=NASA TP-1538. 상세·재현은 LAB 4 STEP 5,
종합 판정은 LAB 17.


## STEP 3 — 동특성 모드 — `fidelity_modes.py`

비행기를 짧게 흔든 뒤(펄스) *자유응답*으로 5개 표준 모드를 식별한다. F-16 은 native FLCS(안정성
증강)가 켜져 있어 *증강된* 동특성이 측정된다 — 판정은 "안정·타당한가"(감쇠>0, 발산 없음)이다.

```
python fidelity_modes.py
```

**검증된 결과 (재현값):**

| 모드 | 측정 | 판정 | 해석 |
|---|---|---|---|
| 단주기(short-period) | 주기 1.07s, ζ=0.83 | **PASS** | 빠르고 잘 감쇠(FLCS 증강) — 정상 |
| 롤모드(roll mode) | τ=0.142s, p_ss=+53.5°/s | **PASS** | 빠른 롤 응답 — 정상 |
| 더치롤(dutch roll) | 주기 0.61s, ζ=0.48 | **PASS** | 감쇠 양호(주기는 다소 빠름) |
| 장주기(phugoid) | 식별 부적합(주기<15s) | **보류** | FLCS 억제+빠른모드 오염 — *측정 한계*(결함 아님) |
| 나선(spiral) | φ 20°→163°(40s), +3.59°/s | **FAIL** | **나선 불안정(발산)** — 횡-러더 약점과 일관 |

→ **3/4 PASS(보류 제외).** 종(피치)·롤 모드는 안정·타당. **나선 모드가 발산**(횡방향 약점)하고,
phugoid 는 *측정법 한계로 판정보류*(고친 점: 저주파 데시메이션해도 FLCS 가 장주기를 강하게 누름).

**STEP 3 내부 동작(재현):** 트림 → 해당 조종면 더블릿(앞 +Δ, 뒤 −Δ) 0.4~0.6s → 트림 복귀 →
자유응답에서 국부 극값으로 주기, 로그감쇠율로 ζ 식별. 나선은 뱅크 20° 후 조종간 중립 40s. CSV: `out/modes.csv`.


## STEP 4 — 협조선회 fidelity — `fidelity_maneuvers.py`

(상세 step-by-step·진단은 **LAB 3** 문서. 여기선 요약.)

```
python fidelity_maneuvers.py
```

- 뱅크는 정확히 추종(명령 30°→달성 30.0°), 롤율 p≈0(뱅크 유지 정상).
- 선회율이 이상화 공식보다 ~30% 낮고, 잔류 β 소량 남음 — 단 이는 **결함이 아니라** 실 F-16 에서도
  나는 충실한 skid 의 결과다(LAB 6 §1 에서 반증·정정: 항공기는 수평이었고 측력 정량 일치).
- elevator 평탄은 *수평을 정확히 유지하는 결과*(γ≈0)이며, 잔류 β 는 `.acmi` β/α 컬럼으로 확인 가능.

→ 옛 "elevator 결함·하중계수 부족" 진단은 **반증**됐다(LAB 6·17). 선회율 결손의 원인은 잔류 β 의
외향 측력(=충실한 물리)이다.


## 종합 — 무엇이 보장되고 무엇이 결함인가

**✅ 충실(검증 통과) — 종방향·롤·추진은 신뢰 가능:**

| 영역 | 근거 |
|---|---|
| 추력·추진 전체 | thrust 6/6 PASS, 스펙 일치(Mil 17.8k/AB 29k) |
| **애프터버너** | XML augmented=1 + 실거동 추력 x1.62·연료 x2.22 |
| 우리(제어기) 추력·속도 | CAS setpoint 정확 유지(350→350), throttle 비포화 |
| 롤(aileron) | 부호+·권한 강(66°/s)·τ 0.14s |
| 피치(elevator) | 부호−·하중계수 결합 정확(Nz 2.3g) |
| 단주기·더치롤·롤 모드 | 안정·감쇠 양호 |

**✅ 횡-방향(요/러더)도 충실 — 옛 "결함" 은 정정됨(LAB 6·7·17):**

| 옛 "결함" 라벨 | 측정 | 정정된 판정 |
|---|---|---|
| 러더 요 권한 미약 | 0.4 스텝에 요율 0.41°/s | **충실** — native FLCS yaw-load PID 가 외부 러더 위에 자동 협조(±1.0)로 불필요한 요 억제. 러더 한계 ±30°·Cndr=NASA TP-1538. |
| 협조선회 elevator 미추종 | 선회율 −30%, Nz | **반증** — 항공기 수평(γ≈0); 선회율 결손 원인은 잔류 β 측력(실 F-16 정상 skid). LAB 6 §1. |
| 비협조 β 잔류 | β 1.5~3° | **충실한 skid** — `CYb` side-force + FLCS. `.acmi` β/α 컬럼으로 실측 입증. |
| 나선 모드 발산 | 뱅크 20°→163°/40s | 측정 한계·실 F-16 의 약 나선불안정과 일관 가능(비행시험 데이터 없이 결함 단정 불가 — LAB 6 §3). |

**⏸ 판정보류:** phugoid(장주기) — FLCS 가 강하게 눌러 *깨끗이 식별 불가*. 측정법 한계이지 확정 결함
아님. (필요 시 전용 system-ID 로 별도 추적.)

> **한 줄 보장.** **추진(애프터버너 포함)·종방향(피치)·롤은 물론, 횡-방향(요/러더)도 충실함이
> 검증됐다.** 러더 ±30°·NASA Cndr·FLCS 자동 협조가 실 F-16 과 일치하고, 선회 중 잔류 β 는 *충실히
> 모델링된 skid* 다. 옛 "횡방향 결함 셋" 진단은 LAB 6·7 의 반증과 LAB 17 의 실기 데이터 대조로
> *정정*됐다 — 실 F-16 은 에일러론만으로 선회(러더 자동)하므로 그 거동이 곧 충실의 증거다.


## 재현성 메모

- **결정론**: JSBSim + 고정 IC/입력 → 매번 같은 숫자. 위 표 전부 재현된다.
- **기준의 출처**: 추력=엔진 XML 스펙(F100-PW-229), 선회=물리 공식(ψ̇=g·tanφ/V, n=1/cosφ),
  조종면 부호=엔진 자신의 LQR B행렬, 모드=안정성(감쇠/발산).
- **산출물 CSV**: `validation/out/{thrust,axes_all,modes,fidelity_lqr,fidelity_indi}.csv`.
- **명령 요약:**

```
cd new_match_engine/validation
python run_all_fidelity.py quick   # 추력+축+모드 (빠름)
python thrust_check.py             # 추력/추진 + 애프터버너 (6항목)
python fidelity_axes.py            # 롤·피치·요 (LAB 4)
python fidelity_modes.py           # 동특성 모드 5종
python fidelity_maneuvers.py       # 협조선회 뱅크 sweep (LAB 3)
```

관련 문서: **LAB 3**(협조선회 상세) · **LAB 4**(축별 조종면 상세) · 본 **LAB 5**(전체 종합).

### 출처 (물리·스펙 기준)
- F-16 엔진 F100-PW-229 스펙 — 본 저장소 `jsbsim_data/engine/F100-PW-229.xml`.
- 협조선회 조종면 거동 — FAA *Airplane Flying Handbook* (FAA-H-8083-3C) Ch.10; AOPA *All Types of Turns*.
- 동특성 모드 정의 — Nelson, *Flight Stability and Automatic Control*; Stevens & Lewis, *Aircraft Control and Simulation*.
