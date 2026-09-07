# LAB 4. 롤·피치·요 축별 조종면 충실도 — step-by-step (완전 재현)

이 실습서는 **각 조종면(aileron·elevator·rudder)이 자기 축(롤·피치·요)을 옳게 움직이는지** 를 가장
근본적인 방법 — *개루프(open-loop) 스텝 응답* — 으로 점검한다. LAB 3(협조선회)이 *제어기 닫힌 루프*
의 충실도였다면, 이 LAB 은 그 **아래층, 즉 조종면→기체 응답 자체**가 적절한지를 본다.

**핵심 질문:** "롤 피치 요에 따른 조종면이 적절한가?" → 두 가지로 답한다.
1. **부호** — +조종면이 그 축을 *옳은 방향*으로 움직이나? (반대면 제어 발산 = 치명적)
2. **권한(authority)** — 그 효과가 *충분히 큰가*? (미약하면 그 축 제어 불가)

모든 단계는 **결정론적**이라 명령을 그대로 따라 하면 *같은 숫자*가 나온다. 스크립트는
`new_match_engine/validation/fidelity_axes.py`.


## STEP 0 — 준비 (한 번만)

의존성(LAB 1.1과 동일). standalone JSBSim 이 필요하다.

```
python -m pip install jsbsim numpy scipy
```

검증 디렉터리로 이동:

```
cd new_match_engine/validation
```


## STEP 1 — 기준값 확보: 엔진 제어모델의 부호(B행렬)

"옳은 방향"의 기준을 먼저 정한다. 엔진이 *내부적으로 가정하는* 조종면 효과는 LQR 선형모델의
**B행렬**(제어효과 ∂(각가속도)/∂(조종면))에 들어 있다. 이 부호가 곧 제어기가 믿는 정답이고,
실제 기체 응답이 여기 *일치해야* 제어가 안정·적절하다.

다음을 그대로 실행(복사용):

```
cd new_match_engine/control
python -c "
import warnings; warnings.filterwarnings('ignore')
from lqr import GainScheduledLQR
from plant import STATE_ORDER, INPUT_ORDER
iP,iQ,iR=(STATE_ORDER.index(k) for k in ('p','q','r'))
uA,uE,uR=(INPUT_ORDER.index(k) for k in ('aileron','elevator','rudder'))
B=GainScheduledLQR([5000,15000,25000],[250,350,450]).build().grid[(15000.0,350.0)].B
print(f'B[p,aileron]  = {B[iP,uA]:+.3f}')
print(f'B[q,elevator] = {B[iQ,uE]:+.3f}')
print(f'B[r,rudder]   = {B[iR,uR]:+.3f}')
"
```

**기대 출력(재현값):**

```
B[p,aileron]  = +15.948      # +에일러론 → +롤율 (롤 권한 매우 큼)
B[q,elevator] = -4.350       # +엘리베이터 → −피치율(기수 내림). 당기려면 −엘리베이터
B[r,rudder]   = -0.841       # +러더 → −요율 (권한이 롤의 1/19 — 작다)
```

> 읽는 법: 크기(|B|)가 그 조종면의 *권한*, 부호가 *방향*이다. 이미 여기서 **러더 권한(0.84)이
> 에일러너(15.95)의 1/19** 임이 보인다 — 뒤 STEP 3에서 실측으로 확인된다.


## STEP 2 — 본 테스트 실행 (롤·피치·요 전부)

```
cd new_match_engine/validation
python fidelity_axes.py
```

**테스트가 내부에서 하는 일(한 축 기준, step-by-step):**

1. **트림** — 15000ft·350kts 수평 정상비행으로 맞춘다(`set_ic`→`trim`→5스텝 안정).
2. **기준 입력 기록** — 트림 상태의 조종면 입력 `u0` 를 저장.
3. **스텝 입력** — 그 축의 조종면 하나만 `u0 ± Δ` 로 바꾸고(다른 입력은 `u0` 고정), **개루프**로
   둔다(제어기 없음 — 순수 기체 응답).
4. **적분·기록** — 120Hz 물리로 T초간 적분하며 매 스텝 `p,q,r,φ,θ,ψ,α,β,Nz`·조종면 위치를 기록.
5. **+Δ 와 −Δ 둘 다** 반복 → 응답이 *부호 반전·대칭* 인지 확인(선형성·부호 일관성).
6. **판정** — (a) 측정 각가속도 부호 == `B`부호×스텝부호, (b) 1차응답 크기 ≥ 권한 임계.

축별 설정(스크립트 `AXES`):

| 축 | 조종면 | 스텝 Δ | 적분 T | 1차응답 | 권한 임계 |
|---|---|---|---|---|---|
| 롤 | aileron | ±0.40 | 1.0 s | 롤율 p | 30 °/s |
| 피치 | elevator | ±0.20 | 1.2 s | 피치율 q | 3 °/s |
| 요 | rudder | ±0.40 | 1.5 s | 요율 r | 1 °/s |

한 축만 보려면:

```
python fidelity_axes.py roll      # roll | pitch | yaw
```


## STEP 3 — 결과 읽기 (실측 재현값)

지금 실행하면 나오는 실제 출력(결정론 → 동일 재현):

### 롤 (aileron → 롤) — PASS

```
엔진 제어모델 B[p,aileron] = +15.948  → +조종면이면 p는 + (기대 부호)
   스텝  rate0.2s  rate_peak     Δφ     Δθ     Δα  Nz_peak  β_peak  r_peak
  +0.40    +50.71    +66.58  +56.6  -0.59  +1.04    -1.14   +1.93   +1.70
  -0.40    -50.44    -65.54  -55.9  -0.02  -2.18     3.12   +0.17   -1.36
판정: PASS   (부호일치=True, 권한충분=True)
```

- **부호 정확**: +에일러론 → +롤율(+66.6°/s), −에일러너 → −롤율. B(+)와 일치.
- **권한 강함**: 0.4 스텝에 1초 만에 롤율 ~66°/s, 뱅크 Δφ ≈ ±56°. F-16의 큰 롤 권한과 부합.
- **교차결합**: β_peak ≈ +1.9°(adverse yaw — 롤 시 약간의 옆미끄럼). 정상 범위.
- → **에일러론(롤)은 적절하다.**

### 피치 (elevator → 피치) — PASS

```
엔진 제어모델 B[q,elevator] = -4.350  → +조종면이면 q는 − (기대 부호)
   스텝  rate0.2s  rate_peak     Δφ     Δθ     Δα  Nz_peak  β_peak  r_peak
  +0.20     -6.12     -6.55   +0.0  -6.65  -3.75    -0.56   +0.00   +0.00
  -0.20     +6.04     +6.24   -0.0  +5.92  +3.32     2.30   -0.00   -0.00
판정: PASS   (부호일치=True, 권한충분=True)
```

- **부호 정확**: +엘리베이터 → −피치율(기수 내림), −엘리베이터(당김) → +피치율(기수 올림). B(−)와 일치.
- **하중계수 결합 정확**: 당기면(−0.2) α +3.3°↑, **Nz_peak 2.30g**(양력↑). 밀면 Nz↓(−0.56). 물리적으로 옳다.
- → **엘리베이터(피치)는 적절하다.**

### 요 (rudder → 요) — FAIL: 권한부족

```
엔진 제어모델 B[r,rudder] = -0.841  → +조종면이면 r는 − (기대 부호)
   스텝  rate0.2s  rate_peak     Δφ     Δθ     Δα  Nz_peak  β_peak  r_peak
  +0.40     -0.41     -0.41   +0.2  +0.01  -0.01     1.01   +0.38   -0.41
  -0.40     +0.41     +0.41   -0.2  +0.00  +0.01     0.98   -0.38   +0.41
판정: FAIL:권한부족   (부호일치=True, 권한충분=False)
```

- **부호는 정확**: +러더 → −요율. B(−)와 일치(반전 아님).
- **권한 미약**: 0.4 러더 스텝(큰 입력)에 요율 겨우 ±0.41°/s, 옆미끄럼 β ±0.38°. 임계 1°/s 미달.
- → **러더 부호는 옳으나 요 권한이 매우 약하다**(에일러론의 ~1/19, STEP 1의 B와 일치).

**종합:** `roll=PASS  pitch=PASS  yaw=FAIL`. 전 컬럼은 `validation/out/axes_all.csv`.


## STEP 4 — 해석: 무엇이 적절하고 무엇이 문제인가

| 축 | 부호 | 권한 | 결론 |
|---|---|---|---|
| 롤 (aileron) | 정확(+) | 강함(66°/s) | **적절** — 기체 롤 응답 정상 |
| 피치 (elevator) | 정확(−) | 충분(6.5°/s, Nz 2.3) | **적절** — 피치·하중계수 정상 |
| 요 (rudder) | 정확(−) | **미약(0.41°/s)** | **부호 OK·권한 부족** |

**가장 중요한 발견 — LAB 3과의 교차검증.** LAB 3(협조선회)에서 *INDI가 러더를 9.7°까지 꺾어도
β(옆미끄럼)가 안 줄던* 이유가 여기서 설명된다: **러더의 요 권한이 근본적으로 약해서**, 아무리
러더를 써도 요 모멘트가 충분히 안 생긴다. 즉 LAB 3의 "비협조(β)" 결함의 *뿌리*가 러더 권한이다.

> 정직한 단서: 부호가 세 축 모두 옳으므로 *기체모델이 뒤집힌 것은 아니다*. 롤·피치는 권한도 충분하다.
> 문제는 **요(러더) 권한**에 국한된다 — 그리고 이는 엔진 자신의 B행렬과도 일치한다(STEP 1). 따라서
> 후속 점검은 "F-16 러더가 원래 이만큼 약한가(실기 특성)" vs "JSBSim F-16 데이터/FLCS 게인 문제"를
> 가르는 것이다(STEP 5).


## STEP 5 — 시나리오·임계 바꾸기 (재현 가능한 변형)

**(가) 권한 임계 조정.** 1°/s 가 너무 빡빡/느슨하면 스크립트 `AUTHORITY_DPS` 를 고친다.

```python
AUTHORITY_DPS = dict(roll=30.0, pitch=3.0, yaw=1.0)   # 요 임계를 0.3 등으로
```

**(나) 스텝 크기·시간.** `AXES` 딕트의 `mag`(스텝)·`T`(적분시간)를 바꿔 더 큰 입력/긴 시간으로
러더 응답을 더 본다(예: 러더를 오래 주면 정상상태 옆미끄럼 β가 얼마까지 서는지).

```python
"yaw": dict(surf=_uRUD, mag=0.60, T=4.0, rate=_iR, b=(_iR,_uRUD), name="rudder→요"),
```

**(다) 비행조건.** 상단 `ALT_FT`/`VC_KTS` 를 바꿔 저속(러더 효과 ↓)·고속에서 권한 변화를 본다.

**(라) 러더 권한 근원 추적(고급).** 러더가 약한 게 *공력데이터*인지 *FLCS 게인*인지 보려면 JSBSim
프로퍼티를 직접 비교한다 — 명령(`fcs/rudder-cmd-norm`) 대 실제 타면(`fcs/rudder-pos-deg`)의 비를
보면 FLCS가 러더를 깎는지 알 수 있다.

```
cd new_match_engine/control
python -c "
import warnings; warnings.filterwarnings('ignore')
from plant import F16Plant
p=F16Plant(); p.set_ic(15000.0,350.0); p.trim(); p.step(5)
p['fcs/rudder-cmd-norm']=0.5
for _ in range(180): p.step(1)
print('cmd=0.5 -> rudder-pos-deg =', round(p['fcs/rudder-pos-deg'],3),
      ' beta-deg =', round(p['aero/beta-deg'],3),
      ' r-dps =', round(p['velocities/r-rad_sec']*57.2958,3))
"
```

**기대 출력(재현값):**

```
cmd=0.5 -> rudder-pos-deg = 1.471   beta-deg = 0.432   r-dps = -0.24
```

> **기대 출력(재현값):**
>
> ```
> cmd=0.5 -> rudder-pos-deg = 1.471   beta-deg = 0.432   r-dps = -0.24
> ```
>
> **결정적 단서 — 근원을 코드에서 확인.** 러더 명령 0.5(절반)인데 *실제 타면은 1.47°* 뿐이다.
> 원인은 `jsbsim_data/aircraft/f16/f16.xml` 의 native FLCS 요 채널(`<flight_control>` 안, 약 662–720행)
> 에 있다. 러더는 **직접 타면 명령이 아니라 yaw-load PID** 다:
> - `fcs/yaw-trim-error` = `rudder-cmd-norm + yaw-rate-norm + yaw-load-norm` (summer — *요율·요하중을 음피드백*).
> - `fcs/yaw-load-pid`(kp=0.1055, ki=1e-5) 가 이 오차를 0으로 만들도록 러더를 구동 → `rudder-pos-norm`.
> - `aerosurface_scale` 범위 ±0.524rad(=±30°).
>
> 즉 외부 제어기(LQR/INDI)가 보내는 `rudder-cmd-norm` 을 **native FLCS 의 요 댐퍼(yaw-rate/load 피드백)가
> 상쇄**한다 — 그래서 0.5 명령이 1.47°로 줄고, 요 권한이 미약하게 *측정*된다. 두 제어층(외부 + native
> FLCS)이 러더를 두고 겨루는 구조다.
>
> **함의·점검 지점:** (1) 협조는 외부 러더 명령이 아니라 *native FLCS 가 이미* 요율·요하중을 잡고 있으므로,
> INDI 의 `nu_r=−K_β·β−K_r·r`(`control/indi.py` 148행) 가 그 위에 *중복*으로 얹혀 충돌할 수 있다 —
> 외부 러더를 끄고 native FLCS 만으로 β 가 잡히는지 먼저 본다. (2) F-16 의 이 yaw-load PID 게인(kp=0.1055)
> 이 협조선회 β→0 에 충분한지(LAB 3 의 β 잔류와 연결) 점검한다.


## 재현성 메모

- **결정론**: JSBSim + 고정 IC + 고정 입력 → *매번 같은 숫자*. 위 표는 그대로 재현된다.
- **단일 진실**: 부호 기준(B행렬)과 측정(plant)이 *같은 모델/엔진*에서 나오므로 비교가 일관된다.
- **산출물**: `validation/out/axes_all.csv`(전 컬럼). 엑셀로 스텝 대 rate_peak 를 그리면 선형성·대칭이 보인다.
- **명령 요약:**

```
cd new_match_engine/validation
python fidelity_axes.py            # 롤·피치·요 전부 (표 + CSV)
python fidelity_axes.py yaw        # 요만
python fidelity_axes.py roll       # 롤만
# CSV: new_match_engine/validation/out/axes_all.csv
```


## 정리 — LAB 3 + LAB 4 의 종합 진단

| 점검 | 방법 | 결과 |
|---|---|---|
| 롤 조종면(aileron) | 개루프 스텝(LAB 4) | **적절** (부호+·권한 강) |
| 피치 조종면(elevator) | 개루프 스텝(LAB 4) | **적절** (부호−·하중계수 정상) |
| 요 조종면(rudder) | 개루프 스텝(LAB 4) | 부호 OK·**권한 약함** |
| 협조선회 전체 | 닫힌 루프(LAB 3) | elevator가 뱅크에 안 따라감(선회율↓)·비협조 β |

> 한 줄: **기체의 롤·피치 조종면은 부호·권한 모두 적절. 남은 두 관찰은 (1) 요(러더) 권한 미약,
> (2) 제어기가 선회 시 하중계수를 직접 안 만들어 elevator 가 뱅크에 안 따라감 — 으로 좁혀졌다.**
>
> ⚠ **후속 결론(17장 §17.3·CANON §7으로 해소).** 이 두 관찰은 *결함이 아니라 충실*로 판명됐다.
> (1) 러더의 약한 *수동* 권한은 실 F-16 특성이며(gun 교범 = roll+pull, 수동 러더 미세), 선회 협조는
> native FLCS `yaw-load-pid`가 ±1.0 전권한으로 *자동* 수행한다(러더 편향 ±30°·Cndr NASA TP-1538
> 일치). (2) 선회 elevator/하중계수 문제도 뱅크 g-cap(4.8g)에 묶였던 것이고, 조건부 high-g(8.2g,
> 9g 구조한계 내)로 해소됐다. 즉 "결함"으로 보였던 것은 *교범 러더 + 보수적 g-cap*의 정당한 귀결이다.
