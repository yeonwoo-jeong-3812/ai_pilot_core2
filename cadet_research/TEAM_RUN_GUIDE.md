# 팀원 실험 실행 안내서 (한 명이 전부 실행)

> 2026-11-17 개정. 앞으로는 팀원 한 명이 **환경 검증부터 남은 실험 전부**를 돌린다. 처음 설치부터 결과를 올리는 데까지 순서대로 적었다.
> 실험 전체 흐름과 용어는 [EXPERIMENT_SUMMARY.md](EXPERIMENT_SUMMARY.md) 를 먼저 읽는다.
> 명령은 Windows 의 **Git Bash** 에서 친다 (PowerShell 도 대부분 같다). 각 단계의 위치 (`cd`) 를 확인한다.

## 0. 요청 요약

| 순서 | 할 일 | 경기 수 | 예상 시간 (PC 1대) | 시작 조건 | 결과물 |
|---|---|---|---|---|---|
| 1 | 환경 검증 | 10 | 10분 | 바로 | 자가 점검·crosscheck 출력 |
| 2 | 기존 결과 재현 검증 | 140 (표본 재생) | 30분 | 바로 | 재현 점검 출력, 분석 재계산 비교 |
| 3 | **넓은 상대 일반화** (가장 중요) | 2,688 | 약 4–5시간 | 태그 `prereg-bt-wide-v1` | 결과 CSV, 분석 보고서 |
| 4 | V1 분해 | 3,456 | 약 5–7시간 | 태그 `prereg-bt-v1split-v1` | 결과 CSV, 분석 보고서 |

- 3·4 는 연우가 계획서를 확인하고 태그를 만든 뒤에 돌린다. 태그가 없으면 코드가 실행을 거부한다.
- 시간은 PC1 실측 (약 5–7초/경기, `--procs 5`) 기준이며 PC 사양에 따라 다르다.
- **3 을 4 보다 먼저 돌린다.** 논문에서 가장 약한 부분이 일반화이기 때문이다.

**각 실험이 묻는 것**

- **넓은 상대 일반화:** 지금까지 일반화 근거는 처음 보는 상대 4종 (heldout) 과 6종 (newtypes) 뿐이었다. 그마저 이득이 작고 상대 한 종에 기댔다. 이번에는 저장소에서 쓸 수 있는 상대를 28종 (합격 점검 통과) 으로 늘린다. 판정도 경기가 아니라 **상대 단위**로 해서 "처음 보는 상대 일반에도 이득이 남는가" 를 다시 묻는다. 계획서: [PREREG_BT_ADDENDUM_WIDE.md](PREREG_BT_ADDENDUM_WIDE.md).
- **V1 분해:** 교범값 변형 V1 은 두 값을 함께 바꿨는데 V0 보다 승률이 낮았다. 하나씩 바꾼 V1a, V1b 로 어느 쪽이 원인인지 가린다. 계획서: [PREREG_BT_ADDENDUM_V1SPLIT.md](PREREG_BT_ADDENDUM_V1SPLIT.md).

## 1. 지킬 규칙

1. **코드와 설계 파일을 고치지 않는다.** 결과를 같은 조건으로 비교하려면 모두 같은 코드로 돌려야 한다. 막히면 멈추고 연우에게 알린다.
2. **결과 파일 (`games*.csv`) 을 손으로 고치거나 이름을 바꾸지 않는다.** 시간 초과 경기 처리도 연우와 상의한다 (§7).
3. **태그 전에는 3·4 를 돌리지 않는다.**
4. **`--force-dev` 를 쓰지 않는다.** 실행 전 점검을 건너뛰는 개발용 옵션이다.
5. **GitHub 에 push 하지 않는다.** 결과는 구글 드라이브로 보낸다 (§8).

## 2. 준비 (처음 한 번)

### 2.1 프로그램

- **Python 3.11.9** (다른 버전이면 실행 전 점검에서 거부된다). 설치할 때 "Add python.exe to PATH" 를 체크한다.
- **Git for Windows** (Git Bash 포함).

### 2.2 코드 받기

```bash
git clone -c core.longpaths=true -b bt-study https://github.com/yeonwoo-jeong-3812/ai_pilot_core2.git
cd ai_pilot_core2/cadet_research/kit
git fetch --tags origin
```

- `-c core.longpaths=true` 는 Windows 의 긴 경로 문제 때문에 꼭 필요하다.
- GitHub 에 접근할 수 없으면 구글 드라이브 `BT실험_공유/1_코드/` 의 최신 번들로 `git clone -c core.longpaths=true -b bt-study <번들 파일> ai_pilot_core2` 한다. 번들에는 올린 뒤에 생긴 태그가 없으므로 3·4 는 GitHub 로 받거나 연우가 새로 올린 번들을 쓴다.
- 구글 드라이브의 `정연우`, `김주혁`, `이주엽` 폴더는 각자의 작업 사본이다. 그 안의 코드로 돌리지 않고, 그 안에서 git 명령을 치지 않는다.

### 2.3 지금까지의 결과 풀기

구글 드라이브 `BT실험_공유/2_지금까지_결과/bt_out_results.zip` 을 내려받아 `cadet_research/kit/bt/` 에 푼다 (압축 안이 `out/...` 이라 `bt/out/` 에 들어간다). 2 단계 재현 검증과 3·4 의 비교 분석에 필요하다.

### 2.4 PC 설정

- **절전 끄기:** Windows 설정 → 시스템 → 전원 → 화면과 절전 모두 "안 함". 노트북은 전원을 연결한다.
- **`--procs` 정하기:** 동시에 돌릴 경기 수. 논리 코어 수 − 2 를 기준으로 하고, **메모리 8 GB 안팎이면 4 이하**로 한다. 지난 본실험에서 메모리가 부족한 노트북이 6 으로 돌다 시간 초과 경기가 33개 나왔다.
- 실행 중 다른 무거운 프로그램은 닫는다.

## 3. 실행기의 기본 동작

- `python bt/run_bt.py <θ 파일> --prefix <접두어> ...` 가 경기를 돌리고 결과를 CSV 에 한 줄씩 쓴다.
- **접두어:** 시드 묶음의 이름. 확증용 접두어 (`bt-confirm4`, `bt-confirm5` 등) 는 `--unlock-confirm` 과 그 계획의 태그가 있어야 돈다.
- **실행 전 점검 (자동):** (1) `bt/` 에 고친 파일이 없는가 (2) Python 3.11.9 인가 (3) crosscheck 해시가 맞는가 (4) 태그가 있는가. 하나라도 틀리면 "실행 거부" 와 함께 멈춘다.
- **이어서 돌리기:** 끊긴 뒤 같은 명령을 그대로 치면 기록된 경기는 건너뛴다.
- **`--dry`:** 경기 수만 센다. 실행 전에 꼭 한 번 확인한다.

## 4. 1 단계: 환경 검증 (위치: `cadet_research/kit`)

```bash
python --version                                     # Python 3.11.9
python -m pip install -r bt/requirements-analysis.txt
python bt/test_bt.py                                 # 마지막 줄 "bt 자가점검 통과" (1–2분)
python bt/analysis/test_analysis.py                  # 마지막 줄 "분석 시험 통과" (수 분)
python bt/crosscheck.py                              # "전체 해시" = fc6501b873df43e1
```

**crosscheck 란:** 정해진 경기 10개를 돌려 결과의 지문 (해시) 을 만든다. 이 엔진은 같은 조건이면 결과가 완전히 같으므로, 해시가 같으면 이 PC 의 결과를 앞선 결과와 합치고 비교할 수 있다. **다르면 더 진행하지 말고** 출력 전체를 연우에게 보낸다.

## 5. 2 단계: 기존 결과 재현 검증

### 5.1 표본 재생 (경기 결과가 이 PC 에서 똑같이 나오는가)

각 결과 파일에서 무작위 20경기를 다시 돌려 기록과 비교한다. 모두 "같다" (종료 코드 0) 여야 한다.

```bash
for f in bt/out/bt-main/games_main_lhs64.csv bt/out/bt-main/games_main_morris_r16.csv bt/out/bt-main-original/games.csv \
         bt/out/bt-confirm/games.csv bt/out/bt-confirm2/games.csv bt/out/bt-confirm2-heldout/games.csv bt/out/bt-confirm3-newtypes/games.csv; do
  echo "== $f"; python bt/verify_shard.py "$f" --n 20 --procs 4 | tail -3
done
```

### 5.2 분석 재계산 (같은 데이터에서 같은 보고서가 나오는가)

```bash
mkdir -p bt/out/recheck
python bt/analysis/confirm.py bt/out/bt-confirm/games.csv --baseline f2306532ecff --out bt/out/recheck
python bt/analysis/tuning.py --out bt/out/recheck
python bt/analysis/generalize.py --out bt/out/recheck
for r in confirm.md tuning_report.md generalize_report.md; do
  git diff --no-index --ignore-cr-at-eol --stat bt/out/analysis/$r bt/out/recheck/$r && echo "$r 같음"
done
git status --short bt                                # 아무것도 안 나와야 한다
```

- 세 보고서 모두 "같음" 이어야 한다. `bt/out/recheck/` 는 저장소 밖 폴더라 실행 전 점검에 영향이 없다.
- `git status --short bt` 에 뭔가 나오면 실험 전에 `git restore bt/out` 으로 되돌린다. 저장소에 올라간 보고서가 바뀌면 실행 전 점검이 거부한다.

## 6. 3·4 단계: 남은 실험 실행 (위치: `cadet_research/kit`)

### 6.1 시작 전 (각 실험마다)

```bash
git fetch --tags origin
git tag -l "prereg-bt-wide-v1" "prereg-bt-v1split-v1"     # 돌릴 실험의 태그가 보여야 한다
git checkout <태그 이름>                                    # 그 실험의 계획을 고정한 코드로 바꾼다
python bt/test_bt.py                                        # "bt 자가점검 통과"
git status --short bt                                       # 아무것도 안 나와야 한다
```

- `git checkout <태그>` 뒤 "detached HEAD" 안내가 나오는 것은 정상이다.
- **실험마다 그 실험의 태그로 checkout 한다.** 결과 행에 코드 버전 (`code_commit`) 이 기록되고, 분석이 이를 확인한다.

### 6.2 3 단계: 넓은 상대 일반화 (태그 `prereg-bt-wide-v1`)

```bash
python bt/run_bt.py bt/thetas/generalize4.csv --prefix bt-confirm5 --unlock-confirm --nseeds 8 --opponents wide --dry
python bt/run_bt.py bt/thetas/generalize4.csv --prefix bt-confirm5 --unlock-confirm --nseeds 8 --opponents wide --procs 4
```

- 결과: `bt/out/bt-confirm5-wide/games.csv`
- 경기 수 = 4 θ × 상대 28 × 24 = **2,688** (`--dry` 로 확인).

### 6.3 4 단계: V1 분해 (태그 `prereg-bt-v1split-v1`)

```bash
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --dry                       # 1,728
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --opponents heldout --dry   # 1,728
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --procs 4
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --opponents heldout --procs 4
```

- 결과: `bt/out/bt-confirm4/games.csv` (patched), `bt/out/bt-confirm4-heldout/games.csv` (heldout)

**진행 상황:** 화면에 `120/2976  900s 경과, 남은 예상 21000s` 처럼 찍힌다. 끝나면 `기록: ...csv (wall_clock 0경기)` 가 나온다. 창을 닫아도 되게 하려면 별도 창에서 돌리고, 로그를 남기려면 명령 끝에 `> run.log 2>&1` 을 붙인다.

## 7. 끊겼을 때와 끝난 뒤

**끊겼을 때**

- 컴퓨터가 꺼졌거나 창을 닫았으면, 같은 태그로 checkout 된 상태에서 **같은 명령**을 다시 친다. 결과 파일을 지우지 않는다.
- "실행 거부" 가 나오면 메시지를 그대로 연우에게 보낸다. 흔한 원인은 `bt/` 의 고친 파일 (`git status --short bt`), Python 버전, 태그 없음이다.

**끝난 뒤 확인 (예: 넓은 상대 일반화)**

```bash
python -c "import csv; r=list(csv.DictReader(open('bt/out/bt-confirm5-wide/games.csv', encoding='utf-8'))); print(len(r), 'games', sum(x['end_reason']=='wall_clock' for x in r), 'wall_clock', sum(x['end_reason']=='disqualified' for x in r), 'disqualified', {x['code_commit'] for x in r})"
```

- **경기 수**가 `--dry` 의 전체 경기와 같아야 한다.
- **wall_clock** (실제 시간 120초 안전장치에 걸린 경기) 이 0 이어야 한다. 0 이 아니면 연우와 상의해 규칙대로 처리한다: 원본 백업 → 그 줄만 삭제 → 같은 명령으로 재실행 (`PREREG_BT.md` §7).
- **disqualified** 가 하나라도 있으면 멈추고 연우에게 알린다.
- **code_commit** 이 하나뿐이어야 한다.

## 8. 분석과 결과 보내기

**분석 (위치: `cadet_research/kit`, 태그 checkout 상태 그대로)**

```bash
python bt/analysis/wide.py        # → bt/out/analysis/wide_report.md, wide_opponents.png
python bt/analysis/v1split.py     # → bt/out/analysis/v1split_report.md, v1split_diffs.png
```

분석 코드는 앞선 실험의 결과 파일 (2.3 에서 푼 것) 도 읽어 비교표를 만든다.

**보내는 곳:** 구글 드라이브 `BT실험_공유/3_결과_제출/<자기 이름>/` 에 실험마다 폴더를 만들어 올린다.

- 결과 CSV (이름 그대로) 와 분석 보고서·그림
- 1·2 단계 출력 (crosscheck 마지막 3줄, 재현 점검 결과, `python --version`)
- 실행 기록: 시작·끝 시각, `--procs`, 끊긴 적이 있으면 그 시각, `git log -1 --format=%h`

연우가 결과를 확인하고 보고서를 저장소에 커밋한다.

## 9. 막혔을 때

추측해서 고치지 말고 멈춘다. 아래를 연우에게 보낸다.

- 친 명령 그대로
- 화면에 나온 마지막 20줄
- `git log -1 --format=%h` 와 `python --version` 결과
