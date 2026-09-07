# ACMI 계층 의사결정 메시지 레퍼런스

Tacview에서 기체 객체를 선택하면 보이는 `L1` / `L2` / `L3` 속성의 전체 값 목록과 발생 조건.

- 기록 지점: [`combat_attrs()`](../aircombat/debrief/acmi.py) — 계층당 문자열 1개로 패킹, `None` 값은 생략.
- 값 산출 지점: L1 = [tactics/](../aircombat/tactics/) BT, L2 = [bfm_guidance.py](../aircombat/guidance/bfm_guidance.py)의 `audit` dict, L3 = [limiter.py](../aircombat/control/limiter.py) 포화 플래그.
- 조립: [match.py](../aircombat/engine/match.py) `_log_frame()` (파일·실시간 공용 포맷).

## L1 — 전술 BT (20Hz)

형식: `L1=node=<전술명> pursuit=<추격유형> burst=<0.00~1.00>`

| 키 | 가능한 값 | 발생 조건 |
| --- | --- | --- |
| `node` | 아래 표 참조 | 현재 tick에 채택된 BT Action 노드의 `name`. dwell 히스테리시스: 새 명령이 나와도 직전 전환 후 0.3초가 지나야 채택(전술 채터링 방지) — 표기가 BT 판단보다 최대 0.3초 늦을 수 있음 |
| `pursuit` | `lead` | 적 미래 위치(`lead_time_s` 초 후) 조준 — 리드 추격 |
| | `pure` | 적 현재 위치 조준 — 퓨어 추격 |
| | `lag` | 적 뒤 `lag_dist_ft` 지점 조준 — 랙 추격 |
| `burst` | `0.00`~`1.00` | L1 의 g_burst — 지속↔순간 봉투 천장 보간 (0=보존, 1=전량). 어떤 값이든 조절 법칙을 통과한다 |

### `node`에 올 수 있는 전술명

`node`는 **에이전트 YAML이 정의하는 자유 문자열**이라 전수 목록은 열려 있다. 아래는 엔진·공식 배포판에 내장된 이름.

**기본 트리** ([dsl.py](../aircombat/tactics/dsl.py) `DEFAULT_SPEC` — YAML 없이 실행 시):

| 값 | 발생 조건 (우선순위순) |
| --- | --- |
| `break_defense` | `foe_threat` — 적이 내 후방 위협 기하 → lag + max-G 방어 브레이크 |
| `lag_reposition` | `overshoot_risk` — 과잉 접근율 → lag로 재배치 |
| `lead_rundown` | `foe_extending` — 적 이탈 중 → lead + max-G 추격 |
| `gun_track` | `in_gun_envelope` — 건 WEZ 접근 기하 → pure 추적 |
| `lead_pull` | `nose_far` — 기수가 조준점서 멂 → lead 당김 |
| `pure_default` | 위 조건 모두 불성립 시 폴백 |
| `default` | 첫 tick 이전 초기값 (매치 시작 직후 잠깐) |

**요요 가지** (구 presets/ — 지금은 [examples/](../examples/) 의 attacker·energy_fighter 에 인라인):

| 값 | 출처 | 발생 조건 |
| --- | --- | --- |
| `yoyo_up` | attacker.yaml (high_yoyo) | 후방점유 + 오버슈트 위험 → lag + 상방 오프셋(하이 요요 상승) |
| `yoyo_down` | attacker.yaml (high_yoyo) | 요요 정점(적이 아래) + 접근 정체 → lead + 하방 커트 |
| `yoyo_pull_up` | energy_fighter.yaml (low_yoyo) | 접근율 확보 상태 → 상방 당김(로우 요요 회복) |
| `yoyo_dive_cut` | energy_fighter.yaml (low_yoyo) | 접근 정체 → 하방 다이브 커트 |

**공식 예제 에이전트** ([examples/](../examples/))에 추가로 등장: `recover_altitude`(하드덱 회복), `headon_stable`, `headon_merge`, `hold_control_zone`, `enter_control_zone`, `gun_soo`, `regain_nose`, `rate_fight_entry`, `rate_fight`, `refuse_one_circle`, `energy_recover`, `press_offense`, `press_attack` 등 — 각 YAML의 condition 시퀀스가 발생 조건.

**이름 생략 시** 자동 생성: `<pursuit>` 또는 `<pursuit>+burst<값>` (예: `lag+burst0.8`).

**스크립트 상대기**(scripted, L1 없음)는 `node`에 기동명이 대신 찍힘: `straight` / `turn` / `extend` / `break`. `pursuit`/`burst`는 생략.

## L2 — BFM 가이드 (60Hz)

형식: `L2=mode=<모드> gmode=<G조절상태> pwr=<파워상태> aim=<ft> dphi=<deg> lead=<s> lag=<ft>`

### `mode` — L1이 지정하는 가이드 모드 (미지정 시 키 생략)

| 값 | 의미 |
| --- | --- |
| `stable` | 포인팅 추적 — 표적을 body forward 축에 정렬(수평 우선 롤 + 부호있는 pitch). 헤드온 노즈온 유지용 |
| `control_zone` | 컨트롤존 체류 — 파워를 접근율 조절기로 대체, 목표거리(`cz_range_ft`, 기본 2,500ft) 수렴 |

### `gmode` — G 조절 상태 (`_regulate_g()` / stable 분기)

| 값 | 발생 조건 |
| --- | --- |
| `regulate` | 기본 — 기수→**조준점** 각도 비례 획득 법칙 (멀수록 강하게, 조준 근접 시 백오프). 천장은 `g_burst` 가 지속↔순간 봉투 사이에서 결정 |
| `track_lock` | 건 추적 창(`track_rng_ft`/`track_ata_deg`, 기본 2,500ft/30°) 안에서 표적 LOS 회전율 추적 G가 비례 G를 초과 — 건 추적 하한 |
| `initial_pull` | 머지 진입 기하(aspect > `initial_pull_aspect_deg`, 슬랜트 대역 4,000–6,000ft) → 초기 당김(6–8G급). 슬랜트 거리 = 고도차 포함 3D 직선거리 |
| `energy_backoff` | KCAS가 파이팅 하한 미만 → G를 낮춰 속도 보존 (다른 상태를 **덮어씀** — 최종 판정) |
| `stable_track` | `mode=stable`일 때 고정 (pitch rate 명령의 등가 G) |

### `pwr` — 파워 스케줄 상태 (`_power()` / `_control_zone_power()`)

| 값 | 스로틀 | 발생 조건 (우선순위순) |
| --- | --- | --- |
| `AB_entry` | AB | 원거리(슬랜트 거리 > 12,000ft = 상한×2) + 진입속도 미달 → 진입 가속 |
| `closure_ctl` | MIL→idle 비례 | 근거리(<2,500ft)·후방(aspect<90°)·파이팅 하한 위에서 과잉 접근율 컷 (900ft 트레일로 수렴하는 깔때기) |
| `AB_accel` | AB | KCAS < 파이팅 하한 → 가속 |
| `decel` | 0.2 | KCAS > 파이팅 상한 → 감속 |
| `margin_regain` | AB→MIL 블렌드 | 상대 TAS 우위 75kt 미달 → 에너지 마진 회복 (50kt 이하는 full AB) |
| `MIL_hold` | MIL | 파이팅 대역 내 + 마진 충분 → 유지 |
| `control_zone` | 비례 조절 | `mode=control_zone` — range 오차→목표 접근율→파워 (위 스케줄 전체를 대체) |

### 조준 기하 수치 (범주형 아님 — 값이 있을 때만)

| 키 | 의미 |
| --- | --- |
| `aim` | 실적용 조준점 수직 오프셋 [ft] (+위/−아래; L1 명시값 > stable/control_zone은 0 > 머지 진입 기하 시 교리 자동 `lv_above_ft` > 0) |
| `dphi` | 리프트벡터 배치 롤 증분 [deg] — 당김(G)은 양력 방향(body −z축)으로만 걸리므로 롤로 리프트벡터를 조준점에 정렬한 뒤 pitch로 당긴다. `dphi` = 현재 자세에서 추가로 굴릴 롤 각(0 근처 = 이미 정렬). 측정값 `RollOff`와 같은 수식이지만 RollOff는 적 현재 위치 기준 순수 LOS 판(lead/lag·수직 오프셋 없음) — 유도 입력이 아니라 관찰용이며, `RollOff`와 `dphi`의 차이가 조준 전략의 효과를 보여준다 |
| `lead` | lead 예측시간 [s] (L1 오버라이드 또는 가이던스 기본 1.0) |
| `lag` | lag 후방거리 [ft] (L1 오버라이드 또는 가이던스 기본 1,500) |

## L3 — 오토파일럿 리미터 (120Hz)

형식: `L3=lim=<축조합|->`

| 값 | 발생 조건 |
| --- | --- |
| `-` | 어느 축도 포화 안 됨 — 리미터 개입 없음 |
| `P` / `Q` / `R` 및 조합 (`PQ`, `QR`, `PQR` 등) | 해당 body축 각속도(P=롤·Q=피치·R=요 rate) 명령이 리미터 상한 초과 → 클램프 중. `Q` 포화가 G 상한(코너 플래토) 도달의 육안 지표 |

## 해석 시 주의

- **L1 `pursuit`는 명령값이다.** `mode=control_zone`에서 근접+접근 시 가이던스가 내부적으로 lag 편향(`pursuit_eff`)을 걸지만 L1 표기에는 반영되지 않는다 — 이때 `lag` 거동인데 `pursuit=pure`로 보일 수 있다.
- `gmode=energy_backoff`는 다른 gmode 판정 후 **최종 덮어쓰기**라, 그 프레임의 G에는 백오프 이전 법칙도 함께 반영되어 있다.
- 결정 메시지와 별개로 측정값(`Distance`·`ATA`·`AA`·`HCA`·`RollOff`·`ClosureRate`·`Health`·`InWEZ`·`Gtarget`·`Gavail`)은 개별 numeric 속성으로 기록된다 — Tacview 시계열 그래프로 소비.
- 각도 정의는 BEM 정합(D7): `ATA`=내 기수(boresight)↔LOS, `AA`=적 종축 기준, `HCA`=양 기체 종축 사이 각.
