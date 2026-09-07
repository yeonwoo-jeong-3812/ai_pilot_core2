# ai-combat-core2

[비공개] 1 vs 1 공중교전 환경 구축 — AI 파일럿 경진대회 개최용 **V2**.
JSBSim F-16 위에 **5계층 BFM 제어 스택**(저수준 제어: 순수 INDI)을 올린 연구·경진 플랫폼.

> as-built 사양·설계 결정(D1–D7)·수직 기동 교리는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 아키텍처 (5계층 + 폐루프)    

```
[L1  전술 BT]        20Hz  aircombat/tactics/     추격유형 + max-G + 조준점 기하(수직 오프셋/lead/lag)
      │ TacticCommand                              Commit/Cooldown 국면 안정화, 조건 20종(임계값 파라미터화)
[L2  BFM 가이드]★    60Hz  aircombat/guidance/    교리 기반 조절: 리프트벡터 배치 + G 조절 + 파워 스케줄
      │ dphi + q_cmd(G) + thrust                   수직 기동 = 조준점 오프셋(aim_above_ft) → L3 무변경
[L3  INDI 오토파일럿] 120Hz aircombat/control/     쿼터니언 shim → 결합 리미터 → INDI rate
      │ 조종면 [ail,elev,rud] + throttle
[L4  JSBSim 6-DoF]  120Hz aircombat/fdm/         F-16 + native FLCS
      │ 상태 피드백 → geometry/energy → L2·L1
      └┄(읽기전용 tap)┄▶ [L5 디브리핑] aircombat/debrief/  ACMI/Tacview (GMode/AimAbove 감사 속성)
```

★ **L2(교리 기반 G·리프트벡터 조절)가 연구 본체** — "감사가능(auditable) AI 전술".

## 모듈

| 경로 | 계층 | 내용 |
|---|---|---|
| `aircombat/fdm/` | L4 | `F16Plant` (JSBSim 래퍼, 포팅) |
| `aircombat/control/` | L3 | `indi.py`(검증된 INDI) · `limiter.py`(코너플래토+AoA→G∩9G) · `attitude.py`(쿼터니언 shim) |
| `aircombat/guidance/` | L2 | `bfm_guidance.py`(조절 법칙 — 교리 setpoint 전 항목 결선) · `doctrine.py`(BEM setpoint) |
| `aircombat/tactics/` | L1 | 경량 BT + YAML DSL (`node`·`conditions`·`dsl`·`policy`) — Commit/Cooldown·파라미터화 |
| `aircombat/geometry/` | — | `combat_geometry.py` · `wez.py` (포팅) |
| `aircombat/engine/` | L5 | `pilot`·`match`(다중레이트 스케줄러+judge)·`opponents/`(스크립트 적기) |
| `aircombat/debrief/` | L5 | `acmi.py` · `tacview_realtime.py`(TCP:42674) |
| `examples/` | — | 참가자용 예시 2종(starter·textbook) — 문법 학습·베이스라인 |
| `lab/` | — | 내부 연구 에이전트(비배포) — 챔피언/아키타입, SDK 빌드 제외(FORBIDDEN) |

## 설치

버전 핀 고정(numpy·jsbsim·pyyaml)이 재현성의 전제이므로 **격리된 가상환경**에 설치한다.
전역 파이썬을 오염시키면 서버와의 물리·수치 동일성 보장이 깨질 수 있다.

**방법 A — `uv` (권장, 빠름)**

```bash
uv venv                            # .venv 생성 (파이썬 3.11+)
uv pip install -r requirements.txt
# 실행 시: `uv run python scripts/...` 또는 아래 activate 후 `python ...`
```

**방법 B — 표준 `venv`**

```bash
python -m venv .venv               # .venv 생성
# 활성화:  Linux/macOS →  source .venv/bin/activate
#          Windows(PowerShell) →  .venv\Scripts\Activate.ps1
pip install -r requirements.txt    # numpy, jsbsim, pyyaml
```

> `.venv/` 는 `.gitignore` 됨. 이후 「실행 / 검증」의 명령은 활성화된(또는 `uv run` 접두) 셸에서 실행한다.

## 실행 / 검증

```bash
python scripts/run_indi_step.py    # L3: 45° 뱅크 스텝 (기대 ~44°, 오버슈트 ~1.8°, q·r RMS<3.5)
python scripts/run_guidance_track.py  # L2: 스크립트 표적 BFM 조절 추적 (감사 로그)
python scripts/run_match.py                                  # 1v1 스크립트 적기 → replays/match.acmi
python -m pytest -q                                          # 회귀 테스트 (159)
```

### 자가대전 (Pilot vs Pilot)

```bash
# headon: V1 룰북식 대칭 IC (양측 15,000ft·350KCAS·상호 대향·6NM).
# 이 페어(공세형 미러전)는 HP 교환이 가장 큰 데모 (180s: 89.3 vs 88.5)
python scripts/run_match.py --scenario headon --blue lab/attacker.yaml --red lab/attacker.yaml

# energy_fighter vs two_circle: 하드덱 결판 데모 (159.7s: 94.7 vs 99.0)
python scripts/run_match.py --scenario headon --blue lab/energy_fighter.yaml --red lab/two_circle.yaml

# 새들 트래킹(closure_ctl + track_lock) 데모: 기본 트리 vs 선회 적기 — 60s에 red 63.4
python scripts/run_match.py --duration 60

# perch: 오버슈트 유발 세팅 (blue 가 red 후방 3,000ft·+100kt) — 요요 데모
python scripts/run_match.py --scenario perch --red scripted:straight

# red 는 YAML(자가대전) 또는 scripted:{turn|straight|extend|break}

# --analyze: 매치 후 교전 분석 자동 실행 (acmi 옆에 _wez·_energy·_tactics.png 3종 저장)
python scripts/run_match.py --scenario headon --blue lab/attacker.yaml --analyze
python scripts/analyze_wez.py replays/xxx.acmi   # 기존 acmi 단독 분석도 가능
```

건 솔루션은 ATA 30° 원뿔·500–3,000ft 균일(정조준 ATA<2° 만점 50HP/s, 룰북 §4 계단).
ATA·AA·HCA 는 BEM 정의 정합 — **종축(기수) 기준**, 속도벡터 아님 (D7, 2026-07-17).
대등한 두 기체가 서로 제대로 방어하면 교환은 통과 순간의 스냅샷 위주가 되며,
리그 순위는 (V1 과 동일하게) 잔여 HP 차이로 갈린다.

`.acmi` 를 Tacview 로 열면 `ActiveNode`(전술)·`GMode`·`PowerMode`·`AimAbove`(수직 오프셋) 속성으로
요요 국면을 육안 확인할 수 있다. 실시간은 `TacviewRealtimeServer`(TCP:42674).

### ACMI 브라우저 뷰어 (Tacview 불필요)

```bash
python tools/acmi_viewer/server.py     # → http://127.0.0.1:7900
```

`replays/` 의 `.acmi` 를 브라우저에서 3D 재생(three.js) — 항적·WEZ 원뿔·Health/전술값·
L1~L3 결정 문자열·HIT 북마크 타임라인. 외부 의존성 없음(Python stdlib + vendored three.js).
상세·웹 이식 노트: [tools/acmi_viewer/README.md](tools/acmi_viewer/README.md)

### 전술 트리 작성 (새 어휘)

```yaml
selector:
  - sequence:                                       # 조건 임계값 파라미터화
      - condition: {name: overshoot_risk, closure_fps: 120, range_ft: 2500}
      - action: {pursuit: lag, name: yoyo_up,
                 aim_above_ft: 750,                 # 조준점 수직 오프셋 [ft] (+위/-아래)
                 lead_time_s: 1.5, lag_dist_ft: 2000}
  - commit: {name: rate_fight, duration_s: 2.0, cooldown_s: 2.0,   # 국면 래치
             child: {sequence: [{condition: merged},
                                {action: {pursuit: lead, g_burst: 0.8, name: entry}}]}}
  - cooldown: {wait_s: 5.0, child: {...}}           # 재진입 차단 (chattering 방지)
```

조건 20종·기본 임계값은 `aircombat/tactics/conditions.py`(함수 시그니처 = 단일 진실),
액션 키는 화이트리스트(오타 시 ValueError). `config/tactics.yaml`(기본 트리)은 회귀 기준 — 불변.

## 스택 불변식 (변경 주의)

- L3 내곽은 **INDI 유지** (PID/LQR 금지, D2). V1 의 RNN/임시 LQR·INDI 는 참고하지 않음.
- L2 출력은 각속도(+추력); 자세는 **쿼터니언 shim** 경유 (D3, Euler 특이점 제거).
- L5 는 L4 를 **읽기만** 함 (D5, 제어경로 위험 0).
- 당김은 **조절(regulation)**, 반사적 max-G 금지, 상한은 코너 플래토 (D6). initial_pull 포함 전 G 경로가 리미터·g_fraction 상한 내.
- 난수 0 — Commit/Cooldown 등 신규 상태는 결정론 시계(`ctx.t_s`) 기반.
