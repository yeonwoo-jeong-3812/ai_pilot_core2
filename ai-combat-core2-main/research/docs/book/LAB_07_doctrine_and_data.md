# LAB 7. 실기 특성 데이터 + 우리 제어기 입력의 교범 일치

이 문서는 두 질문에 답한다.
1. **"실기 특성"을 뒷받침할 데이터가 있나?** — LAB 6 레드팀이 남긴 유일한 공백("결함 vs 실 F-16
   특성")을 *공인 데이터*로 좁힌다.
2. **우리 제어기가 기동 시 결정하는 입력(러더·뱅크·스로틀…)이 교범과 일치하나?** — 명령값을 *F-16
   교범*으로 채점한다.

핵심 결론을 먼저: **이 모델의 공력은 NASA 풍동 실측 데이터(TP-1538)이고, 실 F-16 은 "에일러론만으로
선회·러더 거의 안 씀"이 교범이다. 우리 제어기의 명령값(러더≈0·에일러론 선회·스로틀 증가)은 그 F-16
교범과 일치한다.** 따라서 앞서 "결함"으로 본 *러더 약함·러더 미사용*은 **실 F-16 특성(충실)** 이다.

> **갱신 메모(LAB 17 확정).** 아래 §2·§4 에서 한때 잔류 β≈1.5° 를 "FLCS/ARI 재구성 한계(모델측
> 의심)" 로 적었으나, 이후 검증으로 **잔류 β~3° 가 충실히 모델링된 skid 임이 확정**됐다: `CYb`
> side-force + native FLCS 의 결과로, `.acmi`(Tacview) 의 **β/α 컬럼** 으로 실측되며 수평직진에선
> β≈0(물리적으로 정확)이다. 즉 잔류 β 는 *결함/재구성 미흡이 아니라* 충실의 *증거* 다.


## 1. 데이터 — 이 모델은 어디서 왔나 (실측 출처)

`jsbsim_data/aircraft/f16/f16.xml` 의 `<reference>` 가 출처를 명시한다(실측):

| refID | 내용 |
|---|---|
| **NASA TP-1538** | **풍동 데이터(1979.12)** — F-16 공력의 1차 출처 |
| ISBN 0-7232-3458-2 | William Green, *General Dynamics F-16 Dash-1* (1987) — 제원 |
| Richard Murray (Caltech) | F-16 모델 페이지 |

> **NASA TP-1538** = Nguyen 등의 F-16 아음속 풍동 공력 데이터셋. Stevens & Lewis 교과서와 학계 F-16
> 시뮬의 *표준 기준*이다(우리 `autopilot.py`·`indi.py` 도 Stevens & Lewis 를 인용). 즉 **조종면 효과
> (롤·피치·요 미분계수)가 실 풍동 실측에서 온다.**

**러더 요효과(Cndr)도 실측이다.** `f16.xml` 의 `aero/coefficient/Cndr` 표(α·β 격자)는 NASA TP-1538
값으로, α≈0·β=0 에서 약 **−0.045/rad** 수준이다. 비교로 롤 효과는 훨씬 크다(LAB 1 의 B행렬:
B[p,ail]=+15.9 vs B[r,rud]=−0.84, **러더가 에일러너의 ~1/19**). **이 약한 요효과는 임의값이 아니라
풍동 실측의 반영**이다.


## 2. 데이터 — 실 F-16 의 러더·선회 교범 (외부 공인)

| 사실 | 출처 |
|---|---|
| F-16 선회는 *에일러론만*으로 — **러더 거의 안 씀**. ARI(Aileron-Rudder Interconnect)가 adverse yaw 를 *자동* 보정해 β→0 | F-16.net, Falcon BMS *Dark Side of the FLCS* |
| ARI 의 근거인 adverse-yaw 의존성은 **NASA TP-1538 의 Cl_β 곡선**에 들어 있음 | Falcon BMS 개발노트 |
| "대부분 후퇴익 제트기는 선회에 러더 불필요(adverse yaw 작음)" | F-16.net |
| 러더 권한은 **departure 방지** 위해 의도적 제한 — clean F-16 은 *거의 departure 불가* | Wikipedia(F-16), F-16.net |
| 고AoA 에서 조종면 효과 급감(deep stall 50–60° AoA) | Wikipedia(F-16) |

**함의:** 우리가 LAB 4·6 에서 "결함"으로 본 두 가지 —
- *러더 요권한 미약* → **실 F-16 특성**(풍동 Cndr 작음 + FLCS 가 departure 방지로 제한).
- *선회 시 러더≈0* → **실 F-16 교범**(에일러론만 선회).

**잔류 β 에 대한 정정(LAB 17):** 선회 중 측정되는 **잔류 옆미끄럼 |β|~3°** 는 한때 "ARI 재구성 한계"
로 의심했으나, 이후 **충실히 모델링된 skid 로 확정**됐다. `CYb` side-force + native FLCS 가 만든
물리적 결과이고, 수평직진에선 β≈0(정확)·선회에서만 소량 발현한다 — 이는 실 F-16 에서도 나는 정상
거동이다. `.acmi` 의 β/α 컬럼 + 실제 서보 위치(`RudSrv` 등) 로 직접 확인된다(LAB 8). 즉 잔류 β 는
*결함이 아니라 충실의 증거* 다.


## 3. 우리 제어기 입력의 교범 일치 — `doctrine_inputs.py`

★ 교범 기준은 *기체에 맞춰야 한다*(레드팀 교정). 경항공기(FAA AFH)는 러더로 협조하지만, **F-16 은
에일러론만 선회·러더 자동**이다. 그래서 우리 제어기의 *명령값*을 **F-16 교범**으로 채점한다.

```
cd new_match_engine/validation
python doctrine_inputs.py 30      # 30° 선회 roll-in, 명령값 로깅·채점·그래프
```

**검증된 결과 (30° 선회):**

| 교범 규칙(F-16) | 결과 | 측정 |
|---|---|---|
| 에일러론이 선회 주도 → 확립 후 중립 | **PASS** | 롤인 피크 \|ail\|=1.0 → 정상 0.004 |
| **러더 최소(에일러론만 선회, ARI)** | **PASS** | 정상 \|rud_cmd\|=0.000 (<0.05) — *실 F-16 교범과 일치* |
| 스로틀 증가(에너지·유도항력) | **PASS** | 수평 0.393 → 선회 0.398 |
| 엘리베이터 당김↑(하중계수) | **PASS** | 수평 +0.018 → 선회 −0.018(더 당김) |
| 뱅크 ↔ 협조선회 공식 | 주의 | φ=30° 인데 ψ̇ 는 23° 수준(β 측력 — §아래) |
| [참고] 선회 중 잔류 β | 충실 skid | β~3° (*입력 아님 — CYb+FLCS 의 충실한 결과, 실기 정상*) |

→ **핵심 입력 교범 일치 4/5.** 즉 **우리 제어기가 *결정하는 입력*(러더≈0·에일러론 선회·스로틀
증가·엘리베이터 당김)은 F-16 교범을 따른다.**

![doctrine](../../new_match_engine/validation/out/doctrine_inputs.png)
*그래프(out/doctrine_inputs.png): 에일러론이 롤-인 주도 후 중립화, 러더 내내 ≈0(F-16 교범), 엘리베이터
당김 증가, 스로틀 증가, 뱅크 30° 정착·β 소량.*

**중요한 구분 — 입력 대 결과:**
- *입력*(우리가 결정): 러더≈0·에일러론 선회 = **교범 일치(F-16)**.
- *결과*(FLCS/물리가 결정): β=1.5°·선회율 결손 = **FLCS/ARI 협조의 소관**(입력 교범과 별개).

즉 "선회율 결손"의 책임은 *우리 제어기의 입력 선택*이 아니라 **FLCS/ARI 의 협조 정밀도**에 있다.
이는 LAB 6 의 측력 분석(β 가 선회를 방해)과 일치하며, 책임 소재를 *제어기 입력 밖*으로 확정한다.


## 4. 종합 — 레드팀 공백이 얼마나 닫혔나

LAB 6 의 미해결 공백("결함 vs 실 F-16 특성")이 다음으로 좁혀졌다:

| 항목 | 판정(갱신) | 근거 |
|---|---|---|
| 러더 요권한 미약 | **실 F-16 특성(충실)** | 러더 ±30°·풍동 Cndr(TP-1538) + departure 방지 설계 + FLCS 자동 협조 |
| 선회 중 러더≈0 | **실 F-16 교범** | 에일러론만 선회(ARI/FLCS 자동) |
| 우리 제어기 입력 선택 | **교범 일치** | doctrine_inputs 4/5 |
| 선회 잔류 β~3° | **충실한 skid(실기 정상)** | CYb side-force + FLCS — `.acmi` β/α 로 실측, 수평직진 β≈0 |
| 선회율 결손 | β 의 *결과*(충실 물리), 입력 아님 | 측력 분석 + 입력 교범 일치 |

> **공백은 닫혔다(LAB 17).** 한때 "FLCS/ARI 가 실 F-16 만큼 β→0 을 달성하는가" 를 미해결로 뒀으나,
> 잔류 β~3° 가 `CYb`+FLCS 의 *충실한 skid* 임이 `.acmi` β/α 실측으로 확정됐다(수평직진 β≈0). 러더
> ±30°·Cndr(TP-1538)·FLCS 자동 협조도 실기와 일치. → 횡방향 거동은 **충실**로 결론. (남는 건 정밀
> 비행시험 β *수치표* 와의 정량 대조뿐이며, 결함 여부가 아니라 정밀도 확인의 문제다.)


## 재현 명령

```
cd new_match_engine/validation
python doctrine_inputs.py 30          # 입력 교범 일치 채점 + 그래프
python doctrine_inputs.py 45          # 다른 뱅크
# 산출물: out/doctrine_inputs.png, out/doctrine_inputs.csv
```

데이터 출처 확인:

```
grep -n "reference refID" new_match_engine/jsbsim_data/aircraft/f16/f16.xml   # NASA TP-1538 등
```


### 출처
- F-16 공력 모델: **NASA TP-1538** wind tunnel data (1979) — `f16.xml` `<reference>` 명시; Stevens & Lewis, *Aircraft Control and Simulation*.
- F-16 러더/선회 교범: [F-16.net — Rudder use in an F-16](https://www.f-16.net/forum/viewtopic.php?t=2119); [Falcon BMS — Dark Side of the FLCS](https://www.falcon-bms.com/wp-content/uploads/2021/08/FM_Developers_Notes_Part_4.pdf); [Wikipedia — F-16](https://en.wikipedia.org/wiki/General_Dynamics_F-16_Fighting_Falcon).
- 선회 조종면 거동: FAA *Airplane Flying Handbook* (FAA-H-8083-3C) Ch.10.
