# 논문 fidelity 리뷰 대응 — 준비된 답변(Q&A)

> 숫자·상태·D2 서사는 [`CANON.md`](CANON.md)를 정본으로 한다.

리뷰어가 엔진 충실도(fidelity)를 문제 삼을 때의 *예상 질문 + 준비 답변*. 모든 답변은 본 저장소의
검증 데이터(`validation/`)와 출처로 뒷받침된다.

---

## 핵심 방어선 (한 문단 요약)

> 우리 엔진은 **JSBSim 6-DOF + NASA TP-1538 풍동 실측 공력**(F-16 학계 표준, Stevens & Lewis)이다.
> 우리는 충실도를 *가정*하지 않고 **정량 검증 스위트**(축·모드·추력·선회·성능·교범입력)로 물리법칙·
> F-16 스펙·BFM 교범과 대조했다. 추진(애프터버너 포함)·종방향·롤·**yaw 제어(러더)** 모두 충실히
> 검증됐다 — 러더 편향 한계 ±30°(실 F-16 일치), 러더 yaw 모멘트 Cndr이 NASA TP-1538 일치,
> FLCS가 측방가속도 피드백(yaw-load-pid)으로 선회를 ±1.0 권한으로 자동 협조. realistic 모드의 수동
> 러더 cap(0.2)은 *수동 겨냥(nose-skid)* 러더만 제한하며, 이는 실 F-16 gun 교범(roll+pull, 수동
> 러더 미세)상 옳다. 따라서 **realistic 천장 16/17은 결함이 아니라 정직한 fidelity 귀결**이고,
> 잔여 1승(D2)조차 fidelity 문제가 아니라 *분류 정보한계*다(D2는 oracle에서 격파 — CANON §6).
> 더해 **우리 정책과 17 적이 *같은 엔진*을 쓰므로 어떤 충실도 편향도 대칭이라 비교 결과를 편들지
> 않는다.** 격추·무손상은 *각·에너지의 상대 우위*에서 나오며, 협조 아티팩트의 악용이 아니다.
> (전체 측정·검증: 17장 [17_findings_prediction_and_fidelity.md](17_findings_prediction_and_fidelity.md).)

---

## Q1. "시뮬레이터가 실제와 충분히 가까운가? 결과가 의미 있나?"

**답변.** 본 엔진은 **JSBSim**(6자유도 비행동역학, 학계·산업 표준)을 코어로 하고, F-16 공력은
**NASA TP-1538**(1979 풍동 실측, Nguyen 등)에서 온다 — `jsbsim_data/aircraft/f16/f16.xml` 의
`<reference>` 에 명시. 이는 Stevens & Lewis 교과서와 다수 학술 F-16 제어 연구가 쓰는 *바로 그 모델*이다.
즉 충실도 근거가 임의가 아니라 *공인 풍동 데이터*다. 추가로 우리는 충실도를 검증한 *수치 증거*
(아래 Q3)를 제시한다.

---

## Q2. "충실도를 실제로 검증했는가, 아니면 가정했는가?"

**답변.** 검증했다. `validation/` 에 재현 가능한 스위트가 있고, 각 테스트는 *물리 법칙/스펙/교범*과
정량 대조한다:

| 검증 | 기준 | 결과 |
|---|---|---|
| 추력·throttle·lapse·애프터버너 | 엔진 XML 스펙(F100-PW-229) | 6/6 PASS |
| 롤·피치 조종면(부호·권한) | 엔진 B행렬·물리 | PASS |
| 동특성 모드(단주기·롤·더치롤) | 안정성 | PASS |
| Ps·활공비 | F-16 범위 | PASS |
| 러더 권한·Cndr·FLCS 자동 협조 | **±30°·NASA TP-1538·실 F-16** | PASS (§17.3) |
| 우리 제어기 입력(러더·뱅크·스로틀) | **F-16 교범** | PASS |

대부분의 BT/RL 공중전 논문이 충실도를 *암묵 가정*하는 것과 달리, 우리는 *명시 검증*한다 — 이는 약점이
아니라 방법론적 강점이다.

---

## Q3. "당신들의 fidelity 검증이 *선회 협조 결손*을 찾았다는데, 그게 결과를 무효화하지 않나?"

**답변(3단). — 정정: 이는 결손이 아니라 충실·교범의 귀결이다.**

1. **yaw 제어 물리는 충실히 검증됐다.** 후속 control-fidelity 점검(17장 §17.3)에서 러더 편향 한계
   ±30°(실 F-16 일치), 러더 yaw 모멘트 Cndr이 NASA TP-1538(Nguyen) 데이터와 일치함을 확인했다.
   더 결정적으로, FLCS는 측방가속도 피드백(`yaw-load-pid`)으로 선회를 *자동 협조*하며 이 협조는
   native FLCS 안에서 **±1.0 전권한**으로 작동한다. 곧 turn coordination이 약하거나 잘못된 물리라는
   *이전 진단은 틀렸고 제거한다*.

2. **realistic cap은 *수동* 러더만 제한 — 도덕적으로 옳다.** INDI 제어기는 `fcs/rudder-cmd-norm`을
   쓰므로 그 출력이 native FLCS를 *통과*한다. FLCS 자동 협조는 INDI 명령 *위에* 더해지고 realistic
   cap(`INDI_RUD_MAX_CRUISE=0.2`)에 막히지 않는다. 그래서 cap이 막는 건 *수동 겨냥(nose-skid)*
   러더뿐인데, 이는 실 F-16 gun 교범(gun tracking = roll+pull, 수동 러더 미세)과 정확히 일치한다.

3. **결정적 — 대칭성.** 우리 정책과 17 적이 **동일 엔진·동일 FLCS**에서 싸운다. 어떤 충실도 편향도
   *양측에 똑같이* 작용하므로 *상대 비교 결과를 편들지 않는다*. 격추·무손상은 *각을 끊는 상대
   기하·에너지 우위*(§5·§6)에서 나오며, 협조 아티팩트의 비대칭 악용이 아니다. realistic 천장
   16/17이며(조건부 high-g로 A3 격파), 잔여 1승(D2)은 *교범 러더의 결함*이 아니라 blind 분류의
   정보한계다 — D2는 운동학적으로 격파 가능하다(oracle 17/17, CANON §6).

---

## Q4. "그래도 선회 중 잔여 β(sideslip)가 보인다. 그건 모델 버그 아닌가?"

**답변(정직).** 먼저, 잔여 β는 *충실의 증거*다. fidelity 로깅으로 측정한 선회 중 \|β\|~3°는
side-force(`CYb`) + FLCS 협조가 *작동하는* 결과이며, 수평직진에서는 β≈0이다 — skid 물리가
물리적으로 정확히 모델링됐다는 뜻이다(17장 §17.7). **공력(TP-1538)·러더 권한·FLCS 자동 협조는
충실히 검증됐다(§17.3).**

남는 *저신뢰 잔여 caveat* 하나만 명시한다: FLCS 협조 게인 `kp=0.1055`가 하드 선회에서 ~3° 잔류
sideslip을 남긴다. 단 (a) 이는 realistic·성능 *양 제어 모드에 똑같이* 작용하므로 채점 차이의
원인이 아니며, (b) 실 F-16 FLCS 사양이 비공개라 게인의 정밀 검증은 어렵다. 그래서 우리는 이를
*결함이 아닌 소소한 미해결 caveat*로 둔다. 이 잔여 역시 *대칭*이라 상대 비교 타당성을 해치지
않는다(Q3-3).

---

## Q5. "단일 초기조건·결정론인데 일반화·강건성은?"

**답변.** 평가는 *정준 완전중립 머지*(등에너지·anti-parallel beam) 한 조건으로 — 미분게임의
*barrier(V≈0)* 근방, 즉 가장 어려운 시작점을 의도적으로 택했다(§2.2·§7). 적 17 종이 BFM 교범의
*에너지·각도·반응성 3축 기저*를 span 하므로(§3.1), *전술 공간 전반*을 시험한다. 결정론은 *재현성*을
주며(모든 결과 .acmi+CSV+영상으로 더블체크 가능), 다양 기하·Monte-Carlo·고AoA 는 향후로 명시한다(§9).

---

## Q6. "그래서 결과는 fidelity 변경에 얼마나 민감한가? (경기 결과가 바뀌나)"

**답변.** **현재 경기 결과는 변하지 않았다.** fidelity 검증 중 시도한 controller 수정(turn-comp,
β=0)은 *효과가 없어 전부 원복*했고(레드팀, LAB 6), FLCS·물리는 *건드리지 않았다*. 회귀 확인:
`A3_LagAngler 100:95`, `anchor_ace 격추 100:0` — 문서값과 **동일**. 즉 fidelity *진단*은 했으나
*결과를 바꾸는 (물리) 변경은 없다.* 후속 점검(17장)에서 그 이유가 분명해졌다 — yaw 물리가 이미 충실해
*고칠 결손이 없었기* 때문이고, realistic 천장을 15→16/17로 끌어올린 것은 물리 변경이 아니라 *조건부
high-g*(g-cap 4.8g→8.2g, 9g 구조한계 내)라는 제어 권한의 정당한 확장이었다. 성능 17/17은 비교범
대형 수동 러더에서 추가 승이 온다(모두 env flag로 보존).

---

## Q7. "당신들의 기여가 엔진 충실도에 의존하나?"

**답변.** 아니다. 기여(설명가능 BT, 형상 상황분류, ETM, 전역 시퀀스)는 *의사결정 레이어*
(tactic·setpoint = BFM 교범)에 있고, 이는 *엔진-불가지(engine-agnostic)*다. "ETM 이 회피를 앞지른다",
"GA 가 D2 격파 시퀀스를 찾는다" 같은 결론은 *게임·결정 구조*에 관한 것으로, 합리적 6-DOF 충실도면
어디서나 성립한다. 충실도는 *결과의 정량값*(HP 마진)에 영향을 줄 수 있으나 *정성적 결론*은 불변이다.

---

## 리뷰어에게 제시할 자료 (재현·검증용)

- **검증 스위트**: `validation/{thrust_check,fidelity_axes,fidelity_modes,fidelity_maneuvers,fidelity_performance,doctrine_inputs}.py`
- **데이터(CSV)**: `validation/out/*.csv`
- **그래프(PNG)**: `validation/out/*.png` (추력·선회·축·모드·성능·교범입력)
- **영상**: `validation/out/turn_30deg.{gif,mp4}`(선회 항적 실제 vs 이론), `axes_steps.{gif,mp4}`(축별 응답)
- **`.acmi` fidelity 로깅(Tacview)**: 적·아군 β(sideslip)·α(AoA) + setpoint(`SetptHDG/Alt/CAS`) +
  명령 조종입력 + 실제 서보 위치(`AilSrv/ElevSrv/RudSrv`). 선회 중 \|β\|~3°·수평직진 β≈0 으로 skid
  물리 충실성을 직접 확인 가능(17장 §17.7).
- **종합 발견·control-fidelity 결론**: `docs/book/17_findings_prediction_and_fidelity.md`
- **레드팀·데이터 근거**: `docs/book/LAB_06_redteam.md`, `LAB_07_doctrine_and_data.md`

### 출처
- NASA TP-1538 F-16 풍동 데이터(`f16.xml` `<reference>`); Stevens & Lewis, *Aircraft Control and Simulation*.
- [F-16.net — Rudder use](https://www.f-16.net/forum/viewtopic.php?t=2119); [Falcon BMS — Dark Side of the FLCS](https://www.falcon-bms.com/wp-content/uploads/2021/08/FM_Developers_Notes_Part_4.pdf); [Wikipedia — F-16](https://en.wikipedia.org/wiki/General_Dynamics_F-16_Fighting_Falcon).
- FAA *Airplane Flying Handbook* (FAA-H-8083-3C) Ch.10.
