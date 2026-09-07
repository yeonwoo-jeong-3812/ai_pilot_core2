# AI Combat Tournament System

AI Combat 플랫폼의 토너먼트 시스템은 다수의 AI 에이전트 간 대결을 관리하고, 결과를 기록하며, 순위를 산정합니다.

## 1. 빠른 시작

### 방법 1: 자동화 파이프라인 (권장)

```bash
# 전체 파이프라인 자동 실행
python scripts/auto_tournament.py
```

**자동 처리 단계:**
1. Supabase에서 제출 파일 다운로드
2. 토너먼트 초기화 (최초 1회)
3. 새 팀 자동 등록
4. 미대전 매치 자동 추가
5. 매치 실행
6. 리더보드 출력
7. Supabase에 결과 업로드

### 방법 2: 수동 단계별 실행

```bash
# 1. 팀 등록
python scripts/run_tournament.py register --team-id team_a --name "Alpha" --file submissions/team_a/team_a.yaml
python scripts/run_tournament.py register --team-id team_b --name "Beta"  --file submissions/team_b/team_b.yaml

# 2. 매치 자동 생성 (미대전 조합 전체)
python scripts/run_tournament.py add-matches

# 3. 매치 실행
python scripts/run_tournament.py run

# 4. 리더보드 확인
python scripts/run_tournament.py leaderboard
```

## 2. CLI 명령어 전체 목록

| 명령어 | 설명 |
|--------|------|
| `auto_tournament.py` | 전체 파이프라인 자동 실행 (권장) |
| `download_submissions.py` | Supabase에서 제출 파일 다운로드 |
| `upload_results.py` | 토너먼트 결과를 Supabase에 업로드 |
| `init` | 토너먼트 데이터 초기화 |
| `register` | 팀 등록 |
| `teams list` | 등록된 팀 목록 조회 |
| `teams remove` | 팀 삭제 |
| `add-matches` | 미대전 조합 매치 자동 추가 |
| `start --round qualification` | 전체 예선 대진표 일괄 생성 |
| `run` | 대기 중인 매치 실행 |
| `reset-matches` | 모든 매치 초기화 (팀 등록 유지) |
| `leaderboard` | 순위표 출력 |

### 자동화 파이프라인 옵션

```bash
# 전체 파이프라인 실행
python scripts/auto_tournament.py

# 다운로드 건너뛰기 (로컬 파일 사용)
python scripts/auto_tournament.py --skip-download

# 업로드 건너뛰기 (테스트용)
python scripts/auto_tournament.py --skip-upload

# 데이터 디렉토리 지정
python scripts/auto_tournament.py --data-dir custom_data/
```

### 상세 옵션

```bash
# 팀 등록
python scripts/run_tournament.py register \
    --team-id <ID>    \  # 영문/숫자 고유 ID
    --name <이름>     \  # 표시 이름
    --file <경로>        # 에이전트 YAML 파일 경로

# 팀 관리
python scripts/run_tournament.py teams list
python scripts/run_tournament.py teams remove --team-id <ID>

# 매치 초기화 (팀 등록은 유지, 전적 리셋)
python scripts/run_tournament.py reset-matches          # 확인 프롬프트 표시
python scripts/run_tournament.py reset-matches --yes     # 확인 없이 즉시 실행

# 데이터 디렉토리 지정 (모든 명령어 공통)
python scripts/run_tournament.py run --data-dir custom_data/
```

## 3. 승패 판정 기준

매치는 최대 `max_steps`(기본 6000스텝 = 5분 @ 20 Hz env.step) 동안 진행되며, 다음 순서로 승패를 결정합니다.

| 우선순위 | 조건 | 승리 조건 코드 |
|----------|------|----------------|
| 1 | 상대 체력이 0이 됨 | `health_zero` |
| 2 | Hard Deck(1,000 ft) 위반 | `hard_deck` |
| 3 | 시간 종료 시 체력 우위 | `health_adv` |
| 4 | 시간 종료 시 체력 동점 | `timeout` (무승부) |

> 체력은 WEZ(Weapon Engagement Zone) 내 체류 시간에 비례해 감소합니다.

## 4. 순위 산정

### 승점제 (3-1-0)
- **승**: 3점
- **무**: 1점
- **패**: 0점
- **동점 시**: 평균 잔여 HP가 높은 팀이 상위

### 리더보드 출력 예시
```
[LEADERBOARD]
=========================================================
#    Team               Win   Draw   Loss   Pts   Avg HP
---------------------------------------------------------
1    Eagle 1            2     1      0      7     100.0
2    Ace                1     2      0      5     100.0
3    Simple             1     1      1      4     97.1
4    Viper 1            0     0      3      0     37.7
=========================================================
```

- **Pts**: 승점 (Win×3 + Draw×1)
- **Avg HP**: 매치 종료 시 평균 잔여 체력 (전투력 지표 — 승점 동률 시 결정자)

## 5. 주요 컴포넌트

### `src/tournament/manager.py` — TournamentManager
토너먼트 전체 수명 주기 관리.
- `register_team()` / `remove_team()` / `list_teams()`
- `add_missing_matches()` — 미대전 조합 자동 생성
- `create_qualification_round()` — 전체 리그전 대진 생성
- `run_pending_matches()` — 대기 매치 순차 실행
- `get_leaderboard()` — 승점제 정렬 순위 반환

### `src/tournament/models.py` — 데이터 모델
- `Team`: ID, 이름, 전적(Win/Draw/Loss), 잔여 HP 누적
- `Match`: 매치 정보, 상태(PENDING / RUNNING / COMPLETED / ERROR)
- `MatchResult`: 승자, 체력, 승리 조건, 리플레이 경로

### `src/tournament/persistence.py` — TournamentPersistence
`tournament_data/teams.json`, `tournament_data/matches.json`으로 상태 저장/로드.

### `src/match/runner.py` — BehaviorTreeMatch
실제 시뮬레이션 실행. 체력 기반 승패 판정.

### `src/match/judge.py` — MatchJudge / VictoryCondition
승리 조건 정의 및 판정 로직.

### `src/submission/runner.py` — SubmissionRunner
에이전트 파일 검증 및 임시 디렉토리 격리 실행 준비.

## 6. 데이터 구조

### `tournament_data/teams.json`
```json
{
  "team_a": {
    "id": "team_a",
    "name": "Alpha",
    "submission_path": "/path/to/team_a.yaml",
    "wins": 1,
    "losses": 0,
    "draws": 1,
    "total_hp_remaining": 200.0
  }
}
```

### `tournament_data/matches.json`
```json
[
  {
    "id": "qualification_abc123_1",
    "team1_id": "team_a",
    "team2_id": "team_b",
    "phase": "qualification",
    "status": "completed",
    "result": {
      "winner_id": "team_a",
      "duration": 26.8,
      "replay_path": "replays/qualification_abc123_1.acmi",
      "scores": {
        "team_a": 15.1,
        "team_b": -24.9,
        "team_a_hp": 100.0,
        "team_b_hp": 0.0,
        "victory_condition": "health_zero"
      }
    }
  }
]
```

## 7. 설정 파일

`config/tournament_config.yaml`에서 주요 파라미터를 조정할 수 있습니다.

```yaml
match:
  max_steps: 6000          # 매치 최대 스텝 수 (5분 @ 20 Hz env.step)
  config_name: "1v1/NoWeapon/bt_vs_bt"
```

## 8. 데이터 저장 방식

### JSON 파일 기반 (현재 방식)

토너먼트 시스템은 JSON 파일 기반으로 데이터를 관리합니다.

**장점:**
- 네트워크 지연 없이 빠른 매치 실행 가능
- 오프라인 환경에서도 토너먼트 가능
- 단순한 디버깅 (JSON 파일 직접 확인)
- 버전 관리 용이 (Git으로 변경 이력 추적)

**데이터 흐름:**
```
Supabase (submissions)
    ↓ download_submissions.py
로컬 (submissions/)
    ↓ run_tournament.py
로컬 JSON (tournament_data/)
    ↓ upload_results.py
Supabase (teams, matches)
    ↓
웹 UI 표시
```

### 멱등성 보장

모든 스크립트는 멱등성을 보장하여 여러 번 실행해도 안전합니다.

- **`download_submissions.py`**: 이미 다운로드된 파일은 재다운로드 건너뛰기
- **`upload_results.py`**: `upsert` 사용으로 중복 업로드 방지
- **`auto_tournament.py`**: 전체 파이프라인 안전한 재실행

## 9. 신규 팀 추가 워크플로우

### 자동화 방식 (권장)

```bash
# 전체 파이프라인 실행 (새 팀 자동 감지 및 처리)
python scripts/auto_tournament.py
```

### 수동 방식

```bash
# 1. 팀 등록
python scripts/run_tournament.py register --team-id new_team --name "New Team" --file submissions/new_team/new_team.yaml

# 2. 기존 팀과의 미대전 매치 자동 생성
python scripts/run_tournament.py add-matches
# [OK] 신규 매치 N개가 추가되었습니다.

# 3. 신규 매치만 실행 (기존 완료 매치는 건너뜀)
python scripts/run_tournament.py run

# 4. 업데이트된 순위 확인
python scripts/run_tournament.py leaderboard
```

---

## 10. 결승 토너먼트 (Single Elimination)

예선 round-robin 완료 후 상위 N팀이 결승 브라켓 진출. 표준 시딩으로 1번 시드가 약체와 만나도록 매칭.

### 10.1 시딩 규칙

| 인원 | 페어 |
|---|---|
| 8팀 (8강) | (1v8), (2v7), (3v6), (4v5) |
| 4팀 (4강) | (1v4), (2v3) |
| 2팀 (결승) | (1v2) |

비2제곱 인원이면 상위 시드부터 **bye(부전승)** 자동 부여 (예: 5팀 → 1·2·3번 시드 bye, 4v5만 매치).

### 10.2 프로그래밍 사용

```python
from src.tournament.bracket import BracketGenerator
from src.tournament.models import MatchPhase

# 예선 결과 정렬 (이미 leaderboard 순)
top8 = mgr.get_leaderboard()[:8]

# 8강 매치 생성 (bye 자동)
quarter = BracketGenerator.generate_seeded_bracket(top8, MatchPhase.QUARTERFINALS)
mgr.matches.extend(quarter)

# 8강 완료 후 4강 자동 생성 (승자 진출)
quarter_done = [m for m in mgr.matches if m.phase == MatchPhase.QUARTERFINALS
                                       and m.status.value == 'completed']
semis = BracketGenerator.generate_next_round(quarter_done, MatchPhase.SEMIFINALS)
mgr.matches.extend(semis)

# 4강 완료 후 결승
semis_done = [m for m in mgr.matches if m.phase == MatchPhase.SEMIFINALS
                                     and m.status.value == 'completed']
finals = BracketGenerator.generate_next_round(semis_done, MatchPhase.FINALS)
```

**주의**: `generate_next_round`는 무승부 매치가 있으면 `ValueError`. 결승 토너먼트는 결판이 필요하므로 사전 룰로 무승부 처리(연장전 / 잔여 HP 우위 / 재경기)를 정해야 한다.

---

## 11. 매치 감사 (이의제기 대응)

결정론 매치 (같은 `match.id` → 같은 시드 → 같은 결과)를 활용해 의심 매치를 재실행하고 원본과 비교한다.

### 11.1 단일 매치 감사

```bash
python scripts/audit_match.py <match_id>
```

출력 예 (일치):
```
감사 시작: qualification_team_a_vs_team_b_1
  team1: Alpha (submissions/team_a/team_a.yaml)
  team2: Bravo (submissions/team_b/team_b.yaml)
  seed = 1335379543 (0x4F9E6857)
  original: MatchSnapshot(winner='tree1', total_steps=523, ...)
재실행 중...
[OK] qualification_team_a_vs_team_b_1 — 원본과 재실행 결과 완전 일치 (tree1)
```

출력 예 (불일치):
```
[MISMATCH] qualification_xxx — 불일치 필드: ['winner', 'total_steps']
  original: {...}
  rerun:    {...}
```

### 11.2 매치 목록 조회

```bash
python scripts/audit_match.py --list
```

### 11.3 불일치 시 진단

재실행 결과가 원본과 다르면 가능한 원인:

| 원인 | 진단 방법 |
|---|---|
| 코드 변경 (시뮬·판정·WEZ 등) | git log로 매치 실행 이후 변경 확인 |
| BT 파일 변경 (부정행위 의심) | `git diff <team_yaml>`, `git log <team_yaml>` |
| JSBSim/numpy 버전 변경 | `pip list`로 버전 확인 |
| 외부 randomness 누설 (드뭄) | `src/match/seeding.py`의 시드 적용 범위 확인 |

### 11.4 프로그래밍 사용

```python
from src.tournament.audit import audit_match, MatchSnapshot
from src.match.seeding import derive_seed

original = MatchSnapshot.from_dict(match.result.game_result)
report = audit_match(
    match_id=match.id,
    tree1_file=team1.submission_path,
    tree2_file=team2.submission_path,
    seed=derive_seed(match.id),
    original_snapshot=original,
)
if not report.matched:
    print(report.summary())
```

---

## 12. 공식 매치 규칙

토너먼트 진행은 본 문서, **매치 규칙·승패 판정·정보 공개 정책**은 [RULEBOOK.md](RULEBOOK.md)를 참조한다.
