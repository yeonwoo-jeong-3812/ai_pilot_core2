# F-16 Dogfight AI 제어 스택 — 아키텍처 (as-built)

> **목적:** JSBSim F-16 기반 공중교전 AI 제어 스택. 생도 Airmanship 교육 + 특화연구실 제1세부(검증가능·신뢰성 AI 공중교전 전술) 연구 플랫폼.
> **문서 지위:** 초기 구현 계획([tmp/f16_bfm_control_architecture.md](../tmp/f16_bfm_control_architecture.md))을 **구현 완료 후 as-built 사양으로 승격 개정**한 것. §3의 확정 결정(D1–D7)은 구현으로 유지 확인됨 — 재론하지 말 것.
> **제약:** Python 중심 · 배포 계획 없음(완성도 우선) · 결정론(난수 0).

---

## 1. 최종 아키텍처 (5계층 + 폐루프) — 구현 완료

```
[L1  전술 계층 (BT)]                 aircombat/tactics/   · 20Hz · ✅
      │  전술 명령 (추격유형·max-G·조준점 기하: aim_above/lead/lag)
      ▼
[L2  기동 가이드 블록] ★연구 본체   aircombat/guidance/  · 60Hz · ✅
      │  dphi(리프트벡터 배치) + q_cmd(G) + thrust (교리 setpoint 조절)
      ▼
[L3  오토파일럿 (shim+리미터+INDI)]  aircombat/control/   · 120Hz · ✅
      │  조종면 명령 (aileron/elevator/rudder + throttle)
      ▼
[L4  JSBSim 6-DoF (F-16)]           aircombat/fdm/       · 120Hz · ✅
      │
      ├── 상태 피드백 → L2, L3 (rates, qbar, 자세, 에너지, 상대기하)
      │
      └┄┄(읽기전용 tap)┄┄▶ [L5  시각화·디브리핑]  aircombat/debrief/ · ✅
                              ACMI(사후) + TCP:42674(실시간) → Tacview
```

**폐루프:** L4 상태가 L3·L2로 피드백. L1은 전술 상태(상대 기하)를 읽음. L5는 L4를 **읽기만** 하므로 제어 경로와 완전 분리(위험 0).

**다중레이트 스케줄러**(`aircombat/engine/match.py`): 물리 120Hz 기준으로 L2=÷2(60Hz), L1=÷6(20Hz). 계획 단계의 5/50Hz 는 구현에서 20/60Hz 로 확정(120 의 정수 분주 — 위상 정렬·결정론).

---

## 2. 계층별 사양 (as-built)

| 계층 | 책임 | 모듈 · 주기 | 입력 → 출력 |
|------|------|------------|------------|
| **L1** 전술 | 교전 판단: 추격유형(lead/pure/lag)·max-G·조준점 기하(수직 오프셋/lead/lag 오버라이드). Commit/Cooldown 국면 안정화 | `tactics/` (node·conditions·dsl·policy) · 20Hz | TacticContext → TacticCommand |
| **L2** 가이드 ★ | 교리 setpoint 조절: 리프트벡터 배치(dphi) + G 조절 + 파워 스케줄 | `guidance/bfm_guidance.py` + `doctrine.py` · 60Hz | 전술 명령 → dphi·q_cmd·thrust + audit |
| **L3** 오토파일럿 | 쿼터니언 shim → 결합 리미터 → INDI rate 제어 | `control/` (attitude·limiter·indi) · 120Hz | 자세율·추력 → 조종면 |
| **L4** FDM | 6-DoF 항공역학 적분 (F-16 + native FLCS) | `fdm/plant.py` (JSBSim 1.3.1) · 120Hz | 조종면 → 기체 상태 |
| **L5** 디브리핑 | 매치 실행·WEZ judge + ACMI/Tacview | `engine/` + `debrief/` · 로그 30Hz | L4 상태(tap) → .acmi/TCP |

---

## 3. 확정된 설계 결정 (D1–D7) — 구현으로 유지 확인

**D1. 저수준 제어는 순수 Python INDI를 JSBSim에 직접 연결. PX4 Offboard 사용 안 함.**
근거: PX4 Offboard는 ~10–50Hz MAVLink 제약, native INDI 없음, 거대한 통합 표면. 직접 함수호출 루프가 120Hz 실주기와 완성도 모두 우위. → **유지: `Pilot.control_step` 이 매 tick 직접 호출.**

**D2. 내곽 제어기는 INDI. PID/LQR 사용 안 함.**
근거: 제어 효과가 동압에 따라 배수로 변함 — INDI는 측정 각가속도로 상쇄(40% 모델오차에도 정상상태 0.06°/s). → **유지: `control/indi.py`. 본 개선 라운드도 L3 무변경.**

**D3. 자세 변환은 쿼터니언. Euler 각도 setpoint 사용 안 함.**
근거: Euler θ≈±90° 특이 = 수직 기동이 벌어지는 곳. → **유지·활용: 수직 기동(요요)은 3D 조준점 오프셋 → dphi 로 실행되어 shim/L3 수정이 필요 없었음(§4.5).**

**D4. Paparazzi는 레퍼런스로만. 런타임에 사용 안 함.** → 유지.

**D5. 시각화·디브리핑은 Tacview/ACMI. 수동·비침습.**
→ **유지·확장: `_gc.audit`(L2 감사)를 ACMI 속성(GMode/PowerMode/AimAbove/ActiveNode/Gtarget)으로 노출 — 읽기전용 원칙 그대로.**

**D6. L2는 추종(tracking)이 아니라 조절(regulation). BFM 교리 기반.**
→ **유지: 모든 G 경로가 `g_avail`(리미터)·`g_fraction`(명목 상한) 아래. g_burst 는 천장 보간일 뿐 조절을 우회하지 않고, initial_pull 도 `min(7G, g_nom)`.**

**D7. 교전 기하는 BEM 정의 정합 — 각도는 종축(boresight) 기준. (2026-07-17)**
근거: BEM §4.8.2.4(ATA=기수↔LOS)·§4.8.2.3(AA=적 종축)·§4.3.3.3(HCA=양 종축 각).
구 구현은 속도벡터 기준(점질량 근사)이라 고AoA 에서 룰북 문언("내 기수 원뿔")과
불일치했다. `CombatGeometry` 가 양측 자세(θ/ψ)를 받아 종축으로 산출 — WEZ 판정·
L2 조절·L1 조건·ACMI 가 모두 이 정의를 공유. 1/2-circle 은 순간 HCA 프록시에서
**선회방향 flow**(반대 방향=1-circle, BEM 4.4.4)로 전환(`ctx.my/foe_turn_dir`).
리드 미반영 단순화(wez.py 헤더)는 별개로 유지.

---

## 4. L2 상세 사양 — BFM 교리 기반 (연구 본체)

출처: *Korean AF Basic Employment Manual, F-16C, Vol.5 (2005)*, Chapter 4.

### 4.1 핵심 반전 — 공격 BFM ≠ max-G

교범은 반사적 최대 G를 **명시적으로 금지**:
- 4.4.5.2 — 초기 진입도 "typically 6G to 8G", "**it is not mechanical, but a pull to solve the given problem**".
- 4.4.6.2.2 — "How much G ... but it is **typically just off the limiter**", 적을 ATA 35–50°에 두도록 조절.
- 4.4.6.2.3 — "**stuck in lag is to pull too hard when not required**".
- 4.4.7.2 — "**DO NOT stay on the limiter** and try to fit inside the adversary's turn circle."
- 4.3.3.7 (목표) — "point nose at defender ... with an **acceptable Ps bleed-off**".

→ 실제 "aggressive" = **코너 플래토에서 우월한 지속 선회율로 압박하며 LV·G로 기하를 WEZ로 몰아감**.

### 4.2 교리 setpoint 와 코드 소비처 (전 항목 결선 완료)

| 항목 | 값 (교범 §) | `Doctrine` 필드 | 코드 소비처 |
|------|------------|------------|------------|
| 코너 플래토 | 330–440 KCAS (4.3.3.7) | `corner_kcas_lo/hi` | `BFMGuidance.__init__` → `LimiterConfig` 생성 (교리=단일 진실, Pilot 은 `guid.limiter` 공유) |
| 파이팅 속도 | 325–375 kt (4.4.6.2.2) | `fighting_kts_lo/hi` | `_power` 대역 스케줄 · `_regulate_g` 에너지 백오프 · L1 조건 `below/above_fighting_speed` 기본값 |
| 에너지 우위 | 50–75 kt (4.4.6.2.2) | `energy_margin_lo/hi` | `_power`: 대역 내 상대 TAS 우위 <50kt→1.0, 50–75 선형, ≥75→0.85 (`margin_regain`) |
| 슬랜트 거리 | 4,000–6,000 ft (4.4.6.2.1) | `slant_ft_lo/hi` | audit `in_slant_band` · 진입 기하 판정(`entry_geom`, ×2 원거리 판정) |
| ATA 목표 | 35–50° (4.4.6.2.2) | `ata_target_lo/hi` | audit `in_ata_band` (ATA 비례 G 의 검사 기준) |
| 진입 속도 | 450–480 KCAS (4.4.4.2) | `entry_kcas` | `_power`: 원거리(>2×slant_hi)·미달 시 AB (`AB_entry`) |
| 건 접근 파워 | "modulate power to control closure" (4.4.12.1), idle 까지 (4.4.13.1) | — (기하 유도) | `_power`: 후방 반구·<2,500ft 에서 과잉 접근율을 MIL→idle 비례 컷, 허용치는 900ft 트레일로 수렴하는 깔때기 (`closure_ctl`) |
| 건 추적 G | 추적 사격의 전제 = LOS 회전율 일치 (4.4.10.2) | — (기하 유도) | `_regulate_g`: 건 접근 기하(<2,500ft·후방·ATA<30°)에서 `n=V·ω_LOS/g×1.15` 하한 (`track_lock`) — 획득 법칙(ATA 비례)의 원뿔 직전 평형 해소 |
| LV 배치 | 적 POM 살짝 위 500–1,000 ft (4.4.5.2) | `lv_above_ft` | `compute`: L1 미지정 + 머지 진입 기하 → 자동 `aim_above_ft=+750` (L1 명시값 우선) |
| 초기 당김 | 6–8 G (4.4.5.2) | `initial_pull_g` | `_regulate_g`: aspect>120°·rng<slant_hi → `min(7G, g_nom)` (`initial_pull`) |
| 명목 상한 | "리미터 살짝 아래" (4.4.7.2) | `g_fraction` | `_regulate_g` g_nom = g_avail×0.95 |

### 4.3 교정된 당김 법칙 (구현 확정)

1. **제어 대상 = 기하 오차** (aspect·ATA·HCA·거리), 목표 = 교리 setpoint.
2. **G 목표 = ATA 비례(획득) + 추적 하한 + 상황 오버라이드**: `g = clip(g_nom/45° × ATA, g_min, g_nom)` → 건 접근 기하(<2,500ft·후방·ATA<30°)에선 LOS 회전율 일치 G(`track_lock`, 4.4.10.2)가 하한 → 머지 진입이면 initial_pull(≤7G) → 저속이면 에너지 백오프. 상한 = 코너 플래토 리미터 × g_fraction. 획득 법칙만으로는 근거리 선회 표적에서 WEZ 원뿔 직전 평형에 갇힌다 — 획득≠추적.
3. **에너지 하드 제약 + closure 조절**: 파이팅 대역 유지 + 진입 가속(entry_kcas) + 에너지 마진(50–75kt) + **건 접근 closure 파워 컷**(`closure_ctl`, 4.4.12.1 "modulate power to control closure" — MIL→idle, 900ft 트레일 수렴 깔때기). 스로틀 캘리브레이션: f16.xml FCS 가 pos=2×cmd (augmethod=2) — **cmd 0.5=MIL, 0.6부터 AB 점화, 1.0=full AB, 0.0=idle** (실측 15kft/350kt: 11.2k/13.3k/21.6k/−0.9k lbs). 구 스케줄의 0.85/0.6 은 실제로는 AB 영역이었음.
4. **상황별 버스트**: L1 이 `g_burst`(0~1)로 지속↔순간 봉투 천장을 지정 (적 연장 4.4.8.2.1, 방어 브레이크 등). 지령 G 는 기수→조준점 각도에 비례 — 이진 우회 경로는 2026-08-24 폐지.

### 4.4 성능식 (교범 Table 4.8)

```
Turn Radius (ft)      = V² / (g · G_radial),   V = KTAS × 1.69,  g = 32.2
Turn Rate  (deg/s)    = (G_radial × 1092) / KTAS
```
- Radial G: **지구 쪽으로 당기면** 속도 보존·net G 증가 — §4.5 요요의 물리 기반.

### 4.5 수직 기동 교리 (신설 — 본 라운드 구현)

**실행 원리 — 조준점 수직 오프셋:** L2 는 γ 명령이나 기동 시퀀서 없이 **무상태**를 유지한다. 조준점에 수직 오프셋(`aim_above_ft`, NED 위=+)을 더하면 `dphi = atan2(aim_body_y, −aim_body_z)` 가 3D 조준점을 리프트벡터 배치로 실행하므로 **L3/L4 무변경**으로 수직 기동이 성립한다(D3 쿼터니언 shim 이 특이점을 제거). 국면 전환(진입→정점→재강하)은 L1 트리 분기 + Commit 래치가 담당한다.

**하이 요요 (4.4.6.2.3, 4.4.7.2):** 오버슈트 위험(빠른 접근 + 근거리)에서 lag + 조준점을 적 기동면(POM) **위**로(+750ft) — 접근율을 수직으로 소산. 정점(적이 아래 + 접근율 정리)에서 lead + 아래(−300ft)로 재강하해 공격 기하 회복. `redteams/red_attacker.yaml` 의 high_yoyo 가지 (commit 4s / cooldown 3s; 테스트 픽스처 `tests/fixtures/high_yoyo.yaml`).

**로우 요요 (4.4.6.2.3):** 각도 열세·거리 정체(기수 이탈 + 접근율 없음)에서 적 선회원 **아래**로 다이브 컷(−500ft, 중력 가속·radial G) → 접근율이 붙으면 되당김(+150ft). `examples/energy_fighter.yaml` 의 low_yoyo 가지 (commit 3s / cooldown 3s).

**LV 배치 (4.4.5.2):** 머지 진입(aspect>120°, 슬랜트 이내)에서 L1 이 오프셋을 지정하지 않으면 교리 자동 +`lv_above_ft`(750ft) — "적 POM 살짝 위" + initial_pull 이 같은 조항의 두 처방으로 같은 기하에서 소비된다.

**수직 정점 에너지:** 별도 KCAS→G 보호 루프는 두지 않는다 — ①리미터 G∝KCAS² 가 물리 안전 보장, ②파워 스케줄이 저속에서 이미 AB, ③프리셋 duration≤4–5s·오프셋≤800ft 가 소산 상한. 검증은 테스트 불변식으로 고정(`tests/test_vertical.py`: 요요 중 min KCAS>250·하드덱 무위반·max|θ|>15° 또는 Δalt>500ft).

---

## 5. L1 전술 계층 (as-built)

- **노드:** Sequence / Selector / Condition / Action / Inverter + **Commit**(래치 duration_s + 만료 후 cooldown_s; 래치 중에도 child tick — SUCCESS→명령 갱신, FAILURE→직전 명령 리플레이) + **Cooldown**(성공 국면 종료 후 wait_s 재진입 차단). Preemption 은 별도 기제 없이 **트리 배치**: Selector 상위 브랜치가 성공하면 Commit 은 tick 되지 않고, t0 절대시각이라 해제 시 잔여 래치로 자연 복귀.
- **시계:** `TacticPolicy` 자체 누적(`ctx.t_s/dt_s`) — 매치 시간 주입 불필요, 결정론.
- **조건 14종** (`conditions.py`): 기존 6(foe_threat/overshoot_risk/foe_extending/in_gun_envelope/nose_far/energy_advantage) + 신규 8(foe_above/foe_below/behind_foe/merged/one_circle/closing/below·above_fighting_speed). 전부 `fn(ctx, *, 임계값=기본값)` — **함수 시그니처가 파라미터 스펙의 단일 진실**(dsl 이 inspect 로 검증, partial 바인딩). 파이팅 대역 기본값은 Doctrine 에서.
- **조건 히스테리시스는 보류:** dwell(0.3s, policy)과 Commit/Cooldown 이 명령·국면 두 층위의 chattering 을 이미 덮는다. 조건 단위 값-밴드 히스테리시스는 필요가 관측되면 추가.
- **DSL** (`dsl.py`): 조건 dict 스키마(`{name, 임계값...}`), 액션 키 화이트리스트(미지 키 ValueError — 오타를 조용히 무시하지 않음), commit/cooldown 파서.
- **아키타입:** `examples/`(attacker·energy_fighter·two_circle 등 — 새 어휘 사용례 겸 스파링 상대; 요요 기동 가지는 각 트리에 인라인). `config/tactics.yaml`(기본 트리)은 불변 — 회귀 기준. 엔진 설정(`config/`)과 참가자 자료(`examples/`·`agents/`)는 최상위에서 분리.

---

## 6. 매치 엔진 / 자가대전 (as-built)

- **대칭 인터페이스:** `state/setup/tactic_step/guidance_step/control_step/step_physics/telemetry` — Pilot(JSBSim)과 ScriptedOpponent(운동학)가 동일, `Match` 가 lockstep 처리. **자가대전 = red 자리에 Pilot** (F16Plant 2개 동시 생성·결정론 확인됨).
- **파일럿별 트리 별도 build** — Commit/Cooldown 노드가 상태를 가지므로 공유 금지 (`tests/test_selfplay.py` 가드).
- **시나리오** (`engine/scenarios.py` — BEM 국면 매핑): `headon`(HABFM, V1 룰북식 대칭 IC) / `perch_offense`(OBFM, blue 후방 3,000ft·+100kt 우위 — 구 `perch`) / `perch_defense`(DBFM, 진영 스왑) / `neutral`(중립 머지 — 3,000ft 측방 이격). **시드 지터**: (scenario, seed) → 결정론 IC (고도 12–18kft, 속도 330–370, 방위 ±30°, 분리 ±20%). `swap_sides()` 로 진영 스왑 미러. 리그는 `LEAGUE_SCENARIOS`(3종 — `perch_defense` 는 스왑 미러와 중복이라 제외), 웹 배터리·건틀릿은 `BATTERY_SCENARIOS`(4종, 참가자 진영 고정이라 역할 구분 유효).
- **판정(대회 룰, 2026-07-03):** ① 하드덱 1,000ft ② 실속 <100kts 누적 10s(비행 안전 위반 — over-G·스핀은 L3 리미터가 구조적 방지라 규칙 없음) ③ HP≤0 ④ 참가자 트리 예외 = DISQUALIFIED(L1 tick 격리) ⑤ wall-clock 가드(기본 120s) = 무승부 ⑥ 300s 타임아웃 시 HP 우세. **Gun WEZ(2026-07-13 개정)**: 50 HP/s × 각도계수(BEM lethal burst 1–2s 근거, 2026-07-13 25→50 상향), 500–3,000ft 균일(거리계수 없음), 각도계수는 ATA 계단(<2°=1.0/<10°=0.75/<20°=0.5/<30°=0.25/≥30°=0, `units.WEZ_ATA_TIERS`). 시간 완화 제거.

---

## 7. 미결 결정 사항 — 정리 (4건 해소 / 3건 잔여)

| 항목 | 계획 시점 | 확정 |
|---|---|---|
| 당김 G-목표 조절 법칙 | 비례 vs 최적선회율 추종 | ✅ **ATA 비례(g_nom/45°) + initial_pull 오버라이드 + 에너지 백오프** (§4.3) |
| 적기 | 스크립트 vs 자가대전 vs 병행 | ✅ **병행** — scripted 4종 + Pilot vs Pilot 자가대전 (§6) |
| 적분 주기 | L1 5Hz / L2 50Hz 안 | ✅ **L1 20 / L2 60 / L3·L4 120Hz** (120 정수 분주) |
| 리포지토리 구조 | ai-combat-sdk 통합 위치 | ✅ **ai-combat-core2 독립 저장소**, `aircombat/` 단일 패키지 |
| WEZ 파라미터화 | gun/missile 추상화 | ✅ **각도 tier 로 개정(2026-07-11)** — `units.WEZ_ATA_TIERS`(50HP/s×각도계수 — 2026-07-13 상향, 거리 균일, 시간 완화 제거). 구 시간완화(WEZ_PHASES)는 폐지. gun/missile 추상화는 미착수(올해 gun 전용) |
| 서버 통합 | ai-combat-server 파이프라인 연동 | ⏳ 잔여 — V1 대체 시점에 submissions/matches 스키마 접속 (계획: tmp/competition_platform_plan.md Phase 2) |
| 조건 히스테리시스 | 값-밴드 hysteresis | ⏳ **의도적 보류** — dwell+Commit/Cooldown 이 두 층위를 덮음(§5). 필요 관측 시 추가 |

---

## 8. 검증 자산

- `tests/` 86건: 기하·WEZ·리미터·INDI·shim·가이던스(17)·전술(26)·엔진·ACMI + **자가대전 결정론(test_selfplay)** + **수직 기동 물리(test_vertical — perch 세팅, 요요 vs pure 비교)**.
- `scripts/run_indi_step.py` — L3 45° 뱅크 스텝 (기대 ~44°, 오버슈트 ~1.8°).
- `scripts/run_guidance_track.py` — L2 교리 조절 추적 (감사 로그, verdict PASS).
- `scripts/run_match.py` — end-to-end 매치 → .acmi (Tacview 에서 GMode/AimAbove 로 요요 국면 육안 확인).

### 부록 A. JSBSim 속성 매핑

| 용도 | 속성 |
|------|------|
| 각속도 p,q,r | `velocities/p-rad_sec`, `q-rad_sec`, `r-rad_sec` |
| 각가속도 (INDI 입력) | `accelerations/pdot-rad_sec2`, `qdot-rad_sec2`, `rdot-rad_sec2` |
| 동압 | `aero/qbar-psf` |
| 받음각 (리미터) | `aero/alpha-rad` |
| 자세 | `attitude/phi-rad`, `theta-rad`, `psi-rad` (또는 `-deg`) |
| 위치 (ACMI) | `position/long-gc-deg`, `lat-geod-deg`, `h-sl-meters` |
| 속도 | `velocities/vt-fps`, `vc-kts` |
| 조종면 명령 | `fcs/aileron-cmd-norm`, `elevator-cmd-norm`, `rudder-cmd-norm`, `throttle-cmd-norm` |

### 부록 B. 스택 불변식 (변경 주의 — 2026-07-03 대회 플랫폼화 라운드에서 문구 개정)

- L3 내곽은 INDI 유지, PID/LQR로 되돌리지 말 것(D2).
- L2 출력은 각속도(+추력); 자세 각도를 직접 주면 쿼터니언 shim 경유(D3).
- L5는 L4를 읽기만 하며 제어 경로에 개입 금지(D5).
- 당김은 조절(regulation)이며 반사적 max-G 금지, 상한은 코너 플래토(D6/§4.3). initial_pull 포함 모든 G 는 `g_avail`·`g_fraction` 상한 내.
- **자생 난수 0 — 유일한 난수원은 외부 주입 매치 시드**(시나리오 IC 지터, `engine/scenarios.py`).
  시드 고정 시 완전 결정론. 신규 상태(Commit/Cooldown)는 결정론 시계(`ctx.t_s`) 기반.
- **L2 조절·L3 제어 "법칙"은 무변경 원칙.** 단 ①파라미터 주입 경로(per-pilot `Doctrine`
  — `Doctrine.from_overrides`, 교범 대역 검증, 개방 플래그 `TUNING_ENABLED`)
  ②audit 관측 전용 필드 추가는 **기본값 행동 보존 증명**(기존 테스트·리그 결과 불변) 조건으로 허용.
- 물리·제어 주기(120Hz) 변경은 성능 게이트 실패 시에만, 스택 재검증 동반 (2026-07-03 벤치: 300s 매치 21.4s wall ≈ 14× 실시간 — 게이트 통과).
- 스톡 F-16은 자체 FCS 보유 → 제어 대상은 "기체+내장 FCS". `identify_G0`가 경험적으로 흡수.
- JSBSim F-16 고AoA/post-stall 충실도는 제한적 — 실속 관련 연구는 충실도 상한 명시.
