# LAB 9. yaml 도장 — 정답이 알려진 BFM 문제로 행동트리 훈련하기

이 실습서는 앞 장(3장 BFM 상황, 11장 의사결정 정책, LAB 1 직접 해보기)에서 배운 것을 하나의
반복 루프로 묶는다. 핵심 생각은 단순하다. 답이 이미 알려진 문제를 골라, 그 답을 내는 행동트리를
yaml 로 직접 짓고, 매치를 돌려, 기존 분석 도구로 결과를 읽고, 그 숫자를 다시 트리 수정으로 되먹인다.
답을 알고 있으니 틀리면 어디가 틀렸는지 바로 보인다.

이 문서는 docs/YAML_DUALITY_REVIEW_PLAN.md(yaml 제작·실행 원리 튜토리얼 북)의 짝 실습서다. 원리는
그 북에서, 손은 여기서 푼다. 명령은 프로젝트 루트 ai-combat-sdk 에서 실행한다고 가정한다. 표기는
책 규약을 따른다.

구성:
- LAB 9.1 도장 루프 — 여섯 단계와 각 단계의 도구
- LAB 9.2 되먹임의 핵심 — 분석 지표를 트리 수정으로 번역하는 표
- LAB 9.3 문제 1: 생존 (하드덱)
- LAB 9.4 문제 2: 1-서클 대 2-서클 선회전 (대표 문제, 정답이 기하로 정해짐)
- LAB 9.5 문제 3: 에너지 관리
- LAB 9.6 문제 4: 적 유형 대응
- LAB 9.7 채점 루브릭과 다음 단계


## LAB 9.1 도장 루프 — 여섯 단계

모든 문제는 같은 여섯 단계를 한 바퀴로 돈다. 각 단계는 이미 있는 도구를 쓴다. 새로 만들 것은 없다.

```
        +-----------------------------------------------------------------+
        |                                                                 |
        v                                                                 |
 1 짓기(Author) -> 2 돌리기(Run) -> 3 보기(Observe) -> 4 분석(Analyze) -> 5 진단(Diagnose)
   yaml 트리          매치 실행        승패 HP 이벤트      report plot csv    어느 규칙이 문제인가
   손 또는 bt-editor  run_match.py     Tacview acmi        WEZ dwell 에너지   지표를 규칙으로
        ^                                                                 |
        |                                                                 v
        +----------------------------  6 고치기(Edit)  <-------------------+
                                        트리의 조건 임계 우선순위를 한 곳만 바꾼다
```

| 단계 | 하는 일 | 도구와 경로 | LAB 1 대응 |
|---|---|---|---|
| 1 짓기 | yaml 트리 작성 | 손편집 또는 bt-editor (bt-editor/, npm run dev) | 1.2, 1.3 |
| 2 돌리기 | 매치 실행 | run_match.py(우리 대 적), my_bt_vs_bt.py(적 대 적) | 1.4 |
| 3 보기 | 승패와 이벤트 확인 | 콘솔 출력, Tacview 로 match.acmi 재생 | 1.5.3 |
| 4 분석 | 정량 지표 읽기 | report.txt(7층), plot.png(tools/plot_match_3d_nme.py), match.csv | 1.5.1, 1.5.2 |
| 4b 스캔 | 상황별 유리도, 적 도감 | situation_matrix.py, exp_opp_catalog.py | 1.4.3, 1.2.2 |
| 5 진단 | 지표를 규칙으로 번역 | LAB 9.2 대응표 | 11장, 8장 |
| 6 고치기 | 트리 한 곳 수정 | 1로 복귀 | — |

한 번에 한 곳만 고치는 것이 규칙이다. 여러 곳을 동시에 바꾸면 어느 수정이 효과를 냈는지 알 수 없다.


## LAB 9.2 되먹임의 핵심 — 지표를 트리 규칙으로 번역

도장 루프에서 지금까지 비어 있던 연결고리는 5 진단이다. report.txt 와 plot.png 에서 본 증상을,
yaml 트리의 어느 노드를 어떻게 고칠지로 번역해야 루프가 닫힌다. 아래 표가 그 다리다.

| 분석에서 본 증상 | 뜻 | 트리에서 고칠 곳 |
|---|---|---|
| WEZ dwell 이 0 에 가까운데 거리는 근접 | 조준각(ATA)을 못 맞춤 | 공격 Sequence 의 ATABelow 임계를 올리거나, GunAttack 앞에 LeadPursuit 를 둔다 |
| 하드덱 패배(report 판정 HARD DECK) | 바닥 방어 실패 | BelowHardDeck 임계를 올리고, 그 Sequence 를 Selector 맨 위로 |
| 내 비에너지 Es 가 계속 하락 | 과기동으로 에너지 소진 | SpecificEnergyAbove 게이트를 추가해 열세면 HighYoYo 나 확장 |
| 적에게 자꾸 물림(피격 dwell 증가) | 방어 전환이 늦음 | UnderThreat 의 aa 임계를 낮춰 더 일찍 발동, 방어 Sequence 우선순위를 올린다 |
| 중립인데 각을 못 땀 | 선회전 선택 오류 | IsOneCircle, IsTwoCircle 분기를 넣는다(LAB 9.4) |
| 특정 적한테만 짐 | 그 적 행동유형에 미대응 | exp_opp_catalog 로 적 패턴을 보고 전용 Branch 를 추가 |

report.txt 의 어느 줄을 보는지는 LAB 1.5.2 에 있다. 핵심은 결과(outcome), 교전성(WEZ 횟수와 dwell),
에너지(Es 와 bleed), 판정(격추 근거 또는 미교전 원인) 네 줄이다.


## LAB 9.3 문제 1 — 생존 (하드덱)

목표: 어떤 상황에서도 하드덱(1000ft) 아래로 떨어지지 않는 트리를 짓는다.

알려진 정답: 전투에서 가장 급한 규칙은 죽지 않는 것이다. 그래서 바닥 방어를 Selector 의 맨 위에
두고, 하드덱보다 여유 있는 높이에서 미리 상승을 건다. 이것은 우리 최종 예제 ours.yaml 의 FloorGuard
가지가 하는 일과 같다(YAML_DUALITY 북 Part 2). 즉 이 문제의 정답 구조는 예제의 축소판이다.

만들 트리(new_match_engine/opponents/zoo/Dojo1_Survivor.yaml):

```
name: Dojo1_Survivor
tree:
  type: Selector
  children:
    - type: Sequence              # 최상위: 바닥 방어
      children:
        - type: Condition
          name: BelowHardDeck
          params: {threshold_ft: 1500}
        - type: Action
          name: ClimbTo
    - type: Action                # 평소
      name: Pursue
```

돌리기(적이 우리를 아래로 끌고 내려가도록 방어 시작을 준다):

```
cd new_match_engine/bt
python run_match.py Dojo1_Survivor
```

어느 쪽이 내 트리인가(중요). run_match.py 에서 당신의 yaml 은 적(홍군) 자리에 들어가고, 우리 base
정책이 청군(us)이다(LAB 1.4.0 의 비대칭). 그래서 이 문제에서 당신 트리의 생존은 report.txt 의 opp
쪽 HP 와 판정으로 읽는다. 당신 트리를 청군(us)으로 놓고 report 의 us 쪽으로 채점하려면, LAB 9.4
처럼 my_bt_vs_bt.py 에서 A 자리에 당신 트리를 넣는다.

채점: report.txt 의 판정 줄에 당신 트리 쪽 HARD DECK 패배가 없어야 통과다. plot.png 의 해당 기체
고도 트레이스가 1500ft 아래로 내려가지 않으면 완벽하다.

되먹임 연습: threshold_ft 를 1200 으로 낮춰 다시 돌려 본다. 저고도로 유인하는 적을 만나면 하드덱을
찍는 경기가 생길 수 있다. LAB 9.2 표의 첫 하드덱 행을 따라 임계를 다시 올린다. 여유 높이가 곧 안전
마진임을 몸으로 익힌다.


## LAB 9.4 문제 2 — 1-서클 대 2-서클 선회전 (대표 문제)

이 문제가 이 실습서의 중심이다. 정답이 기하로 정해져 있어서, 트리가 옳은 선택을 하는지 숫자로
검증할 수 있다.

배경(3장 요약). 두 기체가 정면으로 지나친 뒤(머지) 서로를 다시 잡으려 선회할 때 두 갈래가 있다.
한쪽으로 같이 돌아 서로 코를 맞대는 one-circle 선회전과, 반대로 돌아 각자 원을 그리며 꼬리를 노리는
two-circle 선회전이다. 알려진 규칙은 이렇다.

- 선회반경이 작은(코너속도에서 더 팽팽히 도는) 쪽은 one-circle 이 유리하다. 반경 싸움이기 때문이다.
- 선회율이 높은(초당 더 많은 각도를 도는) 쪽은 two-circle 이 유리하다. 각속도 싸움이기 때문이다.

따라서 정답은 내 기체의 상대적 강점에 달렸다. 우리 엔진의 두 기체가 같은 F-16 이므로, 초기 속도와
에너지 배치로 강점을 만들어 준 다음, 트리가 그 강점에 맞는 서클을 고르는지 본다.

만들 트리(new_match_engine/opponents/zoo/Dojo2_CircleFighter.yaml). 머지 뒤 중립이면 서클 선택으로
가고, 그 앞에 안전과 공격 규칙을 우선순위로 둔다:

```
name: Dojo2_CircleFighter
tree:
  type: Selector
  children:
    - type: Sequence              # 안전
      children:
        - type: Condition
          name: BelowHardDeck
          params: {threshold_ft: 1500}
        - type: Action
          name: ClimbTo
    - type: Sequence              # 공격: 적 뒤 근접 조준이면 사격
      children:
        - type: Condition
          name: ATABelow
          params: {threshold_deg: 15}
        - type: Condition
          name: DistanceBelow
          params: {threshold_ft: 3000}
        - type: Action
          name: GunAttack
    - type: Sequence              # 중립 갈림 1: 반경 우위이면 one-circle
      children:
        - type: Condition
          name: IsOneCircle
        - type: Action
          name: OneCircleFight
    - type: Sequence              # 중립 갈림 2: 각속도 우위이면 two-circle
      children:
        - type: Condition
          name: IsTwoCircle
        - type: Action
          name: TwoCircleFight
    - type: Action                # 그 외
      name: Pursue
```

돌리기. 정면 머지에서 시작해야 서클 선택이 의미가 있다. LAB 1.4.2 의 my_bt_vs_bt.py 를 복사해 시작
시나리오를 spawn_headon 으로 바꾸고, 양쪽에 이 트리와 기준 적을 넣는다. 바꾸는 곳은 두 줄이다.

```
from scenarios import spawn_headon
...
A = load_bt(os.path.join("..", "opponents", "zoo", "Dojo2_CircleFighter.yaml"))
B = load_bt(os.path.join("..", "opponents", "aggressive.yaml"))
...
p1, p2 = spawn_headon(range_ft=6000.0)
```

```
cd new_match_engine/bt
python my_bt_vs_bt.py
```

채점(삼중 검증):
1. 이론 정답. 내 초기 강점(반경 우위인지 각속도 우위인지)에 맞는 서클을 골랐는가. plot.png 의 전술
   타임라인에서 머지 직후 OneCircleFight 또는 TwoCircleFight 중 옳은 쪽이 켜지는지 본다.
2. 궤적 형태. plot.png 의 3D 궤적과 원-적합 검출이, one-circle 이면 두 기체가 한 원을 공유하는 모양,
   two-circle 이면 두 개의 분리된 원(피겨8에 가까운 위상)을 보여야 한다.
3. 결과. 옳은 서클을 골랐다면 report.txt 의 WEZ dwell(us)이 상대보다 커야 하고, 승패가 WIN 이어야
   한다. 세 가지가 서로 맞물리면 정답이다. 하나라도 어긋나면 어디가 틀렸는지가 곧 진단이다.

되먹임 연습. 일부러 반대 서클을 강제해 본다(IsOneCircle 가지와 IsTwoCircle 가지의 액션을 서로
바꾼다). WEZ dwell 이 떨어지고 승패가 뒤집히는 것을 확인한다. 이것이 "정답을 알기에 오답도 만들어
볼 수 있다"의 의미다. 오답의 plot 을 정답의 plot 옆에 두고 비교하면 서클 선택의 효과가 눈에 박힌다.

시나리오 강점 바꾸기. spawn_param 으로 한쪽에 속도나 고도 우위를 준 뒤(LAB 1.4.4), 정답 서클이
바뀌는지 확인한다. 예: 내가 더 빠르면 각속도 우위 쪽으로 정답이 이동한다.


## LAB 9.5 문제 3 — 에너지 관리

목표: 에너지 열세일 때 무리한 교전 대신 확장이나 요요로 에너지를 회복하는 트리를 짓는다.

알려진 정답(3장 EM). 비에너지 Es 가 상대보다 낮으면, 그 상태로 선회전에 들어가면 더 빨리 소진해
불리해진다. 정답은 열세를 감지하면 상부 요요나 확장으로 에너지를 되찾은 뒤 다시 교전하는 것이다.

트리에 얹을 가지(공격 규칙 바로 위에 둔다):

```
    - type: Sequence              # 에너지 우위이면 상부 요요로 위치잡기
      children:
        - type: Condition
          name: SpecificEnergyAbove
          params: {threshold_ft: 0}
        - type: Action
          name: HighYoYo
```

주의: SpecificEnergyAbove 는 우위를 검사한다. 열세일 때 회복 기동을 걸려면 조건을 반대로 쓰는
가지(에너지 열세이면 확장)를 별도로 두거나, 임계를 조절해 우위가 아닐 때 fallback 이 확장으로
가도록 우선순위를 짠다. 어휘의 정확한 의미는 1장 조건표(SpecificEnergyAbove, IsEnergyAdvantage,
EnergyDiffAbove)에서 확인한다.

돌리기와 채점: 에너지 열세로 시작하도록 spawn_param 으로 내 고도나 속도를 낮춰 시작한다. 통과 기준은
plot.png 의 Es 트레이스가 초반에 회복 구간(상승 또는 확장)을 보인 뒤 교전으로 복귀하고, report.txt
에서 에너지 bleed 가 상대보다 완만한 것이다.

되먹임 연습: 회복 게이트 임계를 여러 값으로 스윕한다. 너무 보수적이면 교전을 아예 안 하고, 너무
공격적이면 회복이 안 된다. dwell 과 Es 회복량의 균형점을 데이터로 찾는다.


## LAB 9.6 문제 4 — 적 유형 대응

목표: 특정 행동유형의 적을 전용 가지로 파훼한다. 이것은 우리 최종 예제 ours.yaml 의 D2Branch,
A3Branch 가 하는 일의 축소판이다(YAML_DUALITY 북 Part 2, Part 7).

알려진 정답의 얼개. 먼저 상대가 어떤 유형인지 파악한다. 적 도감으로 각 적이 상황별로 어떤 전술을
내는지 표로 본다.

```
cd new_match_engine/bt
python exp_opp_catalog.py
```

예를 들어 계속 저고도로 강하하며 도망가는(dive-to-deck) 적이 있다고 하자. 이 적에게 순수 추격으로
따라 내려가면 하드덱 위험만 커지고 각은 못 딴다. 정답은 따라 내려가지 않고 위에서 각을 유지하다
기회를 잡는 것이다(우리 예제의 D2 독트린이 SMART_DIVE 로 3D 요격을 하는 이유가 이것이다).

전용 가지를 얹는다(고도나 강하율 조건으로 그 적을 식별해 대응 전술로 보낸다). 어떤 조건과 액션을
쓸지는 1장 어휘표에서 고른다(예: AltitudeBelow, ClosureRateAbove 로 식별, 대응은 상부 위치 유지).

채점: 그 적과의 경기에서 하드덱 패배 없이 WEZ dwell 을 확보하고 이기는지 본다. 다른 적들과의 경기가
망가지지 않았는지 배치 러너로 확인한다.

```
cd new_match_engine/bt
python exp_e14_roundrobin.py 300.0
```

되먹임 연습: 전용 가지의 우선순위를 위아래로 옮겨 본다. 너무 위에 두면 그 유형이 아닌 적에게도
잘못 발동하고, 너무 아래면 늦게 발동한다. 우리 예제가 FloorGuard 다음, base 앞에 유형 가지를 둔
이유를 재현으로 이해한다.


## LAB 9.7 채점 루브릭과 다음 단계

각 문제의 통과 여부는 report.txt 와 plot.png 의 같은 잣대로 매긴다. 주관이 들어가지 않게 숫자로 본다.

| 항목 | 어디서 보나 | 통과 기준 |
|---|---|---|
| 생존 | report 판정 줄 | HARD DECK 패배 없음 |
| 교전 | report 교전성 줄, plot WEZ dwell | WEZ dwell(us)이 상대보다 큼 |
| 정답 전술 | plot 전술 타임라인 | 이론이 준 정답 전술이 옳은 시점에 켜짐 |
| 결과 | report 결과 줄 | outcome 이 WIN(표준 평가는 300초) |
| 견고성 | exp_e14_roundrobin 표 | 다른 적과의 경기가 퇴보하지 않음 |

정식 성능 비교는 반드시 표준 중립 빔(spawn_adt_neutral, 300초)으로 한다(LAB 1.4.4 주의). 문제 2처럼
특정 시작 상황이 필요한 실습은 그 시나리오로 돌리되, 최종 점수는 표준 빔에서도 확인한다.

이 네 문제를 다 통과했다면, 학생의 트리는 우리 예제 ours.yaml 이 담은 네 요소(생존, 선회전 선택,
에너지 관리, 유형 대응)를 모두 갖춘 셈이다. 그 예제는 이 사다리의 꼭대기이자 정답지다. 게다가 그
예제는 .py 원본과 틱 단위로 동일함이 증명된 dual 이므로(YAML_DUALITY 북 Part 6), "손으로 짠 트리가
학습된 정책과 같은 수준까지 갈 수 있다"의 상한을 눈으로 보여 준다.

다음 단계로, LAB 1.5 의 도구로 자기 트리의 약점을 새 시나리오로 계속 노출시키며 루프를 돌리거나,
11장과 12장으로 넘어가 손 규칙 대신 데이터로 정책을 학습시키는 길을 밟을 수 있다.


## 정리 — 이 LAB 으로 익힌 것

1. 제작에서 평가까지를 하나의 여섯 단계 도장 루프로 묶었다.
2. 분석 지표를 트리 수정으로 번역하는 되먹임 표로 루프를 닫았다.
3. 정답이 알려진 네 문제(생존, 1-서클 대 2-서클, 에너지, 유형 대응)를 풀며 원리를 손으로 확인했다.
4. 모든 통과를 report 와 plot 의 숫자로 채점해, 우리 예제 ours.yaml 을 사다리의 꼭대기로 놓았다.

### 자주 쓰는 명령 요약

```
python new_match_engine/bt/run_match.py [적이름]     # 우리 base 정책 대 yaml 적
python new_match_engine/bt/my_bt_vs_bt.py            # 적 yaml 대 적 yaml (시나리오 바꿔가며)
python new_match_engine/bt/exp_opp_catalog.py        # 적 상황별 전술 도감
python new_match_engine/bt/situation_matrix.py       # 상황 대 전술 유리도 매트릭스
python new_match_engine/bt/exp_e14_roundrobin.py 300 # 여러 적 배치 대결
cd bt-editor && npm run dev                          # BT GUI 로 트리 그리기
```
