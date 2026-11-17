# 팀원 실험 실행 안내서

> 2026-11-17 작성. 남은 실험을 팀원이 직접 돌릴 수 있게, 처음 설치부터 결과를 올리는 데까지 순서대로 적었다.
> 실험 전체 흐름과 용어는 [EXPERIMENT_SUMMARY.md](EXPERIMENT_SUMMARY.md) 를 먼저 읽는다.
> 모든 명령은 Windows 의 **Git Bash** 또는 **PowerShell** 에서 친다. `cd` 위치가 중요하니 각 단계의 위치를 확인한다.

## 0. 먼저 알아 둘 규칙 다섯 가지

1. **코드와 설계 파일을 고치지 않는다.** 결과를 같은 조건으로 비교하려면 모두 같은 코드로 돌려야 한다. 막히면 고치지 말고 멈춘 뒤 연우에게 알린다.
2. **결과 파일 (`games*.csv`) 을 손으로 고치거나 이름을 바꾸지 않는다.** 예외는 시간 초과 경기 처리 하나뿐이고, 그것도 연우가 한다 (§6).
3. **태그가 생기기 전에는 돌리지 않는다.** 확증 실험은 계획을 고정한 태그가 있어야 돈다. 코드가 알아서 막는다.
4. **`--force-dev` 를 쓰지 않는다.** 실행 전 점검을 건너뛰는 개발용 옵션이다.
5. **GitHub 에 push 하지 않는다.** 결과는 구글 드라이브로 보낸다 (§7).

## 1. 지금 남은 실험

| 실험 | 상태 | 누가 | 이 안내서 |
|---|---|---|---|
| **V1 분해** (교범값 두 개 중 무엇이 승률을 떨어뜨렸나) | 계획 초안·코드·시험 준비 완료, **태그 대기** | 팀원 PC | §4 |
| 사후 계산 기록 (⑨ 의 red_energy 제외 계산) | 계산만 함, 파일 기록 대기 | 연우 | 경기 없음 |
| 3개 파라미터 요인 실험 | 건너뛰기를 권장 (아래 설명) | — | 준비 안 함 |

**V1 분해란:** ⑦ 에서 교범값 변형 V1 은 fight_kcas 와 threat_aspect_deg 를 **함께** 바꿨는데 V0 보다 승률이 낮았다. 두 값을 하나씩만 바꾼 V1a, V1b 를 돌려 어느 쪽이 원인인지 가린다. 계획서: [PREREG_BT_ADDENDUM_V1SPLIT.md](PREREG_BT_ADDENDUM_V1SPLIT.md).

**3개 파라미터 요인 실험을 건너뛰는 이유:** "중요 3개 조정이 새 상대에게도 이득을 유지하면" 하기로 했는데, ⑨ 에서 이득이 작고 상대 한 종에 크게 의존했다. 팀이 다시 하기로 하면 새 계획서부터 만든다.

## 2. 처음 한 번만 하는 준비

### 2.1 프로그램 설치

- **Python 3.11.9** (다른 버전이면 실행 전 점검에서 거부된다). 설치할 때 "Add python.exe to PATH" 를 체크한다.
- **Git for Windows** (Git Bash 포함).

### 2.2 코드 받기

**방법 A (권장): GitHub 에서 받기**

```bash
git clone -c core.longpaths=true -b bt-study https://github.com/yeonwoo-jeong-3812/ai_pilot_core2.git
cd ai_pilot_core2/cadet_research/kit
git fetch --tags origin
```

`-c core.longpaths=true` 는 Windows 의 긴 경로 문제 때문에 꼭 필요하다.

**방법 B: 인터넷이 안 되거나 GitHub 접근 권한이 없을 때 (구글 드라이브의 번들)**

구글 드라이브 `BT실험_공유/1_코드/` 의 `ai_pilot_core2_bt-study.bundle` 을 내려받아 같은 폴더에서:

```bash
git clone -c core.longpaths=true -b bt-study ai_pilot_core2_bt-study.bundle ai_pilot_core2
cd ai_pilot_core2/cadet_research/kit
```

번들은 올린 날 기준의 저장소 전체 (기록·태그 포함) 다. **나중에 생긴 태그 (예: `prereg-bt-v1split-v1`) 는 들어 있지 않다.** 태그가 생긴 뒤에는 방법 A 를 쓰거나 연우가 새로 올린 번들을 받는다.

> **구글 드라이브의 `정연우`, `김주혁`, `이주엽` 폴더는 각자의 작업 사본이다.** 그 안의 코드로 돌리지 말고, 그 안에서 git 명령을 치지 않는다 (다른 저장소를 가리키는 파일이 있다).

### 2.3 패키지 설치와 자가 점검 (위치: `cadet_research/kit`)

```bash
python --version                                     # Python 3.11.9 이어야 한다
python -m pip install -r bt/requirements-analysis.txt
python bt/test_bt.py                                 # 마지막 줄 "bt 자가점검 통과" (약 1–2분)
python bt/crosscheck.py                              # "전체 해시" 가 fc6501b873df43e1 이어야 한다
```

- **crosscheck 란:** 정해진 경기 10개를 돌려 결과의 지문 (해시) 을 만든다. 이 엔진은 같은 조건이면 결과가 완전히 같으므로, 해시가 같으면 내 PC 결과를 다른 PC 결과와 합칠 수 있다.
- **해시가 다르면 돌리지 말고** 출력 전체를 연우에게 보낸다.

### 2.4 PC 설정

- **절전 끄기:** Windows 설정 → 시스템 → 전원 → 화면과 절전을 모두 "안 함". 노트북은 전원을 연결한다. 실행 중에 꺼지면 이어서 돌릴 수는 있지만 시간이 늘어난다.
- **`--procs` 정하기:** 동시에 돌릴 경기 수. 논리 코어 수 − 2 를 기준으로 한다. **메모리가 8 GB 안팎인 노트북은 4 이하.** 지난 본실험에서 PC2 가 6 으로 돌다 메모리가 부족해 시간 초과 경기가 33개 나왔다.
- 실행 중 다른 무거운 프로그램은 닫는다.

## 3. 실행기의 기본 동작 (알아 두면 덜 당황한다)

- `bt/run_bt.py <θ 파일> --prefix <접두어> ...` 가 경기를 돌리고 한 줄씩 결과를 CSV 에 쓴다.
- **접두어 (prefix):** 시드 묶음의 이름. 접두어가 같으면 같은 시작 조건이 나온다. 확증용 접두어 (`bt-main`, `bt-confirm*`) 는 `--unlock-confirm` 과 그 계획의 태그가 있어야 돈다.
- **실행 전 점검:** 돌리기 전에 자동으로 확인한다. (1) `bt/` 에 고친 파일이 없는가 (2) Python 3.11.9 인가 (3) crosscheck 해시가 맞는가 (4) 태그가 있는가. 하나라도 틀리면 "실행 거부" 메시지와 함께 멈춘다.
- **이어서 돌리기:** 끊긴 뒤 **같은 명령을 그대로** 다시 치면 이미 기록된 경기는 건너뛴다.
- **`--dry`:** 경기 수만 세고 돌리지 않는다. 실행 전에 꼭 한 번 확인한다.
- **`--shard i/n`:** 전체 경기를 n 몫으로 나눠 i 번째만 돈다. PC 여러 대가 나눠 돌릴 때 쓴다. 결과 파일 이름에 몫 번호가 붙는다.

## 4. V1 분해 실험 돌리기

### 4.1 시작 전 확인 (위치: `cadet_research/kit`)

```bash
git fetch --tags origin
git tag -l prereg-bt-v1split-v1        # 아무것도 안 나오면 아직 태그 전이다. 멈추고 기다린다
git checkout prereg-bt-v1split-v1      # 모든 PC 가 같은 코드 (태그 커밋) 로 돌린다
python bt/test_bt.py                   # "bt 자가점검 통과"
git status --short bt                  # 아무것도 안 나와야 한다
```

`git checkout <태그>` 뒤 "detached HEAD" 라는 안내가 나오는 것은 정상이다. 태그 시점의 코드에 고정된 상태라는 뜻이다.

### 4.2 몫 나누기

연우가 PC 수 n 과 각자의 번호 i 를 정해 준다. 아래는 예시다 (몫마다 경기 수가 같다).

| PC 수 | 한 PC 의 몫 (두 묶음 합) | 예상 시간 (약 7 s/경기 기준) |
|---|---|---|
| 1대 | 3,456경기 | 약 6.7시간 |
| 2대 | 1,728경기 | 약 3.4시간 |
| 3대 | 1,152경기 | 약 2.2시간 |

PC 성능과 `--procs` 에 따라 시간은 달라진다.

### 4.3 실행 (자기 번호 i, 전체 n 으로 바꿔서)

```bash
# 1) 경기 수 확인 (두 줄 모두 "남음" 이 위 표의 절반이어야 한다)
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --shard i/n --dry
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --opponents heldout --shard i/n --dry

# 2) 실행 (patched 묶음 → heldout 묶음 순서)
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --shard i/n --procs 4
python bt/run_bt.py bt/thetas/v1split4.csv --prefix bt-confirm4 --unlock-confirm --nseeds 36 --opponents heldout --shard i/n --procs 4
```

PC 가 한 대뿐이면 `--shard i/n` 을 빼고 돌린다. 이때 결과 파일 이름은 `games.csv` 다.

**진행 상황:** 화면에 `120/576  900s 경과, 남은 예상 3400s` 처럼 찍힌다. 끝나면 `기록: ...csv (wall_clock 0경기)` 가 나온다.

### 4.4 결과 파일

| 묶음 | 파일 (이름 바꾸지 말 것) |
|---|---|
| patched | `bt/out/bt-confirm4/games_v1split4_shard<i>of<n>.csv` |
| heldout | `bt/out/bt-confirm4-heldout/games_v1split4_shard<i>of<n>.csv` |

## 5. 끊겼을 때

- **컴퓨터가 꺼졌거나 창을 닫았을 때:** 다시 켜고 `cadet_research/kit` 에서 **같은 명령**을 친다. 기록된 경기는 건너뛴다. 결과 파일을 지우지 않는다.
- **"실행 거부" 가 나올 때:** 메시지를 그대로 연우에게 보낸다. 흔한 원인은 다음과 같다.
  - `bt/` 에 고친 파일이 있다 → `git status --short bt` 로 확인.
  - Python 버전이 다르다.
  - 태그가 없다.

## 6. 끝난 뒤 확인

`cadet_research/kit` 에서 (patched 예시, heldout 은 폴더 이름만 바꾼다):

```bash
python -c "import csv; r=list(csv.DictReader(open('bt/out/bt-confirm4/games_v1split4_shard1of3.csv', encoding='utf-8'))); print(len(r), 'games', sum(x['end_reason']=='wall_clock' for x in r), 'wall_clock', {x['code_commit'] for x in r})"
```

- **경기 수**가 4.2 의 몫과 같아야 한다.
- **wall_clock** (실제 시간 120초 안전장치에 걸린 경기) 이 0 이어야 한다. 0 이 아니면 연우에게 알린다. 그 줄만 지우고 다시 돌리는 일은 연우가 한다 (규칙: `PREREG_BT.md` §7).
- **code_commit** 이 하나뿐이어야 한다 (모든 PC 가 같은 태그 커밋).
- `disqualified` 가 한 경기라도 나오면 **실행을 멈추고** 연우에게 알린다.

## 7. 결과 보내기

구글 드라이브 `BT실험_공유/3_결과_제출/<자기 이름>/` 에 올린다.

- 4.4 의 결과 파일 두 개 (이름 그대로).
- `python bt/crosscheck.py` 출력의 마지막 3줄과 `python --version` 결과.
- 실행 기록: PC 이름, 시작·끝 시각, `--procs`, 끊긴 적이 있으면 그 시각.

연우가 받은 파일을 `bt/merge.py` 로 검사·합친다. 중복, 누락, 코드 버전 불일치, wall_clock 이 하나라도 있으면 합치지 않는다.

```bash
python bt/merge.py bt/thetas/v1split4.csv --prefix bt-confirm4 --nseeds 36 --out bt/out/bt-confirm4/games.csv <shard 파일들>
python bt/merge.py bt/thetas/v1split4.csv --prefix bt-confirm4 --nseeds 36 --opponents heldout --out bt/out/bt-confirm4-heldout/games.csv <shard 파일들>
python bt/analysis/v1split.py     # → bt/out/analysis/v1split_report.md
```

분석 코드는 앞선 bt-confirm2 결과도 읽는다 (서술용 비교). 드라이브 `BT실험_공유/2_지금까지_결과/` 의 결과를 `bt/out/` 에 풀어 두면 된다.

## 8. 지금까지의 결과를 다시 보고 싶을 때

드라이브 `BT실험_공유/2_지금까지_결과/bt_out_results.zip` 을 `cadet_research/kit/bt/` 에 풀면 `bt/out/` 아래에 원래 위치대로 들어간다. 그 뒤 분석만 다시 돌릴 수 있다 (경기를 다시 돌리지 않는다).

| 실험 | 분석 명령 |
|---|---|
| ⑦ 튜닝 BT 비교 | `python bt/analysis/tuning.py` |
| ⑧ 사후 탐색 | `python bt/analysis/stage0.py` |
| ⑨ 새 상대 재검증 | `python bt/analysis/generalize.py` |
| ⑥ 확인 단계 | `python bt/analysis/confirm.py bt/out/bt-confirm/games.csv --baseline f2306532ecff --out <폴더>` |

분석 결과 파일이 저장소의 보고서를 덮어쓴다. 같은 데이터면 내용이 같아야 한다. 다르면 연우에게 알린다.

**주의:** 저장소에 올라간 보고서가 바뀌면 `bt/` 에 "고친 파일"이 생겨 다음 실험의 실행 전 점검이 거부한다. 실험을 돌리기 전에 아래로 되돌린다 (위치: `cadet_research/kit`).

```bash
git status --short bt          # 바뀐 파일 확인
git restore bt/out             # 저장소에 올라간 보고서를 원래대로 (결과 CSV 는 저장소 밖이라 영향 없음)
```

## 9. 막혔을 때

추측해서 고치지 말고 멈춘다. 아래를 연우에게 보낸다.

- 친 명령 그대로
- 화면에 나온 마지막 20줄
- `git log -1 --format=%h` 와 `python --version` 결과
