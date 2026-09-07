# AI Pilot 경진대회 SDK (V2) — `{{SDK_VERSION}}`

행동트리(YAML) 하나로 F-16 1v1 교전 AI를 만든다. 서버와 같은 엔진 소스라 **로컬 결과 = 서버 결과**.
당신이 만드는 것은 전술 판단(L1)뿐 — 비행술(G·에너지·리프트벡터)은 전 참가자 공통의 BEM 교리 계층이 수행한다.
**같은 기체, 같은 비행술, 다른 두뇌.**

## 설치 → 첫 매치 (15분)

**Windows 명령 프롬프트(cmd)** 기준. Python 3.14 · 64-bit Windows 전용이다(엔진이 cp314-win_amd64).

```bat
py -3.14 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
python tools\selfcheck.py

copy examples\starter.yaml my_agents\my_agent.yaml
python tools\validate_agent.py my_agents\my_agent.yaml
python scripts\run_match.py --scenario headon --seed 1 --blue my_agents\my_agent.yaml --red examples\energy_fighter.yaml
```

`selfcheck.py` 가 `PASS` 를 내면 로컬 환경이 서버와 같은 방식으로 매치를 돌릴 준비가 된 것이다.

`replays/*.acmi` 를 [Tacview](https://www.tacview.net/)로 열어 복기: `ActiveNode`=그 순간 내 트리의 활성 전술(디버깅 핵심),
`GMode`/`PowerMode`/`AimAbove`=교리 계층의 실행, `Distance`/`ATA`/`AA`/`HCA`=조건 임계값 튜닝 근거.
Tacview 없이 보려면 `run_match.py --view` — 동봉된 브라우저 뷰어가 리플레이를 3D로 재생한다.

## 트리 만들기 — 3단계 요약

```yaml
# ① 액션 하나면 트리다              # ② 조건 게이트로 국면 분기
action: {pursuit: pure, name: chase}
```
```yaml
selector:                                     # 위에서부터 먼저 참인 분기
  - sequence:                                 # 방어: 조준당함 + 근접일 때만 (거리 게이트 필수!)
      - condition: {name: foe_threat, aspect_deg: 150}
      - condition: {name: merged, range_ft: 6000}
      - action: {pursuit: lag, g_burst: 0.8, name: break_defense}
  - sequence:
      - condition: {name: in_gun_envelope, range_ft: 3500, ata_deg: 45}
      - action: {pursuit: pure, name: gun_track}
  - action: {pursuit: lead, name: close_in}
```

어휘 전체(조건·액션 키·노드·교리값)는 [docs/REFERENCE.md](docs/REFERENCE.md) —
**엔진 코드에서 자동 생성**되어 항상 일치한다. 액션이 물리적으로 뭘 하는지는 [docs/MEASURED_BEHAVIOR.md](docs/MEASURED_BEHAVIOR.md) 실측 표.

## 흔한 실수 (전부 실측·실전 사례)

- 사격은 **pure** — 발사 원뿔은 위치(ATA) 기준. 정조준(ATA<2°)이 만점 50HP/s, lead 는 리드각만큼 ATA 가 벌어져 계수↓(룰북 §4 계단).
- 500 ft 미만 데미지 0 — 과접근 방지는 lag(`lag_dist_ft`)로. 3,000 ft 초과도 0.
- `g_burst` 남용 금지 — 순간 봉투를 계속 쓰면 에너지가 급락해 지속 선회가 무너진다(실측 표 참조). 태워야 할 국면에만 올릴 것. `max_g` 는 2026-08-24 폐지되었다(룰북 §10.1).
- 방어 분기에 거리 게이트 없으면 원거리 위협에도 발동 → 수세 고착.
- 회피는 최선이 무승부 — **이기려면 사격**해야 한다. 원뿔이 ATA 30°까지·500–3,000ft 균일이라 명중 기회는 넓다(룰북 §4).
- 저속 방치 = 실속패(100 kts 미만 누적 10 s). 수직 기동 후 에너지 회복 분기.
- **하드덱 회피는 일찍** — 급강하 관성 때문에 낮은 고도(예: 1,500ft)에서 회복하면 늦다.
  `low_altitude`(기본 4,000ft) 분기를 트리 최상단에 두어 완만한 하강에서 미리 잡아라(examples 참고).
  고도 임계값만으로는 강하각에 따라 여유가 달라진다 — 730 fps 강하면 4,500ft 가 6초뿐인데
  60° 강하 회복에 4,500ft 가 든다. `lookahead_s`(예: 3.5)로 침하율을 반영하면 트리거가
  강하율에 비례해 앞당겨진다(수평비행에서는 기본과 동일). 회복 액션에는 `aim_above_ft`
  (조준 오차 확보)와 `g_burst`(천장 해제)를 **함께** 줘라 — `aim_above_ft` 만으로는
  오차가 커져도 천장이 지속 봉투라 3~4G 로만 뽑고, `g_burst` 만으로는 조준 오차가 0 이라
  당길 이유가 없다(examples 의 recover_altitude 가 `g_burst: 0.8` + `aim_above_ft: 4000` 병용).
- 분기가 매 tick 튀면 `commit`/`cooldown` 으로 관성 부여.
- 리그는 `headon`/`perch_offense`/`perch_defense` 전 국면 평가 — 한 국면만 연습 금지.
  `examples/` 아키타입 7종(대표: attacker·energy_fighter·two_circle)을 스파링 상대로,
  `--seed` 고정해 전후 비교(결정론).

## 규칙·제출

판정·순위·제출 정책은 [docs/RULEBOOK.md](docs/RULEBOOK.md) 가 단일 진실 (필독).
제출 = 웹사이트에 YAML 업로드. 제출 전 `validate_agent` 한 번이면 실격(제출물 오류)을 예방한다.

트리 루트 옆에 최상위 `agent_name: 이름` 을 두면 리플레이(Tacview) 체력 바에 그 이름이 표시된다
(예: `agent_name: MyViper`). 미지정 시 blue_1/red_1.

**사용 조건**: 본 SDK 는 대회 참가 목적으로만 사용·수정 가능, 외부 재배포 금지.
제출물의 연구 활용은 룰북 §11. 저작권은 주최측에 있음.
