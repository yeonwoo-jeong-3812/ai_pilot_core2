# 시작 가이드 — combat.py 하나로 다 돌리기 (새 파일·코딩 0)

이 문서 하나면 충분합니다. **파이썬 코드를 새로 쓸 일이 없습니다.** `combat.py` 라는 도구 하나를
*인자만 바꿔* 부르면, 결과 재현부터 적끼리 대결까지 다 됩니다. 당신이 손대는 건 **명령어 인자**와
(원하면) **적 `.yaml` 파일**뿐입니다.

> **결과를 정직하게 읽는 법 (먼저 알아두기).** 숫자·D2 서사는 [`CANON.md`](CANON.md)가 정본입니다.
> 우리 정책의 성적은 채점 조건에 따라 갈립니다. **realistic 16/17**(교범 러더 + 조건부 high-g) ·
> **성능 17/17**(비교범 대형 수동 러더) · **blind 16/17**(실전, 적 정보 0 자가분류 — D2만 무승부) ·
> **oracle 17/17**(유형 given, 상한 벤치마크). blind/realistic의 잔여 1승(D2)은 fidelity 결함이
> *아니라* D2를 제때 유형 분류하지 못하는 *정보한계*입니다 — D2 자체는 운동학적으로 격파 가능하고
> (oracle 17/17), 병목은 우리의 보수적 CLIMB 바닥 상수였습니다(CANON §6). 자세한 근거는 17장.


## 0. 가장 먼저 알아야 할 것 — 적과 우리 편은 형식이 다릅니다

| | 적 17명 | 우리 편 ("이긴 BT") |
|---|---|---|
| 형식 | **`.yaml`** (당신이 익숙한 그 트리) | **`.py`** 파이썬 코드 |
| 파일 | `opponents/*.yaml`, `opponents/zoo/*.yaml` | `bt/exp_e53_integrated_17.py` 의 `IntelPolicy` |
| 성격 | 손으로 짠 if-then 규칙 | 학습값 + 시퀀스 + 상태기계 |

- **우리 BT 파일은 *있습니다*.** `exp_e53_integrated_17.py` 가 바로 그 정책입니다(성능 17/17,
  realistic 16/17, blind 16/17, oracle 17/17 — 위 박스 참고). 단지 `.yaml` 이 아니라 `.py` 라서
  "안 보인다"고 느낀 것뿐이에요.
- **왜 우리만 `.py` 인가?** D2 는 "deck까지 강하추격 + overshoot 가드 + 시간/탐지 상태"(상태·시퀀스),
  A3 는 "거리 따라 모드 전환"(상태), base 는 "학습값 섞기"(계산) — `.yaml` 어휘(조건 35종·액션 37종)
  로는 못 적는 것들이라 코드여야 합니다. 적은 단순 if-then 이라 `.yaml` 로 충분하고요.
- **유형(D2/A3/base)은 적의 *행동 부류*입니다 — 적 `.yaml` 정체가 아닙니다.** IFF 는 관측된
  *궤적 형상*(rmin·aa_min·reopen, 50초 누적)으로 적이 *어떻게 싸우는지*를 스스로 분류합니다(blind,
  실전 기본). 예전의 "적 이름으로 유형 부여"(답 훔쳐보기)는 제거됐고, 지금은 *상한 벤치마크
  (oracle)* 로만 남아 있습니다. 그래서 *그렇게 행동하는 어떤 적*에게도 같은 독트린이 통합니다.


## 1. `exp_e0` ~ `exp_e53` 53개 파일은 *과거 기록*입니다 (안 건드림)

그 수많은 `exp_eNN_*.py` 는 정책을 **만들어 가던 연구 일지**입니다. 한 단계씩 실험한 기록이에요.

> 요리 비유: 냉장고에 **완성 요리(`exp_e53`)** 가 있고, 옆에 *개발하며 만든 시제품 52개* 가 같이
> 놓여 있는 것. 당신은 **완성품을 데우기만** 하면 됩니다. 새 실험을 *당신이* 만드는 게 아닙니다.


## 2. 당신이 하는 일은 딱 둘 — 인자 바꾸기 / `.yaml` 고치기

```
(1) 명령어 인자만 바꾼다       python combat.py vs A3_LagAngler   →   vs D2_LastDitch
(2) 적 .yaml 을 손으로 고친다   opponents/zoo/A3_LagAngler_06.yaml 의 숫자 수정 후 다시 실행
```

**파이썬 코드 작성 = 0.** 끝.


## 3. 명령어 치트시트 — "이걸 하고 싶으면 이 한 줄"

먼저 디렉터리 이동(한 번만):

```
cd new_match_engine/bt
```

| 하고 싶은 것 | 명령어 |
|---|---|
| 17적이 누구고 어느 .yaml 인지 본다 | `python combat.py list` |
| ★ **결과 재현** (우리 정책 대 17적 전원) | `python combat.py 17` |
| **blind 모드 (실전 16/17)** — 적 정보 0 자가분류 | `python combat.py 17 blind` |
| 우리 정책 대 **적 1명** | `python combat.py vs A3_LagAngler` |
| (시간 지정, 초 — 캐노니컬 300) | `python combat.py vs D2_LastDitch 300` |
| **적 대 적** (.yaml 대 .yaml) | `python combat.py duel anchor_ace A3_LagAngler` |
| 17x17 적끼리 상성 행렬 | `python combat.py rr 120` |
| 도움말 다시 보기 | `python combat.py` |

**적 이름 17개** (위 명령의 `<적>` 자리에 그대로):

```
anchor_simple  anchor_aggressive  anchor_defensive  anchor_ace
A1_PurePursuer  A2_GunTracker  A3_LagAngler  B1_EnergyFighter  B2_Extender
C1_TwoCircleRate  C2_OneCircleRad  C3_Lufbery  D1_Reactive  D2_LastDitch
D3_Scissors  E1_AdaptiveAce  E2_Passive
```


## 4. 결과 보는 법

- 화면에 **결과·HP** 가 바로 찍힙니다 (예: `A3_LagAngler: 판정승  HP 100:95  [독트린 A3]`).
- 매 경기 `replays/...` 폴더에 자동 저장: `match.acmi`(Tacview 재생) · `match.csv` · `report.txt` ·
  `plot.png`. 숫자(report)와 궤적(Tacview)을 함께 보면 됩니다 (LAB 1.5 참고).

기대 수치 (참고, **성능 모드** = 비교범 대형 수동 러더):

| 적 | 결과 | HP(우리:적) |
|---|---|---|
| anchor_ace, B1, C1, C2, C3, D1, E1, E2, defensive, B2 | 격추 | 100:0 |
| simple, aggressive, A1, A2 | 판정승 | 100:~93 |
| D3_Scissors | 판정승 | 100:~99 |
| **A3_LagAngler** | 판정승 | **100:95** (ETM) |
| **D2_LastDitch** | 판정승 | **100:94** (시퀀스) |

> 위 A3·D2 의 *판정승*은 **성능 모드**(비교범 러더) 기준입니다. **realistic(충실) 모드**(교범 러더,
> `INDI_RUD_MAX_CRUISE=0.2` + 조건부 high-g)에서는 A3 를 깨 **16/17** 이 됩니다(잔여 = D2). 이때
> 병목은 러더가 아니라 뱅크 g-cap 이었고(4.8g→조건부 8.2g, 9g 구조한계 내 = 충실), 조건부 high-g
> 로 A3 를 격파했습니다. blind 자가분류(실전)에서도 **16/17**(D2만 무). 그 D2 무승부는 fidelity
> 결함이 아니라 *분류 정보한계*이며, D2 는 oracle 에서 격파됩니다(**17/17**, deck-floor 수정 —
> CANON §6). 자세한 측정은 17장.


## 5. `.yaml` 을 직접 고쳐 보는 실험 (당신의 강점)

`list` 로 어느 `.yaml` 이 쓰이는지 확인한 뒤, 그 파일을 열어 숫자 하나만 바꿔 다시 돌려 보세요.

```
python combat.py list                         # A3 는 opponents/zoo/A3_LagAngler_06.yaml 를 쓴다
                                              # → 그 파일을 열어 commit: 4000 을 2000 으로 수정
python combat.py vs A3_LagAngler              # 다시 실행해 결과·궤적 변화를 본다
```

> 검증 루프: ① `.yaml` 한 줄 수정 → ② `combat.py vs <그 적>` 실행 → ③ Tacview 로 `.acmi` 눈으로 확인.
> "규칙 한 줄 → 거동 변화" 를 데이터와 궤적으로 함께 봅니다.


## 한 줄 요약

> **기억할 파일은 `combat.py` 딱 하나.** 적 = `.yaml`(고쳐도 됨), 우리 = `exp_e53`(그냥 실행).
> 새 실험을 만드는 게 아니라, **`combat.py` 를 인자만 바꿔 부릅니다.**
