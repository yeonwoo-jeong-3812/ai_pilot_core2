# LAB 2. 최종 정책 직접 돌리기 — 이긴 BT, 17 적 .yaml, BT 대 BT run_match

이 실습서는 최종 정책 `IntelPolicy` 를 17개 적 BT 와 *손으로 재현*하고, 17개 적 BT 를 *서로* 붙여 보는
데 집중한다. LAB 1 이 "BT 한 명을 .yaml 로 만들고 4적과 붙이는" 입문이라면, 이 LAB 은 "17개 전부를
.yaml 로 다루고, 최종 배포 정책(IntelPolicy)을 그 17적과 돌린다." 선수지식은 LAB 1(특히 1.2 .yaml
구조, 1.4 시나리오, 1.5 replay)이다.

**먼저 결과를 정확히 못박는다(검증된 3-모드 결과 — 17장 종합 참고).** 흔히 인용되는 "17/17"은 한
가지가 아니라 세 가지로 갈린다:
- **realistic(정직한 fidelity 천장) = 16/17.** env `INDI_RUD_MAX_CRUISE=0.2`(교범 러더)·both-INDI·
  high-g ON 에서 블라인드 자가분류로 싸운 결과. high-g 로 A3 를 깨 15→16 이 됐고, 잔여 무승부 1개는
  D2 뿐이다 — *운동학 벽이 아니라 분류 정보한계*(D2 의 강하-도주가 늦게 발현). 제어-fidelity(러더 ±30°,
  NASA TP-1538 Cndr, FLCS 자동 조정)가 충실함을 검증했다.
- **blind(블라인드 자가분류) = 16/17.** oracle 없이 관측 궤적형상으로 스스로 유형을 분류. 무승부 1개는
  D2 의 *정보한계* 다 — D2 의 정의적 행동(얕은 강하-도주)이 ~26초에야 발현해 조기식별이 불가하기 때문.
- **oracle(유형을 알려줄 때·상한 벤치마크) = 17/17.** 유형을 IFF/정찰이 미리 알려주는 *상한 벤치마크*
  이지 *실전 배포가 아니다*. 성능 17/17(전 매치)은 추가로 *비교범 대형 수동 러더*를 쓴다.

> 중요 구분. 정책은 적의 **행동 유형(archetype D2/A3/base)** 을 관측 궤적형상으로 분류한다 — 적의
> 특정 `.yaml` BT 정체를 알거나 추측하지 *않는다*. 과거의 "적 이름을 읽어 유형 부여"는 *답 훔쳐보기*
> 였고 제거됐다 — 그건 이제 oracle 벤치마크로만 남는다.

표기는 책 규약(별표 강조, 한자 없음)을 따른다. 명령은 프로젝트 루트 `ai-combat-sdk` 기준이다.

- LAB 2.1 무엇이 이겼나 — "이긴 BT"(IntelPolicy)의 정체
- LAB 2.2 17개 적 로스터 — 이름 → .yaml 파일 대응표 (★ .yaml 중심)
- LAB 2.3 한 줄로 재현 — blind(16/17, 실전형) 과 oracle(17/17, 상한)
- LAB 2.4 우리 최종 정책 대 *지정한 한 적* 대결
- LAB 2.5 적 BT 대 적 BT — 17명 중 *아무 둘이나* run_match (.yaml 대 .yaml)
- LAB 2.6 17 x 17 라운드로빈 (적들끼리 전원 대결)
- LAB 2.7 어려운 둘 — A3(ETM) · D2(전역 시퀀스) 단독 재현
- LAB 2.8 .yaml 을 직접 고쳐 다시 돌리기


## LAB 2.1 무엇이 이겼나 — "이긴 BT"(IntelPolicy)의 정체

먼저 헷갈리기 쉬운 비대칭부터 못박는다(LAB 1.4.0 의 17적 확장판이다).

- **적 17명 = .yaml BT.** 17개 적 조종사는 전부 `.yaml` 행동트리다(LAB 1.2 와 똑같은 형식 —
  Selector/Sequence/Condition/Action). 이 17개가 *BFM 전략공간 기저*다.
- **우리 편 = "이긴 BT" = `IntelPolicy`.** 최종 배포 정책은 .yaml 이 아니라
  `new_match_engine/bt/exp_e53_integrated_17.py` 의 **`IntelPolicy`** 클래스다. 이것은 학습된 base
  (AdaptivePolicy = 학습 value + 관측-차 보정) *위에* 적 행동유형별 독트린을 얹은 구조다. 매 BT 틱마다
  적 *행동 유형*에 맞는 **tactic(독트린)** 을 고르고, 나머지(guidance·autopilot·JSBSim·judge)는 엔진이
  굴린다. (적의 .yaml 정체는 보지 않는다 — 유형은 관측 궤적형상으로 *자가분류*한다. 위 인트로 참고.)

`IntelPolicy.select` 는 적 *행동 유형* 에 따라 t=0 부터 *파훼 독트린*을 적용한다 — 코드 그대로:

```
if   유형(자가분류) == D2 : deck(하드덱)까지 강하추격 + overshoot 가드(SMART_DIVE);
                            6단계 GA 시퀀스 LEAD>VERTICAL>SCISSORS>GUN>LAG>ETM 는 폴백
elif 유형(자가분류) == A3 : LEAD_PURSUIT 로 merge 강요 ↔ 근접시 ETM_TRACK(예측 조준)
else                     : base 정책(AdaptivePolicy = 학습 value + 관측-차 보정)
```
> 유형은 적의 `.yaml` 정체가 아니라 관측 궤적형상으로 *자가분류*한 **행동 archetype** 이다(blind).

즉 **"이긴 BT"는 17개 중 *15개는 base 한 정책*으로, *어려운 2개(A3·D2)만 전용 독트린*으로** 잡는다.
이 2개가 그동안 "단일 정책으로는 못 잡는다"던 두 회피자다 — 단, realistic(교범 러더·high-g ON) 하에서는
high-g 가 A3 를 깨 16/17 이 되고, 남는 무승부는 D2 뿐이다(운동학 벽이 아니라 분류 정보한계 — 17장 §3 참고).

> 정리. 이 LAB 에서 "BT 대 BT"라 하면 두 뜻이 있다 — (1) **우리 IntelPolicy(이긴 BT) 대 적 .yaml**
> (LAB 2.3·2.4), (2) **적 .yaml 대 적 .yaml** (LAB 2.5·2.6). 둘 다 같은 엔진(`Match.run`)에
> tactic 함수 둘을 꽂는 구조이고, 차이는 *side1 에 무엇을 꽂느냐*뿐이다.


## LAB 2.2 17개 적 로스터 — 이름 → .yaml 파일 대응표 (★ .yaml 중심)

`IntelPolicy` 가 싸우는 17적은 코드(`exp_e53_integrated_17.py` 의 `FULL` 리스트)에 *이름*으로 박혀
있고, 그 이름이 실제 어느 `.yaml` 로 풀리는지는 로더 `_opp(name)` 이 정한다. .yaml 에 익숙하다면 이
대응을 아는 게 핵심이다.

**로더 규칙(`bt/exp_e22_chaseforce.py` 의 `_opp`):**
- 이름이 `anchor_` 로 시작 → `opponents/<뒷부분>.yaml` (예: `anchor_ace` → `opponents/ace.yaml`).
- 그 외(아키타입) → `opponents/zoo/<이름>_*.yaml` 들을 정렬해 **딱 가운데(중앙값) 파일**을 고른다
  (`fs[len(fs)//2]`). 한 아키타입에 변주(_00.._NN)가 여럿이라, 그중 *대표 1개*만 평가에 쓴다.

아래가 17명 전원과, `_opp` 이 *실제로 로드하는* `.yaml` 이다(이 저장소 기준 실측):

| # | FULL 이름(코드) | doctrine 축 | 실제 로드되는 .yaml | oracle 결과(우리:적) |
|---|---|---|---|---|
| 1 | `anchor_simple` | anchor | `opponents/simple.yaml` | 판정 100:~93 |
| 2 | `anchor_aggressive` | anchor | `opponents/aggressive.yaml` | 판정 100:~93 |
| 3 | `anchor_defensive` | anchor | `opponents/defensive.yaml` | 격추 100:0 |
| 4 | `anchor_ace` | anchor | `opponents/ace.yaml` | 격추 100:0 |
| 5 | `A1_PurePursuer` | 각도(pure) | `zoo/A1_PurePursuer_05.yaml` | 판정 100:~93 |
| 6 | `A2_GunTracker` | 각도(gun) | `zoo/A2_GunTracker_06.yaml` | 판정 100:~93 |
| 7 | `A3_LagAngler` | 각도(lag) ★ | `zoo/A3_LagAngler_06.yaml` | **판정 100:95 (ETM)** |
| 8 | `B1_EnergyFighter` | 에너지 | `zoo/B1_EnergyFighter_06.yaml` | 격추 100:0 |
| 9 | `B2_Extender` | 에너지(이탈) | `zoo/B2_Extender_04.yaml` | 격추 100:0 |
| 10 | `C1_TwoCircleRate` | 선회(rate) | `zoo/C1_TwoCircleRate_03.yaml` | 격추 100:0 |
| 11 | `C2_OneCircleRad` | 선회(radius) | `zoo/C2_OneCircleRad_03.yaml` | 격추 100:0 |
| 12 | `C3_Lufbery` | 선회(지속원) | `zoo/C3_Lufbery_04.yaml` | 격추 100:0 |
| 13 | `D1_Reactive` | 반응 | `zoo/D1_Reactive_06.yaml` | 격추 100:0 |
| 14 | `D2_LastDitch` | 반응(spiral-dive) ★ | `zoo/D2_LastDitch_03.yaml` | **판정 100:94 (시퀀스)** |
| 15 | `D3_Scissors` | 반응(시저스) | `zoo/D3_Scissors_01.yaml` | 판정 100:~99 |
| 16 | `E1_AdaptiveAce` | 메타(최상) | `zoo/E1_AdaptiveAce_06.yaml` | 격추 100:0 |
| 17 | `E2_Passive` | 메타(최하) | `zoo/E2_Passive_01.yaml` | 격추 100:0 |

> ★ = 그동안 "단일 정책으로는 못 잡는다"던 두 회피자. 7번 A3, 14번 D2 만 전용 독트린이고 나머지
> 15명은 base 가 처리한다. 위 수치는 **oracle(유형을 알려줄 때) 상한 벤치마크**(격추 10 · 판정 7 =
> 17/17, 우리 HP 전부 100)다 — 실전 배포가 아니다. 실전 blind 자가분류는 16/17(D2 무승부),
> realistic 교범 러더(high-g ON)에서도 16/17(D2 만 무승부 — 분류 정보한계)이 정직한 천장이다(17장 종합 참고).

**확인 명령** — 어느 .yaml 이 로드되는지 직접 보고 싶으면:

```
cd new_match_engine/opponents/zoo
ls A3_LagAngler_*.yaml          # 12개 변주(_00.._11)가 보인다. _opp 은 가운데(_06)를 쓴다.
type A3_LagAngler_06.yaml       # (Windows) 실제로 평가에 쓰이는 A3 트리를 연다
```

이 트리(A3 _06)는 LAB 1.2 에서 본 구조 그대로다 — `BelowHardDeck>ClimbTo`, 근접+정렬이면
`GunAttack`, `DistanceAbove(4000)`면 `LagPursuit`(이게 A3 의 정체: 멀면 뒤를 겨눠 각을 안 내줌),
나머지 `Pursue`.


## LAB 2.3 한 줄로 재현 — blind(16/17, 실전형) 과 oracle(17/17, 상한)

핵심 표를 그대로 뽑아 본다. *우리 정책 대 17적 전원*을 한 번에 돌린다. **현재 CLI(중요):** 인자가
없으면 *블라인드 자가분류*(적 정보 0, 관측 궤적형상으로 스스로 유형 분류) = **실전 배포형, 16/17**.
인자 `oracle` 을 주면 *유형을 IFF/정찰이 알려줄 때의 상한 벤치마크* = **17/17(실전 아님)**.

```
cd new_match_engine/bt
python exp_e53_integrated_17.py            # 블라인드 자가분류(실전 배포형) → 16/17
```

기대 출력:

```
=== E53 통합 정책 [자가분류(실전)] 200s ===
opp               결과     HP 우리:적   유형
anchor_simple     판정승        100:93  base
...
A3_LagAngler      판정승        100:95    A3
...
D2_LastDitch      무            100:100   D2     ← D2 만 무승부(정보한계)
...
=== 격추10 판정6 패0 무1 → 승16/17 ===
```

> 왜 D2 한 판이 무승부(16/17)인가. **D2 의 정의적 행동(얕은 강하-도주)이 ~26초에야 발현**(코너에 몰려야 =
> last-ditch)하기 때문이다. 그 전엔 D2 가 다른 미진입 적과 형상이 겹쳐 조기 식별이 불가하다. 빠른감지를
> 넣어도 D2 는 t=0 위치 선점이 필요해 여전히 무승부 — 이는 *알고리즘 결함이 아니라 D2 행동의 후행성에서
> 오는 정보한계*다(17장 §6). 17/17 에는 oracle(유형 부여)이 필요하다.

**oracle 상한 벤치마크(유형을 알려줄 때)** 는 인자 `oracle` 을 준다 — *실전 배포가 아닌 상한 측정용*:

```
python exp_e53_integrated_17.py oracle      # 유형을 부여(상한 벤치마크) → 17/17
```

A3·D2 두 매치는 증거로 replay 가 저장된다 →
`new_match_engine/replays/research_final17/A3_LagAngler__A3_0001/` 등(LAB 1.5 처럼
`match.acmi`+`match.csv`+`report.txt`+`plot.png`).

> ⚠ oracle 은 유형을 *미리 알려주는* 상한이라 실전이 아니다. 실전 배포 천장은 위 무인자 16/17 이고,
> realistic 교범 러더(env `INDI_RUD_MAX_CRUISE=0.2`, high-g ON)에서도 high-g 가 A3 를 깨 **16/17 이
> 정직한 fidelity 천장**이며 남는 무승부는 D2 뿐이다(운동학 벽이 아니라 분류 정보한계; 러더 ±30°·NASA
> TP-1538 Cndr·FLCS 자동조정 — 충실 검증). 성능 17/17 은
> 추가로 *비교범 대형 수동 러더*를 쓴다. 전체 종합은 17장.

소요 시간을 줄이려면 duration 을 짧게 줄 수도 있다(코드 `main(dur=...)` 기본 200s). 빠른 점검은
아래 LAB 2.4 의 단건 스크립트가 낫다.


## LAB 2.4 우리 최종 정책(IntelPolicy) 대 *지정한 한 적* 대결

17명을 다 돌리지 말고 *한 명*만 빠르게 보고 싶을 때 쓴다. `exp_e53` 의 검증된 `IntelPolicy` 를 그대로
재사용하되, 적 이름 하나만 받아 1경기를 돌리는 얇은 스크립트다. 아래를
`new_match_engine/bt/run17_vs.py` 로 저장한다.

```python
"""run17_vs.py — 우리 최종 정책(IntelPolicy, 유형 부여=oracle 경로) 대 지정한 한 적 1경기.
usage: python run17_vs.py A3_LagAngler [duration_s]
       python run17_vs.py anchor_ace 200
적 이름은 LAB 2.2 표의 'FULL 이름' 17개 중 하나."""
from __future__ import annotations
import sys, os, math, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "control"))

import guidance
from exp_e53_integrated_17 import IntelPolicy           # ★ 이긴 BT 재사용
from exp_e22_chaseforce import _opp                     # 적 이름 → .yaml 로더
from exp_e7_champion import _train
from exp_e10_unified import DS_DA
from lqr import GainScheduledLQR
from autopilot import AutopilotConfig
from match import Match
from scenarios import spawn_adt_neutral
from obs import compute_obs
from replay import next_run_dir, write_acmi_plot, write_csv
from plot_match_3d_nme import analyze_match_files

opp = sys.argv[1] if len(sys.argv) > 1 else "A3_LagAngler"
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 200.0

# 적 유형 → 파훼 독트린 (oracle 경로: 유형을 *부여*해 단건으로 독트린 효과만 본다).
# ⚠ 이름으로 유형을 넣는 건 oracle(상한) 방식 — 실전 배포는 관측 자가분류(exp_e53 무인자)다.
it = "D2" if opp == "D2_LastDitch" else ("A3" if opp == "A3_LagAngler" else "base")

rf, tac = _train(DS_DA)
guidance.ETM_TAU = 2.0
gs = GainScheduledLQR([5000, 15000, 25000], [250, 350, 450]).build()
cfg = AutopilotConfig(KP_PSI=0.25); cfg.MAX_PSI_RATE = math.radians(30.0)

p1, p2 = spawn_adt_neutral()
pol = IntelPolicy(rf, tac, it)
m = Match(p1, p2, gs, cfg1=cfg, cfg2=AutopilotConfig(KP_PSI=0.10),
          control_hz=20, bt_hz=10, log_hz=60, controller1="indi", controller2="lqr")
r = m.run(tactic_fn1=lambda o: pol.select(p1, p2),
          tactic_fn2=lambda o: _opp(opp)(compute_obs(p2, p1)), duration_s=dur)
mk = "격추" if r.health2 <= 0 else ("판정승" if r.health1 > r.health2 else
     ("패" if r.health1 < r.health2 else "무"))
print(f"{opp}: {mk}  HP {r.health1:.0f}:{r.health2:.0f}  [독트린 {it}]")

rd = next_run_dir(os.path.join("..", "replays"), prefix=f"run17_{opp}")
ac = os.path.join(rd, "match.acmi"); cp = os.path.join(rd, "match.csv")
write_acmi_plot(r.log, ac, title=f"ours_vs_{opp}"); write_csv(r.log, cp)
try: analyze_match_files(ac, meta_path=cp, out_dir=rd, title=f"ours_vs_{opp}")
except Exception as e: print("  [analyze skip]", e)
print("replay:", rd)
```

```
cd new_match_engine/bt
python run17_vs.py A3_LagAngler          # 어려운 적 1 — ETM 으로 잡는다 (≈100:95)
python run17_vs.py D2_LastDitch          # 어려운 적 2 — deck 강하추격(폴백 6단계 시퀀스) (≈100:94)
python run17_vs.py anchor_ace            # 쉬운 격추 (≈100:0)
```

기대 결과: 한 줄 결과(결과·HP·적용 독트린)와 replay 폴더. LAB 2.2 표의 수치와 맞는지 대조하라.

> 핵심 관찰. `A3_LagAngler` 에 독트린 `A3`(ETM)가, `D2_LastDitch` 에 `D2`(시퀀스)가 붙고, 나머지는
> 전부 `base` 다. 이 단건 도구로 *유형별 독트린이 실제로 그 적에게만 발동*함을 눈으로 확인할 수 있다.
> 단, 이 도구는 유형을 *부여*하는 oracle 경로다(독트린 효과만 격리해 보려는 것). 실전 배포는 유형을
> 관측 궤적형상으로 *자가분류*하며(LAB 2.3 무인자), 그 천장은 16/17(D2 정보한계)이다 — realistic 교범
> 러더(high-g ON)에서도 16/17 이다(17장).


## LAB 2.5 적 BT 대 적 BT — 17명 중 *아무 둘이나* run_match (.yaml 대 .yaml)

이번엔 우리 정책 없이, **17 적 중 두 명을 서로** 붙인다(논문에는 없는, 로스터를 *서로* 가늠하는
실험). LAB 1.4.2 의 `my_bt_vs_bt.py` 를 *17명 이름 전부*로 일반화한 것이다 — 핵심 차이는 두 side 모두
`_opp(name)` 로 로드해 anchor 든 zoo 아키타입이든 이름만으로 부르는 것. 아래를
`new_match_engine/bt/bt17_vs_bt17.py` 로 저장한다.

```python
"""bt17_vs_bt17.py — 17 적 .yaml 중 둘을 서로 대결 (우리 정책 없음).
usage: python bt17_vs_bt17.py A3_LagAngler D2_LastDitch [duration_s]
이름은 LAB 2.2 의 17개(anchor_* 또는 아키타입) 중 하나. 둘 다 .yaml BT 다."""
from __future__ import annotations
import sys, os, math, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "control"))

from exp_e22_chaseforce import _opp                     # 이름 → .yaml 로더 (anchor/zoo 공통)
from lqr import GainScheduledLQR
from autopilot import AutopilotConfig
from match import Match
from scenarios import spawn_adt_neutral
from obs import compute_obs
from replay import next_run_dir, write_acmi_plot, write_csv
from plot_match_3d_nme import analyze_match_files

blue = sys.argv[1] if len(sys.argv) > 1 else "anchor_ace"
red  = sys.argv[2] if len(sys.argv) > 2 else "A3_LagAngler"
dur  = float(sys.argv[3]) if len(sys.argv) > 3 else 200.0

A = _opp(blue)        # 청군 BT (자기 관점 관측을 받아 tactic)
B = _opp(red)         # 홍군 BT
gs = GainScheduledLQR([5000, 15000, 25000], [250, 350, 450]).build()
cfg = AutopilotConfig(KP_PSI=0.25); cfg.MAX_PSI_RATE = math.radians(20.0)
p1, p2 = spawn_adt_neutral()
m = Match(p1, p2, gs, cfg1=cfg, cfg2=AutopilotConfig(KP_PSI=0.10),
          control_hz=20, bt_hz=10, log_hz=60)
r = m.run(tactic_fn1=lambda o: A(compute_obs(p1, p2)),
          tactic_fn2=lambda o: B(compute_obs(p2, p1)), duration_s=dur)
print(f"{blue} vs {red}: winner={r.winner} HP {r.health1:.0f}:{r.health2:.0f}")

rd = next_run_dir(os.path.join("..", "replays"), prefix=f"bt17_{blue}__{red}")
ac = os.path.join(rd, "match.acmi"); cp = os.path.join(rd, "match.csv")
write_acmi_plot(r.log, ac, title=f"{blue}_vs_{red}"); write_csv(r.log, cp)
try: analyze_match_files(ac, meta_path=cp, out_dir=rd, title=f"{blue}_vs_{red}")
except Exception as e: print("  [analyze skip]", e)
print("replay:", rd)
```

```
cd new_match_engine/bt
python bt17_vs_bt17.py C1_TwoCircleRate C2_OneCircleRad     # rate 대 radius — 선회전 정석 대결
python bt17_vs_bt17.py A3_LagAngler D2_LastDitch            # 두 회피자끼리 (보통 무승부)
python bt17_vs_bt17.py anchor_aggressive B2_Extender        # 공격형 대 이탈형
```

기대 결과: 승자·양측 HP 와 replay 폴더. `blue`/`red` 자리에 LAB 2.2 의 17개 이름 중 둘을 넣으면 어떤
조합이든 붙는다.

> 참고. 두 회피자(A3·D2)끼리는 *둘 다 커밋을 안 해서* 흔히 무승부로 끝난다 — 논문 §2.2 의 "barrier
> 위(V≈0)" 직관을 적끼리 대결로도 체감할 수 있다. 반대로 커밋형(aggressive 등) 대 회피형은 한쪽이
> 끌려나오며 갈린다.


## LAB 2.6 17 x 17 라운드로빈 (적들끼리 전원 대결)

로스터 전체의 *상성 표*를 한 번에 보고 싶을 때. 위 `bt17_vs_bt17` 의 로직을 이중 루프로 돌려 17x17
결과 행렬을 찍는다. `new_match_engine/bt/bt17_round_robin.py` 로 저장한다.

```python
"""bt17_round_robin.py — 17 적 .yaml 전원 라운드로빈(적끼리). 결과 행렬 + CSV.
usage: python bt17_round_robin.py [duration_s]   (기본 120s; 17x17=289경기라 짧게 권장)"""
from __future__ import annotations
import sys, os, math, csv, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "control"))

from exp_e22_chaseforce import _opp
from exp_e53_integrated_17 import FULL                  # 17 이름 (단일 진실)
from lqr import GainScheduledLQR
from autopilot import AutopilotConfig
from match import Match
from scenarios import spawn_adt_neutral
from obs import compute_obs

dur = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
gs = GainScheduledLQR([5000, 15000, 25000], [250, 350, 450]).build()

def duel(blue, red):
    A, B = _opp(blue), _opp(red)
    cfg = AutopilotConfig(KP_PSI=0.25); cfg.MAX_PSI_RATE = math.radians(20.0)
    p1, p2 = spawn_adt_neutral()
    m = Match(p1, p2, gs, cfg1=cfg, cfg2=AutopilotConfig(KP_PSI=0.10),
              control_hz=20, bt_hz=10, log_hz=60)
    r = m.run(tactic_fn1=lambda o: A(compute_obs(p1, p2)),
              tactic_fn2=lambda o: B(compute_obs(p2, p1)), duration_s=dur)
    if r.health1 > r.health2: return "W"      # 청군(행) 승
    if r.health1 < r.health2: return "L"      # 청군 패
    return "."                                 # 무

rows = []
print("blue\\red ".ljust(20) + " ".join(n[:6] for n in FULL))
for b in FULL:
    line = []
    for rd_ in FULL:
        line.append("-" if b == rd_ else duel(b, rd_))
    rows.append([b] + line)
    print(b.ljust(20) + "  ".join(line))

out = os.path.join(os.path.dirname(__file__), "..", "replays", "bt17_roundrobin.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["blue\\red"] + FULL); w.writerows(rows)
print("\nmatrix CSV:", out)
```

```
cd new_match_engine/bt
python bt17_round_robin.py 120        # 17x17 결과 행렬(W/L/무) + CSV 저장
```

기대 결과: 행=청군, 열=홍군의 W/L/. 행렬과 `replays/bt17_roundrobin.csv`. 한 경기 120s x 289 ≈ 다소
걸리니, 처음엔 더 짧게(예 `60`) 돌려 감을 잡아라. 이 행렬은 "어느 doctrine 이 어느 doctrine 에
강한가"를 *데이터로* 보여 준다(논문 §3.1 의 doctrine 3축 직관을 적끼리로 검증).

> 주의. 적끼리 라운드로빈은 *우리 정책 평가가 아니다*. 정식 점수는 반드시 LAB 2.3 의
> `exp_e53_integrated_17.py`(우리 IntelPolicy 대 17적, 중립 빔)로 본다 — 무인자 blind 16/17(실전),
> `oracle` 상한 17/17. 라운드로빈은 로스터의 내부 상성을 이해하는 *보조 실험*이다.


## LAB 2.7 어려운 둘 — A3(ETM) · D2(전역 시퀀스) 단독 재현

논문 §5·§6 의 두 파훼를 *따로* 재현한다.

**A3 — 형상분류 + ETM (§5).** LAB 2.4 단건 도구로 충분하다:

```
cd new_match_engine/bt
python run17_vs.py A3_LagAngler 200
#   기대: 판정승 ≈100:95, 독트린 A3. replay 의 plot.png 에서 ETM 이 lag 호를 앞질러
#         ATA<12° 를 만드는 구간(WEZ dwell)을 확인.
```

ETM 자체의 효과(논문 "일반 gun 4 dmg → ETM 6 dmg")를 더 파고들려면 `guidance.ETM_TAU`(예측 선행시간)
를 바꿔 가며 `run17_vs.py` 를 돌려 비교한다(스크립트 상단 `guidance.ETM_TAU = 2.0` 을 1.0/3.0 으로).

**D2 — 전역 시퀀스 최적화 (§6).** 6단계 시퀀스가 *어떻게 발견됐는지*는 전용 GA 스크립트다(현재 정책은
deck 강하추격 SMART_DIVE 가 1차 경로이고, 이 GA 시퀀스는 폴백으로 유지된다 — 17장 §17.10):

```
python exp_e52_d2_optimize.py 16 28
#   기대: 최선 순이득 +6, HP 100:94,
#         seq = LEAD > VERTICAL > SCISSORS > GUN > LAG > ETM
```

발견된 그 시퀀스를 *적용해 이기는* 것은 LAB 2.4 의:

```
python run17_vs.py D2_LastDitch 200       # 독트린 D2 폴백 = 위 6단계 시퀀스 (≈100:94)
```

**블라인드 16/17 형상분류기.** 적 유형을 *모르고* 관측 형상특징으로 스스로 가려내는 본격 분류기 모드
(적의 .yaml 정체는 보지 않고 *행동 archetype* 만 분류):

```
NME_TCLASS=40 python exp_e49_type_classifier.py 200
#   기대: 격추10 판정6 패0 무1(D2) → 16/17. (D2 한 판은 정보한계로 무승부 —
#         강하-도주가 ~26초에야 발현해 조기식별 불가. 알고리즘 결함 아님. 17장 §6.)
```

형상특징 분리성({A3,D2} 대 나머지 15, 거짓양성 0)은:

```
python exp_e48_type_features.py 50
```


## LAB 2.8 .yaml 을 직접 고쳐 다시 돌리기

당신은 .yaml 구조에 익숙하므로, *적을 손으로 바꿔* 우리 정책이 여전히 이기는지 보는 게 가장 빠른
학습이다. 두 가지 길이 있다.

**(가) 기존 17적 .yaml 변주 바꾸기.** `_opp` 은 아키타입의 *가운데* 변주를 쓴다(LAB 2.2). 다른 변주를
쓰게 하려면 그 아키타입 폴더에서 *가운데가 되도록* 파일을 더하거나, 간단히 단건 스크립트에서 특정
파일을 직접 로드한다. 예: A3 의 *공격적인* 변주(_11)를 직접 붙이려면 `run17_vs.py` 의 적 로드 줄을

```python
from yaml_bt import load_bt
B_fn = load_bt(os.path.join("..", "opponents", "zoo", "A3_LagAngler_11.yaml"))
# ... tactic_fn2=lambda o: B_fn(compute_obs(p2, p1))
```

로 바꾸면 된다(이름 대신 *파일 경로* 직접 지정).

**(나) 내 적 .yaml 새로 만들어 IntelPolicy 와 붙이기.** LAB 1.2 처럼 `MyFighter.yaml` 을
`opponents/zoo/` 에 둔 뒤, `bt17_vs_bt17.py`/`run17_vs.py` 의 `_opp(name)` 대신
`load_bt(".../zoo/MyFighter.yaml")` 로 그 파일을 직접 꽂는다. 우리 IntelPolicy 의 `base` 독트린이
*처음 보는 적*에게도 통하는지(논문 §8 "과적합 아님"의 핵심)를 손으로 시험할 수 있다.

> 검증 루프(권장). ① zoo 의 한 .yaml 을 열어 임계값 하나(예 A3 의 `commit: 4000`)를 바꾼다 →
> ② `run17_vs.py <그 적>` 로 결과·replay 확인 → ③ Tacview 로 `.acmi` 를 눈으로 더블체크(LAB 1.5.3).
> "규칙 한 줄 → 거동 변화"를 *데이터(숫자)와 궤적(눈)*으로 함께 본다.


## 정리 — 이 LAB 으로 익힌 것

1. **"이긴 BT"의 정체** — 최종 정책은 우리 `IntelPolicy`(exp_e53)이고, 적 17명은 .yaml BT 다. 어려운
   2개(A3·D2)만 전용 독트린(ETM·시퀀스), 나머지 15는 base. 결과는 3-모드: realistic 16/17(정직한
   천장)·blind 16/17(실전)·oracle 17/17(상한). 유형은 *행동 archetype 자가분류*(.yaml 정체 아님).
2. **이름 → .yaml 대응표** — anchor 4개(`opponents/*.yaml`) + 아키타입 13개(`zoo/<이름>_중앙값.yaml`),
   로더 `_opp` 규칙까지(LAB 2.2).
3. **세 가지 run_match** — (2.3) 우리 정책 대 17적 전원 한 줄 재현(무인자 blind 16/17 · `oracle`
   상한 17/17), (2.4) 우리 정책 대 지정 1적, (2.5/2.6) 적 .yaml 대 적 .yaml 단건·라운드로빈.
4. **어려운 둘 단독 재현**(2.7) 과 **.yaml 직접 수정 루프**(2.8).

### 자주 쓰는 명령 요약

```
cd new_match_engine/bt
python exp_e53_integrated_17.py            # ★ 블라인드 자가분류(실전) → 16/17 (D2 정보한계)
python exp_e53_integrated_17.py oracle     # 유형 부여 상한 벤치마크 → 17/17 (실전 아님)
python run17_vs.py A3_LagAngler 200        # 우리 정책 대 지정 1적 (단건, 유형 부여=oracle 경로)
python bt17_vs_bt17.py C1_TwoCircleRate C2_OneCircleRad   # 적 .yaml 대 적 .yaml
python bt17_round_robin.py 120             # 17x17 적끼리 상성 행렬 + CSV
python exp_e52_d2_optimize.py 16 28        # D2 6단계 시퀀스 GA 재현
NME_TCLASS=40 python exp_e49_type_classifier.py 200      # 블라인드 형상분류기 16/17
python exp_e48_type_features.py 50         # {A3,D2} 형상 분리성 검증
```

> 한 줄. 이 LAB 은 최종 정책(blind 16/17·realistic 16/17·oracle 17/17)·A3(ETM)·D2(시퀀스)·실행
> 아키텍처를 *명령으로* 잇는다 — "이긴 BT 가 17개 .yaml 적과 *실제로* 어떻게 도는지"를 손으로 재현하고,
> 17명을 서로 붙여 로스터를 가늠하는 도구까지 갖춘다. 결과의 정직한 천장과 그 fidelity 근거는 17장 종합.
