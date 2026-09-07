# LAB 8. Fidelity 놀이터 — 시나리오 만들고, 돌리고, 보기 (학생용)

이 LAB 은 **직접 시나리오를 만들고 충실도(fidelity)를 실험**하는 핸즈온이다. 앞 LAB(03~07)이
"무엇이 검증됐나"라면, 이 LAB 은 "직접 해보며 논다." 모든 도구는 `new_match_engine/validation/` 에
있고, 결정론적이라 같은 명령은 같은 결과를 낸다.

> **제어기 메모.** 프로젝트 기본 제어기는 **INDI**(양측 동일·대칭). 어느 실험이든 앞에 `NME_CTL=lqr`
> 를 붙이면 양측 LQR 로 바꿔 비교할 수 있다. 예: `NME_CTL=lqr python ...`.

- LAB 8.1 5분 워밍업 — 충실도 한눈에
- LAB 8.2 시나리오 만들기 ① 뱅크·고도·속도 바꾸기
- LAB 8.3 시나리오 만들기 ② 나만의 기본기동(.acmi replay)
- LAB 8.4 시나리오 만들기 ③ 5분 복합 프로파일 (가속·감속·상승·하강)
- LAB 8.5 교전 중 조종면이 reasonable 한가
- LAB 8.6 제어기 비교 (INDI vs LQR)
- LAB 8.7 도전 과제


## LAB 8.1 5분 워밍업 — 충실도 한눈에

```
cd new_match_engine/validation
python run_all_fidelity.py quick      # 추력 + 축별 조종면 + 동특성 모드
```

무엇을 보나: 추력 6/6 PASS(애프터버너 포함), 롤·피치·요 충실(요는 FLCS 자동 협조로 개루프 요율이
작게 보일 뿐 결함 아님 — LAB 5·17), 단주기/더치롤 안정. 숫자의 의미는 **LAB 5**(종합)에 있다.
개별로도 돌릴 수 있다:

```
python thrust_check.py            # 추력·애프터버너
python fidelity_axes.py           # 롤·피치·요 조종면 (부호·권한)
python fidelity_modes.py          # 단주기·장주기·롤·더치롤·나선
python fidelity_performance.py    # Ps·활공비·지속선회
```

> 결과는 화면 + `out/*.csv`. 그래프는 `python plot_fidelity.py` 로 `out/*.png` 생성.


## LAB 8.2 시나리오 만들기 ① — 뱅크·고도·속도 바꾸기

가장 쉬운 실험: **협조선회를 원하는 뱅크로** 돌려 이론과 비교.

```
python fidelity_maneuvers.py              # 두 제어기 x 뱅크 10/20/30/40
python fidelity_maneuvers.py indi 25 35 50 60    # indi, 뱅크 직접 지정
```

**바꿔 보기(놀이):**
- 인자로 뱅크 목록을 바꾼다: `... 5 15 25 35 45 55`.
- 고도·속도를 바꾸려면 파일 상단 상수: `ALT_FT`, `VC_KTS`.
- 허용오차(엄격도)는 `TOL` 딕트.

> 관찰 포인트: 뱅크가 커질수록 *선회율·Nz 가 이론보다 점점 더 벌어지는가*? 왜? → 답은 LAB 6(레드팀,
> 옆미끄럼 β 측력). `turn_fidelity.png` 그래프로 보면 한눈에.

**축별 스텝(롤/피치/요) 시나리오:**

```
python fidelity_axes.py roll      # 또는 pitch | yaw
```
스텝 크기·시간은 `AXES` 딕트의 `mag`·`T` 로 바꾼다.


## LAB 8.3 시나리오 만들기 ② — 나만의 기본기동 replay (Tacview)

기동을 .acmi 로 만들어 Tacview 3D 로 본다(이벤트 로그 포함).

```
python replay_maneuvers.py                 # 12종 전부(완전360°선회·climb·loop·split-s…)
python replay_maneuvers.py loop            # 하나만
python replay_maneuvers.py turn 45         # 45° 완전 선회
python replay_fidelity.py turn 30          # 짧은 30° 선회
```

→ `replays/maneuvers/*.acmi`, `replays/fidelity/*.acmi`. Tacview 로 열면 **좌측 Event Log** 에
▶ 기동명 + HIGH-G / INVERTED / TRANSONIC 등이 뜨고, **텔레메트리** 패널에 β(skid)·α(AoA)·
LoadFactor·setpoint(`SetptHDG/Alt/CAS`)·명령 조종입력·**실제 서보 위치(`AilSrv/ElevSrv/RudSrv`)**·
Throttle 이 나온다.

> **충실도 체크 포인트(LAB 17):** 수평직진에서 **β≈0**(물리적으로 정확), 선회 중 **|β|~3°** 가 보이면
> 그것이 곧 *충실히 모델링된 skid*(`CYb` side-force + FLCS)의 증거다 — 결함이 아니다. 명령 조종입력과
> 실제 서보 위치를 겹쳐 보면 native FLCS 의 자동 협조(러더)도 눈으로 확인된다.

**나만의 기동 추가(놀이):** `replay_maneuvers.py` 의 함수 하나를 복사해 입력 패턴만 바꾼다. 예 —
*고속 4G 당김*:

```python
def my_pull():
    def c(ts, p, u):
        u[0] = 1.0                      # full 추력
        if ts > 2: u[_uELEV] = -0.25    # 당김(개루프)
        return u
    return _run_open(c, 12.0, alt0=15000.0, v0=450.0)
# MANEUVERS 딕트에 "my_pull": my_pull 추가 → python replay_maneuvers.py my_pull
```

> 주의(현실성): 개루프 당김을 너무 세게/고속에서 주면 g 가 9g 를 넘는 *과도 오버슈트*가 난다(FLCS
> g-limiter 는 ~9g). 현실적 시나리오는 속도를 관리한다(LAB 의 aerobatic 참고).


## LAB 8.4 시나리오 만들기 ③ — 5분 복합 프로파일

여러 기동을 이어붙인 **연속 5분 비행**. 가속·감속·상승·하강이 *명시 라벨*로 구분된다.

```
python replay_profiles.py composite       # ★ 가속→감속→상승→하강→선회→저속 (라벨됨)
python replay_profiles.py                 # 5종 전부(composite·grand_tour·spiral·bfm·aerobatic)
```

→ `replays/profiles/*.acmi`. `composite` 를 Tacview 로 열면 Event Log 에:
```
▶ ACCEL 350->480kt → ▶ DECEL 480->280kt → ▶ CLIMB 15k->22k → ▶ DESCENT 22k->13k
→ ▶ LEFT TURN 30° → ▶ RIGHT TURN 45° → ▶ CLIMBING TURN → ▶ DESCENDING TURN → ▶ SLOW FLIGHT
```

**나만의 프로파일(놀이):** `replay_profiles.py` 의 `composite()` 를 복사해 세그먼트 리스트를 편집.
세그먼트 = `(종류, 함수, 초, "라벨")`:
- `("ap", straight(고도, 속도), 초, "라벨")` — 직진(고도·속도 setpoint).
- `("ap", turn(뱅크, +1/-1, 고도, 속도), 초, "라벨")` — 선회(+1=우, −1=좌).
- `("ap", spiral(뱅크, ±1, 시작고도, 고도율, 속도), 초, "라벨")` — 나선.
- `("open", 함수, 초, "라벨")` — 개루프(곡예).

`PROFILES` 딕트에 추가하면 `python replay_profiles.py 이름` 으로 실행.


## LAB 8.5 교전 중 조종면이 reasonable 한가

단순 기동이 아니라 **실제 교전(우리 정책 대 적)** 중 우리 조종입력이 합리적인지 본다.

```
cd new_match_engine/bt
python ../validation/engagement_check.py A3_LagAngler 150
python ../validation/engagement_check.py anchor_ace 100
```

점검: 입력 범위·**포화율**·chatter(진동)·변화율·**러더 사용량**·명령 대 실제타면 괴리.
→ `validation/out/engagement_<적>.png` 에 시계열(명령 cmd + 실제 servo).

> **러더 사용량 읽는 법(정정·LAB 17).** 성능 모드(기본 `INDI_RUD_MAX_CRUISE=1.0`)에서 INDI 가 큰
> *수동* 러더를 쓰는 건 **비교범**이지만(roll+pull 가 실 F-16 gun 교범), realistic 모드
> (`INDI_RUD_MAX_CRUISE=0.2`)에선 *수동* 러더가 교범대로 최소가 된다. 어느 쪽이든 INDI 러더 명령은
> `plant.py` → `fcs/rudder-cmd-norm` → **native FLCS** 를 통과하고, FLCS 의 yaw-load PID 가 ±1.0
> 권한으로 *자동 협조* 한다(이 자동 협조는 0.2 cap 과 무관). 즉 cap 이 막는 건 *수동 nose-skid*
> 러더뿐이다. → `.acmi` 의 β/α + 서보 컬럼으로 실제 협조를 직접 확인하라(선회 중 |β|~3° = 충실 skid).

**바꿔 보기:** 적 이름(LAB 2 의 17종), 시간(초)을 바꾼다.


## LAB 8.6 제어기 비교 (INDI vs LQR)

프로젝트 기본은 **INDI**(대칭). 어느 명령이든 `NME_CTL` 로 바꿔 비교한다.

```
python fidelity_maneuvers.py indi 30          # 협조선회(직접 지정)
python doctrine_inputs.py 30                   # 우리 입력의 교범 일치 (기본 INDI)
NME_CTL=lqr python doctrine_inputs.py 30       # LQR 로 비교
python replay_profiles.py composite            # INDI 프로파일
NME_CTL=lqr python replay_profiles.py composite # LQR 프로파일(덮어씀 — 따로 보려면 파일명 변경)
```

> 관찰: INDI 와 LQR 의 *러더 거동·협조(β)·선회율* 차이. 잔류 β 는 두 제어기 모두 충실한 skid 다(LAB 6·7).

> **★ 두 러더 모드 — 충실 vs 성능(정정·LAB 17).** 핵심: realistic 모드는 *결함이 아니라 정직한
> fidelity 천장* 이다.
> - **realistic(충실, 16/17):** `INDI_RUD_MAX_CRUISE=0.2`·high-g ON → *수동* 러더 최소(실 F-16 gun 교범:
>   roll+pull). high-g 가 A3 를 깨 16/17 이 되고 남는 무승부는 D2 뿐인데, 이는 **운동학 벽이 아니라
>   분류 정보한계이지 버그가 아니다.** = **정직한 fidelity 천장.**
> - **성능(17/17):** 기본 `INDI_RUD_MAX_CRUISE=1.0` → 추가 2승은 *비교범 대형 수동 러더(nose-skid)*
>   에서 온다.
> ```
> python combat.py vs A3_LagAngler                          # 기본 1.0 → 성능 모드(비교범 수동 러더)
> INDI_RUD_MAX_CRUISE=0.2 python combat.py vs A3_LagAngler  # 교범 최소 수동 러더(high-g ON) → A3 격파, D2 만 무승부(16/17)
> INDI_RUD_MAX_CRUISE=0.2 python ../validation/engagement_check.py anchor_ace 80   # 수동 러더 최소 확인
> ```
> 어느 모드든 INDI 러더는 native FLCS(yaw-load PID, ±1.0 자동 협조)를 통과한다 — 0.2 cap 은 *수동
> nose-skid* 만 제한한다. → '교범 최소(수동)러더 + 16/17' 은 **정직한 천장**, 17/17 은 비교범 러더의
> 대가다. 둘 다 env 로 보존된다. (참고: ETM KF·뱅크-선행 같은 *예측 개선*은 in-engine 에서 중립/악화
> 인데, dwell 이 제어-한계라서다 — "예측 더 잘하면 더 이긴다" 가 *아니다*. LAB 17 §17.5.)


## LAB 8.7 도전 과제

1. **뱅크 sweep 그래프:** `fidelity_maneuvers.py indi 10 20 30 40 50 60` → `plot_fidelity.py turn`.
   뱅크 대 선회율 결손이 *비선형으로 커지는가*? β 측력으로 설명하라(LAB 6).
2. **나만의 5분 프로파일:** 가속→하드선회→줌→다이브→저속→회복 을 라벨해 만들고, Event Log 로 확인.
3. **교전 조종면:** 17 적 중 셋을 골라 `engagement_check` 를 돌려, *어느 적에서 뱅크 g-cap 이 코 정렬
   각속도를 묶는가*(수동 러더는 교범상 0.2로 제한될 뿐 포화가 병목이 아님 — 17장 §17.5·CANON §7)?
   (회피기동이 심한 A3/D2 vs 커밋형 비교.)
4. **제어기 대결:** 같은 협조선회를 INDI/LQR 로 돌려 β·러더·선회율을 표로 비교.
5. **고AoA 탐험:** `slow_flight` 기동을 더 느리게(파일에서 200→160kt) 만들어 AOA 가 어디까지 가는지,
   FLCS alpha-limiter(28°)가 잡는지 Tacview 텔레메트리로 확인.


## 도구 요약

| 하고 싶은 것 | 명령 |
|---|---|
| 충실도 한 번에 | `python run_all_fidelity.py quick` |
| 협조선회(뱅크 지정) | `python fidelity_maneuvers.py indi 30 45 60` |
| 축별 조종면 | `python fidelity_axes.py roll\|pitch\|yaw` |
| 동특성 모드 | `python fidelity_modes.py` |
| 성능(Ps·활공·지속선회) | `python fidelity_performance.py` |
| 기동 replay(Tacview) | `python replay_maneuvers.py [기동]` |
| 5분 복합 프로파일 | `python replay_profiles.py composite` |
| 교전 중 조종면 | `python ../validation/engagement_check.py <적> <초>` |
| 교범 입력 일치 | `python doctrine_inputs.py 30` |
| 그래프 생성 | `python plot_fidelity.py` |
| 영상(GIF/MP4) | `python animate_fidelity.py` |
| 제어기 전환 | 앞에 `NME_CTL=lqr` (기본 INDI) |

> 산출물: `validation/out/`(CSV·PNG·GIF·MP4), `replays/{fidelity,maneuvers,profiles}/`(.acmi+csv).
> Tacview 로 .acmi 를 열어 3D·Event Log·텔레메트리로 본다. 카탈로그: `replays/fidelity/README.md`.
> 분석 근거: LAB 03~07, `FIDELITY_REVIEW_RESPONSE.md`.
