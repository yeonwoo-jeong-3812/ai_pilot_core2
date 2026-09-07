# v3.0.0 ↔ v2.11.2 비교 — `max_g` 폐지와 조절층 개방

> 대상: v2.11.2 → **v3.0.0** (= 22458d5. 본체 26edcf5 + 코드 리뷰 반영 d5f8936·dd8299c + 본 문서).
> 52파일, +1,093 / −338. DB 스키마 변경 없음.
> 실측 근거: 배터리 320경기(t4) + 프로브 재검증 40경기(t5) + 풀리그 396경기(t7) + 개발 중 A/B ~200경기.

---

## 1. 요약

| | v2.11.2 | v3.0.0 |
|---|---|---|
| 공격성 제어 | `max_g: true/false` — G 조절 법칙 전체를 우회하는 **이진 스위치** | `g_burst` 0.0~1.0 — 지속↔순간 봉투를 잇는 **연속 천장**. 우회 경로 없음 |
| G 조절 오차항 | 적까지의 ATA | **기수→조준점 각도** (`aim_above_ft` 반영) |
| 액션 파라미터 | 8키, **범위 검사 없음** | 11키, 전 숫자 키에 (lo, hi) 강제 — 범위 밖 = 제출 거부 |
| 교리 필드 | 15개 (그중 4개는 audit 전용 장식) | 19개 (장식 4개 중 3개 실제 연결 + 4개 신설, `corner_kcas_hi` 만 잔존) |
| `lead_time_s` 생략 시 | 1.0 s (문서는 1.5 로 오기) | **1.5 s** (문서와 일치) |
| examples | 5종 | 4종 (`bem_control_zone` 삭제) + 의도적 비최적 파라미터 |
| 하위호환 | — | **없음. `max_g` 제출물은 검증 거부** |
| 배터리 만점 전략 | `max_g` 상시 (실리더보드 FNG 40전 40승) | **없음** — 상위 4개 설계가 108~117에 분산 |

**변경 동기**: 예선 리더보드 1위(FNG)가 40전 40승 만점. 원인은 `max_g: true`가
[bfm_guidance.py](../aircombat/guidance/bfm_guidance.py)의 `_regulate_g`에서 ATA 비례 조절·track_lock·
initial_pull·energy_backoff 전부를 건너뛰고 순간 봉투를 즉시 반환하는 구조. 참가자에게 열린
공격성 노브가 사실상 이진값 하나뿐이라 `true`로 전원 수렴 → 일반 참가자 모집을 앞두고
전략 설계의 다양성이 소멸할 위험.

---

## 2. 코드가 어떻게 바뀌었는가

### 2.1 G 조절 법칙 재설계 — `aircombat/guidance/bfm_guidance.py` (핵심)

**v2.11.2:**

```python
g_nom = min(g_avail * doc.g_fraction, g_sustained)
if max_g:
    return g_avail, "max_g"          # ← 조절 법칙 전체 우회
k = g_nom / 45.0                     # ← 하드코딩, 오차항 = 적 ATA
g = clip(k * ata_deg, doc.g_min, g_nom)
```

**v3.0.0:**

```python
err_deg = aim_ata_deg               # ← 오차항 = 기수→조준점 각도 (신규 ①)
ceiling = g_sustained + max(0, g_avail - g_sustained) * g_burst   # (신규 ②)
g_nom = min(g_avail * doc.g_fraction, ceiling)
if err_deg < doc.ata_target_lo:     # 대역 안 burst 선형 감쇠 (신규 ③)
    g_nom = min(g_nom, g_sustained + max(0, g_nom - g_sustained) * err_deg / doc.ata_target_lo)
k = g_nom / g_full_ata_deg          # 포화 각도 개방, 기본 = doc.ata_target_hi (신규 ④)
g = clip(k * err_deg, doc.g_min, g_nom)
```

**① 오차항 전환이 가장 근본적인 변화다.** v2 는 L1 이 `aim_above_ft` 로 조준점을 옮겨도
G 는 적 기준 ATA 로 쟀다. 그래서 "기수는 적을 문 채 조준점만 위" 인 국면 — 하드덱 회복,
요요 — 에서 조절기가 "이미 도착했다"고 오판해 1G 로 주저앉았고, **이 결함을 덮는 목발이
`max_g` 였다** (2026-08-01 하드덱 회복 사고의 뿌리와 동일). v3 에서 조준점 오프셋은 곧
조준 오차가 되어 비례 조절이 알아서 당긴다. 실측:

| 기하 (거리 3,000ft) | v2 지령 G | v3 지령 G |
|---|---:|---:|
| 하드덱 회복 — 적 ATA 0°, 조준점 +4,000ft, burst 0.8 | 1.0 (max_g 없으면) | **8.16** (오차 53.1°) |
| 동일, burst 생략 | 1.0 | **4.79** (지속 봉투 캡) |
| 정조준 추격 — ATA 0°, 오프셋 0, burst 1.0 | 9.0 (max_g 시) | **1.00** |

마지막 행이 v3 의 설계 핵심이다: **조준이 맞은 상태에서 고G 를 상시 유지하는 것이
원리적으로 불가능**해졌다(그때는 오차가 0이다). 상시 고G 가 필요 없어졌고, 얻을 수도 없다.

**② `g_burst`** 는 지속 봉투(Ps≥0, 3.3~4.8G)와 순간 봉투(리미터 9G)의 사이를 잇는
연속 천장이다. 1.0 이어도 위의 비례 조절을 통과한다 — "무조건 최대" 경로는 없다.

**③ ata_target_lo 감쇠**: ATA 목표대역(교범 4.4.6.2.2) 안쪽에서 burst 효과를 선형으로
줄인다(4.4.7.2 "DO NOT stay on the limiter"). 개발 중 절벽형(경계에서 즉시 지속 봉투로
강등)을 시험했으나 수렴 원뿔(25~35°)의 마무리 당김을 죽여 강한 에이전트 무접촉을
2/12→6/12 로 악화시켜 기각, 감쇠형으로 확정(감쇠판 8격추/3무접촉 ≈ 해제판 8/2).

**④ track_lock 창 개방**: 건 추적 하한 G(순간 봉투 사용)의 발동 창
`rng<2500 ∧ ata<30`(하드코딩)이 `track_rng_ft`/`track_ata_deg` 로 열렸다.
**허용 범위 상한 = WEZ(3,000ft / 30°)** — 상한을 5,000ft/50°로 열었던 중간 버전은
프로브가 배터리 40전 전승 만점을 기록해 기각했다(WEZ 밖 track_lock = max_g 의 재림).

기타: `initial_pull` 게이트가 슬랜트 **대역**(`slant_ft_lo`~`hi`)으로, `_power` 새들
`900.0` → `doc.closure_saddle_ft`, energy_backoff 바닥 `0.5` → `doc.energy_backoff_floor`,
`CZ_CLOSE_T` → `doc.cz_close_t_s`.

### 2.2 액션 파라미터 스키마 — `aircombat/tactics/dsl.py`

```python
_ACTION_BOUNDS = {                       # 신설 — 검증·자동 문서의 단일 진실
    "aim_above_ft":   (-5000.0, 5000.0),
    "lead_time_s":    (0.0, 3.0),
    "lag_dist_ft":    (0.0, 8000.0),
    "cz_range_ft":    (500.0, 6000.0),
    "g_burst":        (0.0, 1.0),        # 신규
    "g_full_ata_deg": (20.0, 90.0),      # 신규
    "track_rng_ft":   (1000.0, 3000.0),  # 신규 — 상한 = WEZ 사거리
    "track_ata_deg":  (10.0, 30.0),      # 신규 — 상한 = WEZ 원뿔
}
_ACTION_KEYS = set(_ACTION_BOUNDS) | {"pursuit", "name", "mode"}   # max_g 제거
```

- v2 는 화이트리스트만 있고 범위 검사가 없었다 — `aim_above_ft: 99999` 도 통과했다.
  v3 는 범위 밖이면 **제출 거부**(조용한 클램프 없음), 에러는 doctrine 방식대로 모아서
  한 번에 보고(한 필드씩 고쳐 재제출하는 왕복 제거).
- `max_g` 는 미지 키 일반 오류가 아니라 **전용 마이그레이션 안내**를 던진다
  ("g_burst 로 대체하십시오. 권장 전환 true→0.8 / false→0.0 …").
- 스레딩: `node.py`(Action) → `context.py`(TacticContext/TacticCommand) → `policy.py` →
  `pilot.py` → `bfm_guidance.compute` 전 구간에서 `max_g` 필드 제거, 신규 4키 추가.

### 2.3 교리 — `aircombat/guidance/doctrine.py`

**신설 4필드** (기본값 = 구 하드코딩값, 거동 불변):

| 필드 | 범위 | 기본 | 대체한 하드코딩 |
|---|---|---:|---|
| `initial_pull_aspect_deg` | 90–150 | 120 | 머지 초기당김 aspect 게이트 |
| `closure_saddle_ft` | 600–1,500 | 900 | 접근율 깔때기 새들 |
| `energy_backoff_floor` | 0.3–0.8 | 0.5 | 저속 G 감쇠 바닥 |
| `cz_close_t_s` | 2.0–8.0 | 4.0 | control_zone 수렴 시상수 |

**장식 노브 수리**: v2 에서 "튜닝 가능"이라 개방됐지만 `audit` 딕셔너리 안에서만 소비돼
거동을 못 바꾸던 3필드를 실제 조절에 연결했다(무작위 감도 4,000회 실측):

| 필드 | v2 감도 | v3 연결 | v3 감도 |
|---|---:|---|---:|
| `ata_target_hi` | 0% | `g_full_ata_deg` 미지정 시 기본값 | 12.7% |
| `ata_target_lo` | 0% | 대역 안 burst 선형 감쇠 | 3.4% |
| `slant_ft_lo` | 0% | 초기당김 슬랜트 대역 하한 | 0.1% |

`corner_kcas_hi` 는 여전히 미연결 — 리미터가 하한만 사용하고 상한은 구조 한계로 이미
포화라 **물리적으로 연결할 자리가 없다**. 개방 목록에서 제외할지는 운영 결정 대기
(`tests/test_no_dead_knobs.py` 의 명시 예외로 등록).

### 2.4 기본값 변경

| 항목 | v2.11.2 | v3.0.0 | 비고 |
|---|---:|---:|---|
| `lead_time_s` 생략 시 | 1.0 | **1.5** | README·docstring·예제가 전부 1.5 를 보여주고 있었음(문서-코드 불일치 해소). 근접에서는 1.0 이 유리한 경우가 많음 — 의도적 "생략 시 평범" |
| `g_burst` 생략 시 | (개념 없음) | 0.0 | 지속 봉투만 — 가장 보수적 |
| track 창 생략 시 | 2500/30 (하드코딩) | 2500/30 | 동일 (오버라이드만 열림) |

### 2.5 에이전트 YAML

- **전 YAML 기계 전환**: `max_g: true → g_burst: 0.8`, `max_g: false → g_burst: 0.0`
  (examples·redteams 11종·agents·config). 1.0 이 아니라 0.8 인 이유: 1.0 전환은 구 수렴을
  그대로 이식한다 — 전환값을 비최적으로 두어 "더 태우려면 직접 올려야" 하게 했다.
- **`agents/maverick_JesterF.yaml` = 전 파라미터 레퍼런스판**: 액션 숫자 8키 + 교리
  19필드를 전부 명시. "어떤 노브가 있고 어디 쓰는지"를 한 파일에서 보는 용도.
- **`examples/bem_control_zone.yaml` 삭제** (5종→4종): stable/control_zone 시연이
  `textbook_headon` 과 중복. `in_control_zone` 조건 시연은 textbook 에 흡수하되
  **사격(SOO)을 CZ 유지보다 위에 배치** — 순서를 뒤집으면 존에 주차한 채 300초 무사격
  (실측 무접촉 15/40)이 된다는 주석 포함.
- **examples 4종에 의도적 비최적 파라미터** + "출발점이지 정답이 아니다" 헤더:
  그대로 제출하면 중위권, 튜닝하면 상승하도록.
- 레드팀 5종(배터리)은 기계 전환만 — 재튜닝은 별도 작업으로 분리.

### 2.6 감사(ACMI)·문서·테스트

- ACMI L1 문자열: `maxG=0/1` → `burst=0.80` (연속값). audit 에 `aim_ata_deg`
  (조절 오차항), `g_burst` 추가 — 리플레이에서 조절 동작을 그대로 추적 가능.
- `scripts/gen_references.py`: 액션 표를 `_ACTION_BOUNDS` 에서 파생(범위·기본값 자동),
  JSON Schema 에 `minimum`/`maximum` 내보냄. REFERENCE.md·agent.schema.json 은
  빌드 시 자동 재생성되므로 별도 갱신 불필요.
- RULEBOOK §10 을 「튜닝 파라미터 (교리·액션)」로 확장, §10.1 마이그레이션 절 신설,
  개정 이력 추가. 태그 푸시 시 웹 `/rules` 자동 동기화.
- 테스트: 211개 (신규 `test_no_dead_knobs.py` 3건 — 개방 필드가 audit 밖에서 소비되는지
  정적 검사, `TestActionBounds` 5건 — 범위 거부·일괄 에러·bool 함정·마이그레이션 메시지).

---

## 3. 변경의 영향

### 3.1 하위호환 — 없음 (의도적)

- **`max_g` 가 들어간 제출물은 검증 단계에서 거부**된다(실격 아님 — 전용 안내 메시지).
  현재 리더보드의 참가자 제출물은 전부 `max_g` 를 쓰므로 **전원 재제출 필요**.
- `lead_time_s` 를 생략한 트리는 리드 예측이 1.0→1.5s 로 바뀐다(명시하면 무영향).
- 기존 극단값(범위 밖) 파라미터가 있던 트리는 이제 거부된다.

### 3.2 거동 변화 (재제출 없이도 체감되는 것)

- **하드덱 회복 정상화**: `aim_above_ft` 가 곧 조준 오차라 비례 조절이 회복을 당긴다
  (burst 생략 시 지속 봉투 캡 ~4.8G, `g_burst: 0.8` 병용 시 ~8.2G). v2 에서 회복
  분기에 `max_g` 를 빼먹으면 1G 강하로 추락하던 함정 소멸.
- **레드팀**: 기계 전환(0.8)이라 순간 봉투 상시였던 v2 보다 약간 순해짐. 단
  `red_extender`/`red_reactive` 의 하드덱 자멸(발동 고도 1,200ft = 여유 200ft)은
  **v2 부터 있던 기존 결함** — 구 엔진 동일 조건 24경기 대조로 확인(5건 vs 7건, 노이즈 수준).
- **감사 충실도 향상**: 지령 G 의 근거(조준점 오차)가 audit 에 그대로 남아
  "왜 이 G 였나"를 리플레이에서 재구성 가능.

### 3.3 봉인된 뒷문 (개발 중 실측으로 기각한 설계)

릴리스에는 없지만, 재도입하면 안 되는 이유가 실측으로 확정된 설계들:

| 기각 설계 | 실측 | 원인 |
|---|---|---|
| `g_floor` (지령 G 하한 노브, 1~8G) | 단독으로 배터리 81→**111점**, burst 와 무관 | `clip(k·ata, 8.0, 천장)` = ATA 무관 상시 8G — max_g 정확 복원 |
| track 창 상한 5,000ft/50° | 프로브 **40전 전승 만점(120)** | WEZ 밖 track_lock = 선회전 전 구간 순간 봉투 |
| `ata_target_lo` 절벽 감쇠 | 강한 에이전트 무접촉 2→**6**/12 | 수렴 원뿔(25~35°) 마무리 당김 사멸 |

---

## 4. 매치 결과 변동 (실측)

### 4.1 웹 배터리 미러 (320경기, 레드 5 × 시나리오 4 × salt 2)

| # | 에이전트 | 설계 | 승점 | 전적 | 격추승 | 무접촉 |
|---|---|---|---:|---|---:|---:|
| 1 | maverick_JesterF | **국면별 조합** (분기마다 burst/track 다름) | **117** | 39-1 | 33 | 0 |
| 2 | maverick_JesterL | burst 0.8 상시 | 114 | 38-2 | 31 | 2 |
| 2 | probe_trackmax† | track 창 WEZ 최대 | 114 | 38-2 | 30 | 2 |
| 4 | probe_burst10† | burst 1.0 극단 | 108 | 36-4 | 29 | 4 |
| 5 | energy_fighter | 예시(비최적) | 66 | 22-18 | 3 | 10 |
| 6 | starter | 예시(문법) | 60 | 20-20 | 16 | 3 |
| 7 | doctrine_regulator | 예시(교리 시연) | 39 | 13-27 | 10 | 15 |
| 8 | textbook_headon | 예시(교본형) | 15 | 5-35 | 3 | 17 |

† 측정 전용 프로브(JesterL 사본에 해당 노브만 변경) — 배포 대상 아님.
  `probe_trackmax` 행은 WEZ 캡(3,000/30°) 재검증(t5, 40경기) 수치다 — 같은 프로브가
  캡 이전 상한(5,000/50°)에서는 40전 전승 만점(120)이었다(§3.3 기각 근거).

**판독**:

- v2 리더보드에서는 `max_g` 상시(FNG)가 **만점**이었다. v3 에서는 만점 전략이 없고,
  서로 다른 설계 4개가 108~117 에 분산 — **단일 수렴 해소가 실측으로 확인**됐다.
- 극단(burst 1.0, 108) < 중간(0.8, 114) < 국면별 조합(117): **노브를 끝까지 올리는 것이
  최선이 아니다**. 내부 최적이 존재하므로 튜닝이 설계 문제가 된다.
- 프로브 2종이 JesterL 과 트리 동일·노브만 다른데 3~6점 차 — 노브가 실제 변별 요인.

### 4.2 풀리그 (12종 round-robin, 396경기, 진영 스왑 미러)

| # | 팀 | 승점 | | # | 팀 | 승점 |
|---|---|---:|---|---|---|---:|
| 1 | maverick_JesterF | 180 | | 7 | starter | 54 |
| 2 | maverick_JesterL | 153 | | 8 | red_extender | 51 |
| 3 | probe_burst10 | 150 | | 9 | red_phangman | 45 |
| 4 | red_adaptive | 108 | | 10 | red_energy | 42 |
| 5 | energy_fighter | 84 | | 11 | doctrine_regulator | 42 |
| 6 | red_reactive | 63 | | 12 | textbook_headon | 18 |

- **리그↔배터리 순위 상관 rho = +1.000** (공통 7종 완전 일치). v2 계열의 실측 대역은
  +0.39~+0.57 이었다 — 배터리가 참가자 간 실력 순서를 그대로 예측하는 수준으로 격상.
  (리그 강자가 레드팀에 약하던 v2 의 역전 현상 소멸.)
- 튜닝판(JesterF 180) vs 무설정에 가까운 판(starter 54): 튜닝이 확실히 보상받는다.

### 4.3 종료 사유 분포 (배터리, v2 동일 구성 대비)

| 사유 | v2 (구 엔진, 280경기 환산) | v3 (320경기) |
|---|---:|---:|
| 격추 (health_zero) | 41% | 50% |
| 타임아웃 | 26% | 24% |
| 무접촉 (no_contact) | 20% | 16% — **강한 4종만 보면 3.8%** (6/160) |
| 하드덱 | 13% | 10% — 전량 레드팀 자멸(기존 결함) |

무접촉은 여전히 약한 예시(textbook 17/40 등)에 집중 — 원인은 트리 성향(소극 분기)이며
엔진이 아님을 A/B 로 확인(강한 에이전트는 구성 무관 2~6/12). 기존 결론
"무교전은 참가자가 주도" 유지.

---

## 5. 참가자 입장에서 바꿔야 하는 것

### 5.1 필수 (안 하면 제출 거부)

1. **`max_g` 키를 전부 제거**하고 `g_burst` 로 전환:
   - `max_g: true` → `g_burst: 0.8` 부터 시작 (⚠ 거동 동일하지 않음 — §5.3)
   - `max_g: false` 또는 생략 → 그냥 생략 (기본 0.0)
2. **숫자 파라미터를 허용 범위 안으로** — 범위는 REFERENCE.md 표 참조. 범위 밖은
   클램프되지 않고 거부된다(에러 메시지에 전 위반 필드가 한 번에 나온다).
3. 제출 전 로컬 검증: `python tools/validate_agent.py my_agent.yaml`
   (서버와 동일 파서 — 여기서 통과하면 서버에서도 통과).
4. **재제출** — 리더보드 리셋 후 기존 제출물은 자동 복구되지 않는다.

### 5.2 확인 권장 (거부되진 않지만 거동이 달라짐)

- `lead_time_s` 를 생략했다면: 기본이 1.0→1.5s. 이전 거동 유지가 목적이면
  `lead_time_s: 1.0` 명시.
- 하드덱 회복 분기에 `max_g` 를 썼던 이유(1G 함정)는 사라졌다 — `aim_above_ft: 4000`
  만으로 강한 회복이 성립하므로 회복 분기에는 `g_burst: 0.8` 정도면 충분.

### 5.3 새 노브 지도 — 무엇으로 무엇을 설계하나

| 원하는 것 | v2 방법 | v3 방법 |
|---|---|---|
| 세게 당기며 추격 | `max_g: true` | `g_burst` ↑ (+ `g_full_ata_deg` ↓ = 조준각이 조금만 벌어져도 포화) |
| 에너지 보존 | `max_g: false` | `g_burst` 0~0.3 (지속 봉투 위주) |
| 사격 국면만 강하게 | (불가 — 이진뿐) | `track_rng_ft`/`track_ata_deg` 로 창 조절 — 창 안에서는 LOS 추적 G 를 순간 봉투까지 사용. **창을 좁히면 에너지 절약** |
| 수직 기동(요요·회복) | `aim_above_ft` + `max_g` 목발 | `aim_above_ft`(오차) **+ `g_burst`(천장) 병용** — 오프셋이 G 를 유도하되, 천장을 안 올리면 지속 봉투(~4.8G)에 캡 |
| 전역 성향 | doctrine 15필드 | doctrine 19필드 (신설 4 + 되살린 3 포함) |

**핵심 감각의 변화**: v2 는 "어느 분기에 `max_g` 를 켜나"의 조합 문제였다. v3 는
"조준이 맞으면 G 가 자연히 빠진다"가 전제다 — 고G 는 ① 조준점을 옮기거나(`aim_above_ft`)
② 천장을 올리거나(`g_burst`) ③ 사격 창 안에서(track) 얻는다. 셋 다 대가(에너지·조준 이탈)가
있어 **국면별로 갈라 쓰는 설계가 상시 극단값을 이긴다** (배터리 실측: 117 > 114 > 108).

### 5.4 빠른 전환 예시

```yaml
# v2.11.2                                        # v3.0.0
- action: {pursuit: lead, max_g: true,           - action: {pursuit: lead, g_burst: 0.8,
           name: lead_chase}                                name: lead_chase}

- action: {pursuit: pure, max_g: true,           - action: {pursuit: pure, g_burst: 0.8,
           aim_above_ft: 4000,                              aim_above_ft: 4000,
           name: recover_altitude}                          name: recover_altitude}
                                                 # (오프셋 = 조준 오차가 G 유도, burst = 천장 해제)

- action: {pursuit: lead, lead_time_s: 0.2,      - action: {pursuit: lead, lead_time_s: 0.2,
           max_g: true, name: gun_approach}                 g_burst: 0.9, g_full_ata_deg: 40,
                                                            track_rng_ft: 3000, track_ata_deg: 30,
                                                            name: gun_approach}
```

---

## 6. 잔여 이슈 (v3.0.0 에 포함되지 않음)

| 항목 | 상태 |
|---|---|
| 레드팀 하드덱 자멸 (`red_extender`/`red_reactive`, 발동 고도 1,200ft) | v2 부터 있던 결함. 배터리 변별에는 유효(참가자 쪽 아님) — 레드팀 재튜닝 작업으로 분리 |
| `corner_kcas_hi` 장식 노브 | 물리적 연결 자리 없음 — 개방 목록 제외 여부 운영 결정 대기 |
| examples 내부 서열 (starter > 성향형 2종) | 교육 의도와 어긋남. 36경기 표본이라 미확정 — 필요시 예시 파라미터 재조정 |
| JesterF 헤더의 duel 실측치 | "구 엔진 측정값, 재측정 대기"로 표기됨 — duel 재측정 미실행 |

> `MEASURED_BEHAVIOR.md` 는 dd8299c 에서 신 엔진 기준으로 재측정 완료 — v2 의 "max_g 는
> 선회가 오히려 준다" 서술이 뒤집혔다(신 엔진 burst 1.0: 선회 +6.3°/s > 기준 +5.5, 대가는 에너지).
