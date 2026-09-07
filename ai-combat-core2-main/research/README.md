# ai-combat-core2 — research/rollout-distillation 브랜치

[비공개] 1 vs 1 공중교전 환경 — AI 파일럿 경진대회 개최용 **V2**.
JSBSim F-16 위에 5계층 BFM 제어 스택(저수준 제어: 순수 INDI)을 올린 연구·경진 플랫폼.

이 브랜치에는 공식 엔진(main) 위에 우리 연구 결과를 얹었다. 핵심은 **되감기 학습**이다:
이 게임은 주사위가 없어서 같은 판을 다시 돌리면 100% 똑같이 흘러간다. 그래서 지는 판을
되감아 "그때 다르게 했다면 이겼는가"를 실제로 전부 돌려보고, 이기는 수가 나오는 상황
조건을 규칙으로 압축할 수 있다. 이 방법으로 상대 64종 × 양 진영 = 128판을 전부 이기는
**함수형 조종사 F**(상황 함수 16종 좌표 위의 조각별 정의 — 기저 함수 2개 + 국면 문장
12개, `agents/champion128.yaml`)를 만들었고, 그것을 만드는 파이프라인을 단일 명령으로
재실행하는 프레임워크(`research/framework.py`)와 문서 일체가 이 브랜치에 있다.

- **F 정식 명세**(함수형 규칙의 수식·상황별 해·실행 의미론): [docs/F_SPEC.md](docs/F_SPEC.md)
- **방법론 정식 명세**(원리·산출물 사슬·설계 근거·연구적 가치): [docs/PIPELINE_SPEC.md](docs/PIPELINE_SPEC.md)
- 방법과 성적의 전체 이야기: [docs/rollout_distillation_methodology.md](docs/rollout_distillation_methodology.md)
  (요약판: [docs/쉬운설명_전승프로젝트.md](docs/쉬운설명_전승프로젝트.md))
- 엔진 설계 결정(D1–D7): [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)

---

## 1. 공식 main 과 무엇이 다른가, 왜 다른가

> **최신 main 정합(2026-07) 이후.** 이 브랜치가 독자적으로 넣었던 비행 물리·관전
> 기능의 상당수를 main 도 자체 구현해 **수렴**했다 — 음의 G 구조 한계(−3.0G)+중력항,
> 기총 시각화, `dwell_s` 오버라이드, `presets/` 제거는 이제 양쪽 공통이라 더는 차이가
> 아니다. **하드덱 예측 가드는 main 을 따라 제거**했다(급강하 회복 오버라이드 — 판정
> 규칙 `HARD_DECK_FT` 1,000ft 는 존치). 평가 정책(perch 6,000ft·`neutral`·`no_contact`·
> 대항군 5종)도 main 을 채택. 아래는 **정합 후에도 남는 실제 델타**다.

| # | 바꾼 것 | 위치 | 왜 |
|---|---|---|---|
| 1 | 커스텀 조건·노드 | `tactics/custom.py` + `dsl.py` | "상대 체력이 몇 남았나"처럼 **기억(상태)이 필요한 판단** — commit/cooldown 선례의 개방형으로, 사용자가 조건·노드를 파이썬으로 정의해 트리에서 쓴다(§6). 기본 봉인 — 켜려면 `AICOMBAT_ALLOW_CUSTOM=1` |
| 2 | include 저장소-루트 폴백 | `tactics/dsl.py` | `agents/` 등 어디에 둔 트리도 저장소-상대 경로로 조각(`include:`)을 참조 — 내 위치→상위→저장소 루트 순 탐색 |
| 3 | 연구 하네스 | `research/` | 채점→패인 진단→되감기→규칙 압축→재검증 파이프라인과 128승 조종사. 엔진과 분리된 별도 폴더. 단일 진입점 `research/framework.py` |
| 4 | 문서·도구 한곳으로 | `docs/book` `docs/reference` `bt-editor/` | core-live 에 흩어져 있던 BFM 교재·분석 자료·웹 BT 편집기 이관. 챔피언 수학 정의 [docs/F_SPEC.md](docs/F_SPEC.md) |
| 5 | 배치 매치 러너 | `scripts/run_match.py` | 128판 검증 반복용 `--roster`(배치 채점·종료코드)·`--live`(Tacview 실시간 중계). (`--analyze`·기총빔·`dwell_s` 는 main 과 수렴) |
| 6 | 관전 계측 잔여 | `engine/match.py` `debrief/` | 자동 복기 그래프(`auto_debrief`)·실시간 중계 훅. 전부 기록 전용 — 결정론 재실행 diff 0 |
| 7 | 폴더·위생 | `roster/` `examples/` `pytest.ini` | 평가 로스터 64종+판 목록을 최상위 `roster/`로, 아키타입은 `examples/` 인라인(구 presets 픽스처는 `tests/fixtures/`). `pytest.ini` 로 수집 범위 고정 |
| 8 | 봉투 클립(계약 명시) | `guidance/bfm_guidance.py` | 조절 G 를 음의 하중 한계 안으로 클립 — 리미터 계약을 유도층에서도 명시 |

**승패 판정·비행 물리는 이제 main 과 같다** — 음의 G 한계·중력항이 양쪽에 들어와
정합됐다. 남은 델타는 참가자 기능 확장(#1·#2)·연구 하네스(#3~#6)·코드 위생(#7·#8)이며,
#1·#2 는 쓰지 않으면 아무것도 달라지지 않고 #6~#8 은 조종에 무영향이다.

> ⚠️ **128승 재검증 필요.** 비행 물리(하드덱 예측 가드 제거)와 평가 정책(perch
> 3,000→6,000ft·`neutral`·`no_contact`·대항군 5종)이 바뀌었으므로, 정본 성적표는 새
> 조건에서 재산출 전까지 무효다 — 상세는 [HARNESS.md](HARNESS.md). 전체 확인:
> `python -m pytest -q`.

## 2. 구조 — 5계층이 무엇을 하나

참가자가 만드는 것은 맨 위 L1(전술 판단)뿐이다. 그 아래 비행술은 전 참가자 공통 —
**"같은 기체, 같은 비행술, 다른 두뇌"**가 이 대회의 컨셉이다.

```
[L1 전술 트리]   20Hz   "지금 어떤 기동을 할까" — 참가자가 YAML 로 작성 (§5)
[L2 BFM 유도]    60Hz   그 기동을 교범대로 실현 — 어디를 조준하고 몇 G 로 당길지 (+하드덱 가드)
[L3 자동조종]   120Hz   조종면을 실제로 움직임 (INDI 제어)
[L4 물리]       120Hz   JSBSim F-16 6자유도 시뮬레이션
[L5 기록]       120Hz   위를 읽기만 해서 ACMI 녹화·이벤트·복기 그래프 생성
```

### 폴더 지도 — 역할당 폴더 하나

**엔진** (공식 main 그대로 + §1의 수정):

| 폴더 | 담당 |
|---|---|
| `aircombat/tactics/` | L1 — 트리 문법(`dsl`)·조건 20종(`conditions`)·커스텀(`custom`) |
| `aircombat/guidance/` | L2 — 교리 기반 조준·G 조절(`bfm_guidance`)·교범 수치(`doctrine`) |
| `aircombat/control/` | L3 — INDI·G 리미터·쿼터니언 자세 |
| `aircombat/fdm/` `jsbsim_data/` | L4 — JSBSim 래퍼와 기체 데이터 |
| `aircombat/geometry/` | 각도(ATA·AA·HCA, 기수 기준)와 사격 판정(`wez`) |
| `aircombat/engine/` | 경기 진행(`match`)·조종사 조립(`pilot`)·초기조건(`scenarios`) |
| `aircombat/debrief/` | L5 — ACMI 기록·자동 복기 그래프·실시간 중계 |
| `config/` | 엔진 기본값(`sim.yaml`)·기본 트리(`tactics.yaml` — 회귀 기준, 불변) |
| `scripts/` | 실행 도구 — 한 판(`run_match`)·리그(`run_tournament`)·그래프(`analyze_wez`) 등 10종 |
| `tests/` | 엔진 테스트 (`python -m pytest -q` → 170 = 엔진 162 + 파이프라인 불변식 8) |
| `sdk/` `tools/` `bt-editor/` | 제출 검증 SDK · ACMI 웹 뷰어 · 웹 트리 편집기 |

**트리(YAML)** — 만든 주체·용도별로 폴더가 다르다:

| 폴더 | 누가·무엇 |
|---|---|
| `agents/` | **참가자 제출물** — 128승 조종사 `champion128.yaml` (+동봉 `champion128/`) |
| `examples/` | 공식 예제 5종 (배우기용 — 요요 등 기동 조각도 여기 인라인으로 들어 있다) |
| `redteams/` | 공식 대항군 3종 |
| `roster/` | **평가 로스터** — 상대 64종 YAML + 판 목록 `all_128.txt` (§4.2 배치 러너의 기본 상대 폴더) |

**연구·산출물**:

| 폴더 | 담당 |
|---|---|
| `research/` | 연구 파이프라인 (구명 port_measure) — 도구 17종·`data/blueteam/`(문장·지문·덤프)·`data/redteam/`(공격 프로브)·`models/`·`results/`·`replays/`(증인·로그) — [research/README.md](HARNESS.md) |
| `docs/` | 방법론·설계(ARCHITECTURE)·자동화 계획·교재(`book/`)·레퍼런스 |
| `replays/` | 경기 녹화가 쌓이는 곳 (git 제외 — 재생성 가능) |
| `tmp/` `heritage/` | 공식 main 의 초기 설계 문서(불변) · 구 저장소 이력 스냅샷(로컬 전용) |

## 3. 받기와 설치

### 3.1 저장소 받기 (clone)

```bash
git clone https://github.com/rokafa-daslab/ai-combat-core2.git
cd ai-combat-core2
git checkout research/rollout-distillation      # 이 브랜치 (연구 결과 포함)
# 공식 엔진만 원하면 checkout 없이 main 그대로 사용
```

### 3.2 설치

수치 재현성을 위해 라이브러리 버전이 고정돼 있다. **반드시 가상환경에** 설치할 것.

```bash
# 방법 A — uv (빠름, 권장)
uv venv && uv pip install -r requirements.txt        # 실행은 `uv run python ...`

# 방법 B — 표준 venv
python -m venv .venv
# Linux/macOS: source .venv/bin/activate    Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt              # numpy, jsbsim, pyyaml, matplotlib
```

설치 확인: `python -m pytest -q` → 170개 통과(엔진 162 + 연구 불변식 8)가 나오면 정상.

## 4. 경기 돌리기

### 4.1 한 판 — `scripts/run_match.py`

```bash
# 128승 조종사로 한 판 (상대는 아무 트리나)
python scripts/run_match.py --scenario headon --blue agents/champion128.yaml --red redteams/red_attacker.yaml

python scripts/run_match.py --scenario headon --blue redteams/red_attacker.yaml --red examples/energy_fighter.yaml
python scripts/run_match.py --scenario headon --blue agents/my.yaml --red scripted:turn   # 스크립트 적기
python scripts/run_match.py ... --analyze        # 끝나고 사격·에너지·전술 그래프 3장 자동 생성
```

- 시작 조건: `--scenario headon` = 양측 15,000ft·350kt·11km 정면 대치(대회 기본).
  **`--seed N` 을 주면 시작 조건이 바뀐다** — 고도 12~18kft·속도·방위가 번호별로
  정해진 만큼 틀어진다(같은 번호는 항상 같은 조건이라 수정 전후 비교에 쓴다).
- `--red` 는 YAML(맞대전) 또는 `scripted:{turn|straight|extend|break}`.
- 결과물: `replays/` 에 녹화(.acmi)·콘솔 로그(.txt)·복기 그래프(png)가 자동 저장.
- 주사위가 없어서 같은 명령이면 결과도 항상 같다.

승패 규칙: 내 기수 기준 30° 원뿔 + 거리 500~3,000ft 안에 상대를 넣으면 체력이 깎인다
(정조준 2° 이내 초당 50, 10°/20°/30° 이내는 37.5/25/12.5). 체력 0 즉시 패배.
지면(1,000ft) 충돌·실속(100kt 미만 10초 누적)도 즉시 패배. 시간(300초) 종료 시 체력 많은 쪽 승.

### 4.2 여러 판 한번에 — `run_match.py --roster`

```bash
# 128승 조종사의 전 로스터 성적 재현 (64종 × 양 진영 = 128판, 결과 표 + 합계)
# 녹화는 기본 저장 — replays/roster_<일시>/ 에 판마다 .acmi + 복기 그래프
python scripts/run_match.py --blue agents/champion128.yaml --roster roster/all_128.txt

python scripts/run_match.py ... --roster ... --acmi-dir replays/my_batch   # 폴더 직접 지정
python scripts/run_match.py ... --roster ... --no-acmi                     # 녹화 끄기 (속도·용량 우선)
```

**roster 파일이 코드에서 읽히는 방식** (`scripts/run_match.py`의 `run_roster`):

1. 파일 전체를 읽어 **줄바꿈과 쉼표 둘 다** 구분자로 자른다 — 한 줄에 하나씩 써도 되고,
   `all_128.txt` 처럼 한 줄에 쉼표로 이어 써도 된다. 빈 항목은 무시.
2. 각 항목을 **마지막 `/` 기준**으로 `<상대이름>` 과 `<내 진영>` 으로 나눈다.
   - `<내 진영>` 은 `blue` 또는 `red` — **--blue 로 준 내 트리가 그 진영에 앉고**,
     상대가 반대편에 앉는다. 같은 상대와 양 진영을 다 겨루려면 두 항목을 쓴다.
   - `<상대이름>` 은 `--opponents-dir` 폴더(기본 `roster`)의
     `<상대이름>.yaml` 파일명이다. 다른 폴더의 상대를 쓰려면 `--opponents-dir` 로 바꾼다.
3. 시작 조건은 전 판 공통 — `--scenario`(기본 headon)·`--seed` 를 그대로 따른다.
4. 출력: 판마다 `상대/진영 · 승/무/패 · 체력차 · 종료 사유` 한 줄, 끝에 합계와 패배 목록.
   종료 코드는 전승이면 0, 패배가 있으면 1 (스크립트 연동용).

**roster 파일 만드는 법** — 그냥 텍스트 파일이다:

```text
# my_roster.txt — 예제 상대 3종과 양 진영씩 (6판)
attacker/blue
attacker/red
energy_fighter/blue
energy_fighter/red
two_circle/blue
two_circle/red
```

```bash
python scripts/run_match.py --blue agents/my.yaml --roster my_roster.txt --opponents-dir examples
```

연구용 러너(`research/proto_ledger_gate.py` — 관측 덤프·문장 실험 전용)는
[research/README.md](HARNESS.md) 참조.

### 4.3 녹화 보기 — 브라우저 뷰어

Tacview 설치 없이 브라우저에서 3D로 복기한다. 방법은 셋이고, **① 이 제일 편하다.**

```bash
# ① 매치 돌리면서 바로 열기 — 끝나자마자 크롬 창이 뜬다 (서버는 알아서 기동)
python scripts/run_match.py --blue agents/champion128.yaml --red roster/official_ace.yaml --view

# ② 이미 있는 녹화 하나 열기
python tools/acmi_viewer/launch.py replays/canon/roster_t3full_150/vs_anchor_ace_blue.acmi --t 40

# ③ 서버만 띄우고 목록에서 고르기 (replays/ 이하 전부 — 하위 폴더 포함)
python tools/acmi_viewer/server.py          # → http://127.0.0.1:7900
```

서버는 포트를 이미 물고 있으면 재사용하므로, 매치를 연달아 돌려도 탭만 새로 열린다.

**한국 지도 위에서 보기**(선택) — 교전 좌표가 이미 37°N/127°E(경기 남부 내륙)라
그 자리의 실제 지도를 지면에 깔 수 있다. 한 번 구우면 계속 쓴다:

```bash
python tools/acmi_viewer/make_map.py        # static/maps/ 에 생성 (git 제외)
```

지도가 없으면 종전의 격자 지면으로 자동 폴백한다. 실지형 고도는 일부러 쓰지 않는다 —
엔진 물리가 평지(하드덱 해수면 1,000ft 고정)라 산을 넣으면 판정과 화면이 어긋난다.

**URL 파라미터** — `?replay=canon/xxx/yyy.acmi` (특정 녹화) · `&t=40` (해당 시각으로 점프) ·
`&skin=real` (원본 F-16 도장. 사실적이지만 청/적 구분이 사라진다).

**화면에서 볼 것** — 기체는 F-16 실기 형상이고 상면이 팀색, 하면이 밝은 팀톤이라
배면비행이 한눈에 보인다. 카드의 `L1` 줄이 그 순간 내 트리의 어느 가지가 켜져 있는지
(디버깅의 핵심), 그 아래 `L2`~`L4` 가 유도·리미터·기체 상태. Gun WEZ 원뿔은 기수 정렬,
타임라인의 노란 틱이 피격·승패 북마크다. 좌·우 하단은 청/적 각각의 **1인칭 콕핏 뷰** —
시선이 기수(boresight)라 조준 링 2°/10°/20°/30°(피해 등급 경계)에 상대가 들어왔는지가
바로 읽힌다. 상단 `1인칭` 버튼으로 끈다. 자세한 항목은
[tools/acmi_viewer/README.md](../tools/acmi_viewer/README.md), 메시지 값의 뜻은
[docs/ACMI_MESSAGES.md](../docs/ACMI_MESSAGES.md).

Tacview 가 있으면 `.acmi` 를 바로 열어도 된다. 실시간 중계는 `run_match.py --live`.

### 4.4 일반해 분석기 — 파이프라인 한 번에 돌리기

이 브랜치의 핵심 도구다. **로그에서 전승 정책을 자동으로 만들어 내는 전 과정**이
단일 명령으로 돈다(원리·수학·설계 근거는 [docs/PIPELINE_SPEC.md](docs/PIPELINE_SPEC.md)).

```bash
# ① 가장 단순한 형태 — 문장 0 에서 시작해 전승까지 (콜드스타트)
python -m research.framework run --agent agents/my.yaml --roster roster/all_128.txt --fresh
```

무엇이 도는가: **불변식 검사 → 기저 채점 → (지표 스캔) → 폐루프(채점→되감기 수확→
규칙 귀납→재채점 반복) → 문장 다이어트 → 지문 저장 → YAML 번역 → 게이트(전판 실측
+ 두 런타임 패리티) → (검증·녹화·일반화) → 사슬 감사**. 각 단계는 산출물이 있으면
건너뛰므로(멱등), 중단돼도 같은 명령으로 재개된다.

```bash
# ② 제대로 된 연구 프로토콜 — 훈련/검증 분리 + 전 옵션
python -m research.framework split --seed 7                    # 층화 무작위 추첨(시드 기록)
python -m research.framework run --agent agents/my.yaml        --roster roster/train_s7.txt --val roster/val_s7.txt --tag s7        --fresh --scan --minproof --lofo

# ③ 성공 기준을 "불패"로 완화 + 강건 증인 + 확장 어휘 (막힌 반례를 뚫을 때)
CD_ALLOW_DRAW=1 CD_ROBUST=1 CD_ACTS="gun_pure,dive,extend,break,climb,lag,unload,e_extend" CD_DURS="2,4,8,12" python -m research.framework run --agent agents/my.yaml        --roster roster/train_s8.txt --val roster/val_s8.txt --tag s8 --fresh
```

**주요 옵션**

| 옵션 | 뜻 |
|---|---|
| `--tag <이름>` | 캠페인 격리 — 산출물·작업 폴더가 태그별로 분리(정본을 덮어쓰지 않음) |
| `--fresh` | 산출물이 있어도 전 단계 재실행 (없으면 완료분 건너뜀) |
| `--val <목록>` | 홀드아웃 성적 측정 — **수리에는 절대 쓰이지 않음**(일반화 측정 전용) |
| `--scan` | 지표 스캔 보고(어떤 좌표가 승패를 가르는지 AUC 전수) |
| `--minproof` | z3 로 문장 수 하한 증명 |
| `--lofo` | 가족-제외 교차검증(14가족) — 이월·회귀 행렬 |
| `--replay` | 전판 녹화 세대 생성 |
| `--dry` | 실행 없이 계획만 출력(어느 단계가 돌지 확인) |

**환경 변수(탐색 공간 조절)** — 막혔을 때 넓히는 순서대로:

| 변수 | 기본 | 뜻 |
|---|---|---|
| `CD_ACTS` | 기동 4종 | 되감기에서 강제할 기동 어휘(최대 8종) |
| `CD_DURS` | `4,8` | 개입 지속시간 후보 [s] |
| `CD_ALLOW_DRAW` | `0` | `1` 이면 **무승부도 성공**으로 인정(일반해의 하한 = 불패) |
| `CD_ROBUST` | `0` | `1` 이면 **승리-시간창이 가장 넓은** 증인을 우선 선택(강건성) |
| `CD_REUSE_WIT` | `1` | 기존 증인 재사용(수확 조건이 다르면 자동 재수확) |

#### 진단·감사 서브커맨드

```bash
python -m research.framework stats --log <결과.log>          # 승/무/패·HPΔ 분포·격추 시각
python -m research.framework diff --a <A.log> --b <B.log>    # 두 결과 전판 대조(회귀 검사)
python -m research.framework schedule --rules <문장.json> --dump <덤프.csv>   # 문장별 발화 기록
python -m research.framework timing --witness research/campaigns/witness        # 승리-시간창 폭
python -m research.framework audit --tag s8 --roster roster/train_s8.txt --val roster/val_s8.txt
```

`audit` 는 **산출물 사슬 11항목**을 점검한다 — 로스터→기저 판 수, 덤프 헤더=런타임
좌표 계약, 증인 수확 조건 신선도, 데몬 최종 라운드→문장 정본, 다이어트 손실 여부,
배포본 지문, 런타임 패리티, **훈련/검증 격리**까지. `run` 말미에 자동 실행된다.

#### 상대(시험지) 늘리기

```bash
python -m research.gen_opponents make --seed 100 --count 12   # 변이 상대 생성
python -m research.gen_opponents filter --seed 100            # 역량 필터(자명한 상대 탈락)
```

생성 상대는 수치 섭동뿐 아니라 **추격점 교체·수직 편향 주입**으로 기존 로스터에
없는 기동 방향을 만든다. 판정 지표는 승수가 아니라 **문장 수의 증가 곡선**이다 —
상대를 늘려도 문장이 안 늘면 일반해에 가까워지는 것이다.

### 4.5 초기조건 강건성 — 정책이 IC 를 넘어 통하는가

> ⚠️ **먼저 알아야 할 실측 결과.** 정본의 "150판 142승 8무 0패"는 **초기조건 하나**
> (headon 고정, 지터 없음)에서만 성립한다. IC 20종으로 넓히면 문장 정책 65.2% 대
> **문장을 끈 기저 70.2%** 로 **문장이 순손해**다(3,000판 대응표본, McNemar z=−7.12).
> 방어 국면(`perch_defense`)에서는 표본 전패다. 전문은
> [`docs/IC_ROBUSTNESS.md`](docs/IC_ROBUSTNESS.md).

정책 하나를 여러 IC(국면·시드)에서 병렬 채점한다. 매치는 서로 독립이고 엔진에
자생 난수가 없어(주입 시드 하나뿐) **병렬화가 결정론을 깨지 않는다** — 순차 45시간
짜리가 64코어에서 1시간 안에 끝난다.

```bash
# 챔피언을 headon 20시드에서 (3,000판, 20워커)
python -m research.sweep_ic --tag t3full_ic --seeds 1-20 --workers 20 \
       --rules research/data/blueteam/induced_rules_t3full_verified.json \
       --csv research/results/ic_sweep_t3full.csv

# 대조군: 문장을 끈 기저를 같은 IC 에서
python -m research.sweep_ic --tag plain_ic --seeds 1-20 --workers 20 --plain

# 국면까지 넓히기 (방어 국면 = 적이 내 6시 6,000ft·+100kt)
python -m research.sweep_ic --tag def_ic --seeds 1-8 \
       --scenarios headon,perch_defense,neutral --rules <문장.json>
```

집계는 단위별 승/무/패에 더해 **슬롯별 취약도**(몇 개 IC 에서 졌나)를 낸다 —
강건성의 소재지를 바로 짚기 위한 것이다. 이미 돈 단위는 건너뛰므로(멱등) 중단해도
이어서 돌릴 수 있고, `--summarize-only` 로 재집계만 할 수 있다.

**IC 격자 위에서 문장 유도하기.** 위 결과의 원인은 문장 하나하나가 아니라 합성
절차가 고정 IC 하나 위에서 돌았다는 것이므로, 데몬도 격자 위에서 돌 수 있다.

```bash
CD_TAG=grid CD_SCENARIOS=headon,perch_defense CD_IC_SEEDS=0,3,7,11 \
CD_ALLOW_DRAW=1 LG_BASEFN=gun20 python -m research.cegis_daemon
```

반례 식별자에 IC 가 붙고(`E1_AdaptiveAce_03/blue@perch_defense@s7`), 되감기는 그
칸의 IC 를 재현해 수색한다. obs 덤프 태그도 IC 를 구분하므로 **엄격분리가 다른
IC 의 승리 자취까지** 침범 금지 대상으로 삼는다. 시드 `0` = 지터 없는 기준 IC.

### 4.6 기동 계측 — 궤적에 무엇이 나타났나

교범 기동(루프·임멜만·스플릿S·급상승·급강하)을 자세 시계열에서 식별한다.

```bash
python -m research.bfm_taxonomy --dir replays/canon/roster_t3full_150   # 챔프/상대 동시
python -m research.bfm_taxonomy --sweep <녹화.acmi>                      # 임계값 민감도
python -m research.bfm_compare --a <녹화폴더A> --b <녹화폴더B> \
       --fired <문장.fingerprint.json>            # 발화판/휴면판 분리 대조
```

> **절대 개수를 인용하지 말 것.** 검출 게이트를 ±10° 흔들면 총 개수가 2.7배 변한다.
> 그리고 대조군 없이 세면 **기동 어휘가 없는 순수추격 스크립트도 같은 빈도로
> "임멜만"으로 집계된다** — 그래서 `classify_pair` 가 같은 매치의 상대를 항상 함께
> 잰다. 주장은 **차이로만** 성립한다. 실측 결과는
> [`docs/BFM_EMERGENCE.md`](docs/BFM_EMERGENCE.md).

## 5. 트리(YAML) 문법

### 5.1 파일의 큰 틀

```yaml
agent_name: MyPilot          # (선택) 녹화에 찍히는 내 이름
custom_module: my_nodes.py   # (선택) 커스텀 조건·노드 파이썬 파일 — §6
dwell_s: 0.3                 # (선택) 명령 전환 히스테리시스 [s] — 자체 래치가 있는 트리는 0
selector: [...]              # 트리 본체 (아래 노드들로 조립)
```

### 5.2 노드 9종

| 노드 | 쓰는 법 | 뜻 |
|---|---|---|
| `selector` | `{selector: [자식...]}` | 위에서부터 검사해 처음 성공하는 자식을 채택 |
| `sequence` | `{sequence: [자식...]}` | 전부 성공해야 성공 (조건들을 이어 붙일 때) |
| `condition` | `{condition: 이름}` 또는 `{condition: {name: 이름, 문턱값...}}` | 상황 검사. 문턱값 이름을 틀리면 즉시 에러 |
| `action` | `{action: {pursuit: ..., ...}}` | 기동 명령 (§5.4). 항상 성공 |
| `inverter` | `{inverter: 자식}` | 성공↔실패 뒤집기 |
| `commit` | `{commit: {duration_s, cooldown_s, name, child}}` | 자식이 성공하는 순간 **잠금** — duration 동안 그 기동을 유지하고, 끝나면 cooldown 동안 재진입 금지. 요요 같은 다단 기동, "6초 강제 후 1회성" 개입에 사용 |
| `cooldown` | `{cooldown: {wait_s, name, child}}` | 성공 후 wait 초 동안 재진입 금지 (떨림 방지) |
| `include` | `{include: my_fragments/yoyo.yaml}` | 다른 파일의 트리 조각을 끼워 넣기 (저장소-상대 경로, `..` 금지) |
| `custom` | `{custom: {name: 등록이름, 인자...}}` | 내가 정의한 노드 — §6 |

조립 예:

```yaml
selector:
  - sequence:                                       # 과속 접근이면 요요로 회피
      - condition: {name: overshoot_risk, closure_fps: 120, range_ft: 2500}
      - action: {pursuit: lag, name: yoyo_up, aim_above_ft: 750, lag_dist_ft: 2000}
  - include: my_fragments/yoyo.yaml                 # (선택) 따로 만든 트리 조각 끼워 넣기
  - commit: {name: rate_fight, duration_s: 2.0, cooldown_s: 2.0,
             child: {sequence: [{condition: merged},
                                {action: {pursuit: lead, max_g: true, name: entry}}]}}
  - action: {pursuit: pure, name: default_chase}    # 마지막엔 무조건 실행되는 기본 기동을 둘 것
```

### 5.3 조건 20종 (괄호 안이 문턱값과 기본값)

| 조건 | 언제 참인가 |
|---|---|
| `foe_threat` (aspect_deg=120) | 적이 나를 조준하고 있다 |
| `overshoot_risk` (closure_fps=150, range_ft=2000) | 가까운데 너무 빨리 접근 중 — 지나칠 위험 |
| `foe_extending` (closure_fps=0, range_ft=6000) | 적이 멀리서 도망 중 |
| `in_gun_envelope` (range_ft=3000, ata_deg=30) | 사격창에 들었다 |
| `nose_far` (ata_deg=60) | 내 기수가 적을 놓쳤다 |
| `energy_advantage` (min_ft=0) | 에너지(고도+속도 환산)가 min_ft 이상 우위 |
| `low_altitude` (floor_ft=4000) | 고도가 낮다 — 지면 주의 |
| `foe_above` / `foe_below` (min_ft=500) | 적이 그만큼 위 / 아래에 있다 |
| `behind_foe` (aspect_deg=60) | 내가 적 꽁무니 쪽에 있다 |
| `in_control_zone` (2000~3000ft·aspect 30·hca 30) | 적 후방의 이상적 사격 위치를 잡았다 |
| `merged` (range_ft=1500) | 초근접 — 스쳐 지나는 중 |
| `one_circle` / `two_circle` | 선회전 종류 (서로 반대 방향 / 같은 방향으로 돌기) |
| `closing` (min_fps=100) | 의미 있게 가까워지는 중 |
| `below_fighting_speed` / `above_…` (kcas=325/375) | 전투 속도 대역보다 느림 / 빠름 |
| `is_head_on` (hca_deg=150) | 정면으로 마주 보는 국면 |
| `is_offensive` / `is_defensive` (aspect_deg=60/120) | 내가 공세 / 수세다 |

구간 검사는 문턱값과 `inverter` 를 조합한다. 예) 거리 1,500~3,000ft:

```yaml
sequence:
  - inverter: {condition: {name: merged, range_ft: 1500}}   # 1,500ft 보다는 멀고
  - condition: {name: merged, range_ft: 3000}               # 3,000ft 안쪽
```

### 5.4 액션 항목 (여기 없는 키를 쓰면 에러)

| 키 | 값 | 뜻 |
|---|---|---|
| `pursuit` (필수) | `pure` / `lead` / `lag` | 조준점: 적 현재 위치(기수를 바로 겨눔) / 앞질러 요격점 / 꽁무니 뒤 |
| `max_g` | true/false | 한계까지 당길지 (기본은 교범식 부드러운 조절) |
| `name` | 문자열 | 녹화의 `ActiveNode` 에 찍히는 이름 — 꼭 붙일 것 |
| `aim_above_ft` | 숫자 | 조준점을 위(+)/아래(−)로 올려 수직 기동 유도 |
| `lead_time_s` | 숫자 | 얼마나 앞질러 조준할지 (0이면 사실상 기수-온; **사격각이 기수 기준이라 붙었을 땐 작을수록 유리**) |
| `lag_dist_ft` | 숫자 | 꽁무니 뒤 몇 ft 를 조준할지 |
| `mode` | `stable` / `control_zone` | 날개 수평 유지 추적 / 일정 거리 유지(자동 감속) |
| `cz_range_ft` | 숫자 | control_zone 의 목표 거리 (기본 2,500ft) |

## 6. 커스텀 조건·노드 만들기 (이 브랜치 추가 기능)

"상대 체력 추정치", "몇 초째 교전이 없나"처럼 **기억이 필요한 판단**을 트리에 넣는 방법.
기본 봉인(fail-closed) — 임의 파이썬을 실행하므로 대회 서버·SDK 는 무설정으로 안전하다.
신뢰된 리서치 환경에서만 `AICOMBAT_ALLOW_CUSTOM=1` 로 켠다. 봉인 상태에서 custom_module
트리를 로드하면 조용히 넘어가지 않고 거부 에러를 낸다.

```python
# my_nodes.py — 트리 YAML 과 같은 폴더에 둔다
from aircombat.tactics.custom import custom_condition, custom_node
from aircombat.tactics.node import Node, Status

@custom_condition("range_between")            # ① 기억 없는 조건: 함수 하나
def range_between(ctx, *, lo=0.0, hi=1e9):
    return lo <= ctx.range_ft <= hi

@custom_node("score_ledger")                  # ② 기억 있는 노드: 클래스
class ScoreLedger(Node):
    def __init__(self, *, dps=50.0):          # YAML 의 인자가 여기로 들어옴
        self.foe_dmg = 0.0                    # 기억은 self 에 (commit 노드와 같은 원리)
    def tick(self, ctx):
        # 볼 수 있는 것: ctx.range_ft, ata_deg, aspect_deg, closure_fps, kcas,
        #   energy_diff_ft, alt_gap_ft, alt_ft, my_health, hca_deg, t_s(경과시간) ...
        # 명령도 직접 내릴 수 있다(커스텀 액션): ctx.set_command("pure", True, "fire")
        ctx.trace.append(("ledger", round(self.foe_dmg, 1)))   # 복기용 기록을 남길 것
        return Status.FAILURE                 # "기록만 하고 지나가는" 패턴이면 실패 반환
```

```yaml
agent_name: LedgerBot
custom_module: my_nodes.py
selector:
  - custom: {name: score_ledger, dps: 50}     # 매 틱 장부 기록 (실패 반환 → 아래로 통과)
  - sequence:
      - condition: {name: range_between, lo: 1000, hi: 2000}   # 커스텀 조건도 같은 문법
      - action: {pursuit: pure, name: press}
```

지킬 것: **난수 금지**(재현성이 깨진다), 시간은 `ctx.t_s` 만 사용, `ctx.trace` 에 기록을
남겨 복기가 가능하게. 동작 예시는 `tests/test_custom_nodes.py`.

## 7. 128승 조종사와 연구 자료

- **128승 조종사**: `agents/champion128.yaml` — **함수-구간 3층 BT**: ①상황 함수
  12종 계산(`ledger_book`) → ②함수값 구간 문장 11개(구간 숫자가 YAML 에 그대로
  보임; 96개 승리판에선 전 문장 휴면) → ③구간 밖 일반해를 판독 가지 6개로 분해
  (게이트 거부·하드덱·다이브-대응·헤드온 억제·증류트리 — 임계값이 YAML 에 표시
  되고 정본 값과 일치가 로드 시점에 단언됨). 기저 트리는 joblib 모델이 아니라
  명시 분기 스냅(`base_tree.json`, 158리프)이라 제출물 런타임에 sklearn 이 필요
  없다. 상대 64종 × 양 진영 128판 전승(연구 런타임과 전판 HPΔ 일치). 실행법은 §4.1·§4.2,
  재료·도구는 [research/README.md](HARNESS.md),
  성적표는 [research/results/RESULTS.md](results/RESULTS.md)
- **어떻게 만들었나** (되감기 학습의 전 과정, 실패 사례와 한계 측정까지):
  [docs/rollout_distillation_methodology.md](docs/rollout_distillation_methodology.md)
- **자동화 파이프라인**(원리·산출물 사슬·설계 근거·연구적 가치): [docs/PIPELINE_SPEC.md](docs/PIPELINE_SPEC.md) — 실행법은 §4.4
- **교재**: [docs/book/](docs/book/) — F-16 BFM 제어를 처음부터 설명하는 연재 + 용어 정본(CANON)

## 8. 바꾸면 안 되는 것들

- L3 제어는 INDI 유지 (PID/LQR 로 바꾸지 말 것).
- L5(기록)는 읽기 전용 — 조종에 관여하는 코드를 넣지 말 것.
- 난수 금지 — 커스텀 노드 포함 모든 상태는 경기 시계(`ctx.t_s`)로만.
- `config/tactics.yaml`(기본 트리)은 회귀 시험의 기준이므로 불변.
