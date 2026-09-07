# 09 — core2 결함 감사 (core-live·gbrain 히스토리 함정 렌즈)

> 전제: **core2 구조를 정본으로 채택**(프로젝트 분기 방지). 단 core2가 정답이라 전제하지 않고, core-live가 17번 루프로 비싸게 배운 **검증 함정**을 체크리스트 삼아 core2를 감사하고 **그 구조 안에서** 고친다.
> 방법: 3개 병렬 감사(engine / debrief·geometry / guidance·control) + 룰북 §5–§8 정본 대조 + match.py 직접 확인.

---

> **⚠️ 2026-07-13 정정 (규칙 확정):** 대회 공식 룰북(V2, 엔진=ai-combat-core2)과 최종 WEZ가 확정됐다. 엔진 자체가 core2이므로 **core2 채점이 정본**이다. 이 보고서가 core-live RULEBOOK을 정본 가정하고 잡은 **F1(WEZ)·F2(안전판정)·F7(틱레이트)은 결함이 아닌 것으로 정정**한다:
> - **F1 해소** — 확정 §4 = ATA 30° 계단(2/10/20/30°→1.0/.75/.5/.25) + 거리 500–3000ft 균일 + **50 HP/s**. 아래 F1의 "12° 선형·거리감쇠" 정본 가정은 무효. 단 **로컬 core2는 DPS 25→50 동기화** 필요(레포 최종=50).
> - **F2 해소** — 룰북 §1·§5 = 참가자는 BT(YAML)만 제출, 비행제어층(리미터)은 전원 공통 → 과부하·스핀 구조적 불가 → 규정 없음이 의도. core2 주석과 룰북 일치.
> - **F7 해소** — 룰북 §2 = 물리 120Hz·L1 20Hz = core2 값.
>
> 남는 실질 항목: 로컬 DPS 동기화 1건 + F3(리플레이, 우리 인프라)·F5·F6(경미)·F4(확인). 종합·재검증 계획은 `10_REDTEAM_ANALYSIS.md`. **아래 F1·F2 원문은 정정 전 기록으로 보존한다.**

## 심각도순 결함표

| # | 결함 | 위치 | 심각도 | 대응 gbrain 히스토리 |
|---|---|---|---|---|
| **F1** | WEZ 채점 버그 (거리감쇠 부재 + ATA 30° 계층형) | `geometry/wez.py`, `geometry/units.py:171` | 🔴 치명 | [[core2-function-map-and-improvement]] |
| **F2** | 안전위반 판정 불완전 (과부하·스핀 누락) | `engine/match.py:27,203` | 🔴 치명(대회) | [[formal-advantage-event-laws]] |
| **F3** | replay 3라이터 미비 (ACMI만, plot·CSV 없음) | `engine/match.py:69` | 🟠 중 | [[feedback-replays-mandatory]] · [[feedback-replay-not-saved-writecsv-only]] |
| **F4** | 검증 대항이 kinematic (both-INDI 아님) | `engine/opponents/scripted.py` | 🟠 중(caveat) | [[core-engine-integration-pr35]] · [[real-match-duration-300s]] |
| **F5** | stall 누적 부동소수 knife-edge (10.0s 경계) | `engine/match.py:106` | ⚠️ 경 | [[cma-yaml-portable-but-knife-edge]] |
| **F6** | 단위상수 근사 (왕복정합 discipline 위반) | `guidance/bfm_guidance.py:35` | ⚠️ 경 | [[loop17-empty-dive-arm-declocked]] |

**안전 확인(함정 회피 성공):** 매치 길이 300s ✓ · outcome 단일경로 ✓ · 시계화 상수 0개 ✓ · knife-edge 전술상수 0개 ✓ · BFM 무상태 ✓ · Commit/Cooldown 결정론 ✓ · TAU 3-2-1 ✓ · 단위 왕복 ✓ · doctrine 수치 광역정합 ✓.

---

## F1 🔴 — WEZ 채점 버그 (치명, 정본 위반)

**두 감사 + 룰북으로 삼중 확증.** core2는 룰북과 **다른 게임을 채점**한다.

**정본(RULEBOOK §5):** `dHP/dt = 25·f_R(R)·f_ATA(ATA)`
- `f_R(R) = (3000−R)/2500`, 500→3000ft 선형 (500ft=1.0, 2000ft=0.4, 3000ft=0)
- `f_ATA(ATA) = (12−ATA)/12`, 0→12° 선형, **12° 초과=0**

**core2 실제(`wez.py`/`units.py:171`):**
```python
WEZ_ATA_TIERS = ((2.0, 1.00), (10.0, 0.75), (20.0, 0.50), (30.0, 0.25))  # 계층형, 30°까지
return DPS_MAX * _angle_coef(geometry.ata_deg()) * dt   # 거리계수 없음
```

**오채점 반례:**
| ATA / R | 룰북 dHP/dt | core2 dHP/dt | 오차 |
|---|---|---|---|
| 15°, 1000ft | **0** (12° 초과) | 12.5 | +12.5 |
| 20°, 2500ft | **0** | 12.5 | +12.5 |
| 5°, 2800ft | 25·0.583·0.08 ≈ 1.2 | 25·1.0 = 25 | +23.8 |

**왜 치명:** core2 위에서 튜닝·검증하는 모든 정책은 **틀린 물리로 최적화**된다. core-live의 42/42는 12°·거리감쇠 게임에서 나온 해다 — core2가 30°·거리무관이면 "nose-on gun dwell 최적화"([[ai-pilot-doctrine-optimizes-gun-wez-dwell]]) 목적함수 자체가 어긋난다. **다른 모든 수정보다 먼저**여야 한다.

**core2 구조 내 수정:** `wez.py`에 core-live `judge.py`의 선형 공식 이식.
```python
def _range_coef(r_ft):  return max(0.0, (3000.0 - r_ft) / 2500.0)  # 500ft=1, 3000ft=0
def _angle_coef(ata):   return max(0.0, (12.0 - ata) / 12.0)       # 0°=1, ≥12°=0
# calculate_damage: DPS_MAX * _range_coef(r) * _angle_coef(ata) * dt
```
`units.py:171` `WEZ_ATA_TIERS` 삭제. **검증:** core-live judge와 동일매치 데미지 궤적 0오차.

---

## F2 🔴 — 안전위반 판정 불완전 (대회 채점기로 부적격)

**근거 코드(`match.py:27`):**
```python
# over-G·스핀 위반 판정은 두지 않는다 — L3 리미터(코너 플래토 ∩ 9G)가 구조적으로 방지.
```
`_judge`(`match.py:203`)는 `hard_deck > stall > health_zero`만 판정. **룰북 §6/§8이 요구하는 과부하(\|n\|>9G/5s)·스핀(\|roll\|>360°/s/3s)이 통째로 빠짐.**

**왜 잘못:** 주석의 "리미터가 구조적 방지"는 **core2 자기 파일럿에만 참**. 플랫폼은 **임의 참가자 BT/제어스택**을 채점한다 — 참가자 정책이 9G를 넘거나 스핀에 빠지면 룰북상 즉시 패인데 core2 심판은 못 잡는다. 룰북 §8 우선순위 2번(OVERLOAD/SPIN/STALL) 중 2/3이 미구현. 이는 [[formal-advantage-event-laws]]의 "승패=권위있는 상태변수 사건법칙, 단일 판정경로" 원칙에 대한 **판정경로 누락**이다.

**참고 — 올바른 값(룰북 §6):** STALL은 이미 정합(`STALL_KTS=100.0`, `STALL_LIMIT_S=10.0`, 매치 누적 ✓). 누락된 2종:
- OVERLOAD: `|n_pilot| > 9.0 G`, 누적 5.0s
- SPIN: `|roll rate| > 360°/s`, 누적 3.0s

**core2 구조 내 수정:** `_stall`과 대칭으로 `_overload`/`_spin` 누적 딕셔너리 추가, 매 물리틱 조건검사, `_judge`의 `reason()`에 우선순위 반영(hard_deck > overload/spin/stall > health_zero). **검증:** 9G 초과를 강제하는 스텁 파일럿으로 5s 후 overload 패 확인.

---

## F3 🟠 — replay 3라이터 미비

`match.py:69`는 `ACMIWriter`만 배선. **plot(png)·CSV 미구현**(전체검색 0히트). [[feedback-replays-mandatory]](모든 실험은 ACMI+plot+csv 기본)·[[feedback-replay-not-saved-writecsv-only]](라이터 미배선 버그) 교훈 미반영. CSV가 없어 [[loop15-d2-00-converted-empty-dive-gate]]의 "per-tick live 계측"도 불가.

**core2 구조 내 수정:** core-live `engine/replay.py`의 `write_acmi_plot()`·`write_csv()`를 `debrief/`로 이식, `Match`에 `plot_path`/`csv_path` 추가해 ACMI와 원자적 동시 기록. **검증:** 1매치 3산출물 생성 + CSV 행수 = 로그틱수(dedup 없음).

---

## F4 🟠 — 검증 대항이 kinematic (both-INDI 아님) · caveat

`scripted.py`는 `psi += turn_rate*dt`, `pos += vel*dt`로 **위치 직접 적분** — INDI·JSBSim **우회**. **이건 버그가 아니라 설계**(빠른 dev용, `match.py:5` 주석이 self-play 인터페이스 명시). 위험은 **검증·랭킹에 scripted를 쓰면** core-live가 [[real-match-duration-300s]]·[[ours-yaml-beats-ace-300s]]에서 배운 "**both-INDI 300s가 유일한 진짜 검증**" 원칙을 어긴다는 것.

**core2 구조 내 조치:** `tournament.py`가 랭킹에 Pilot-vs-Pilot(both-INDI)만 쓰는지 확인·강제. scripted는 dev-only로 명시. **검증:** 랭킹 경로가 scripted를 배제하는지 코드 확인.

---

## F5 ⚠️ — stall 누적 부동소수 knife-edge

`match.py:106` `self._stall[side] += self.dt`(dt=1/120). **결정론적이나**(동일연산·동일순서→동일결과, 재현성은 OK) 10.0s 경계에서 1200회 누적오차가 판정을 가를 수 있다([[cma-yaml-portable-but-knife-edge]]의 5자리 카오스 민감과 동류). **수정:** 정수 틱카운트 누적 후 `count*dt` 비교, 또는 `count >= round(LIMIT/dt)`. 사소하나 경계 안정성↑.

---

## F6 ⚠️ — 단위상수 근사

`bfm_guidance.py:35` `FT_S_TO_KT = 0.592484`(6자리 하드코딩) vs core-live 엄격 역수 `1.0/KNOT_TO_FT_S`. 왕복 누적 ~0.1–0.5fps/1000회. [[loop17-empty-dive-arm-declocked]]의 "손튜닝 상수 → 물리 유도" discipline과 같은 결. **수정:** `FT_S_TO_KT = 1.0/(1852.0/(3600.0*0.3048))`.

---

## 실행 우선순위

```
1. F1 WEZ      ← 최우선. 이게 틀리면 이후 모든 검증이 무의미(틀린 게임).
2. F2 안전판정  ← 대회 채점 정합성. 참가자 제출 안전.
3. F3 replay   ← 분석·재현 인프라(F1/F2 검증에도 필요).
4. F4 확인     ← tournament.py 랭킹경로 both-INDI 강제.
5. F5·F6       ← 사소, 묶어서.
```

**대원칙:** F1·F2는 **correctness**(게임 정의) — 즉시. F3·F4는 **검증 인프라**. F5·F6은 **discipline**. correctness부터 고쳐야 "core2 위에서 42/42 재현되는가"라는 진짜 질문을 물을 수 있다.

## 관련
[[core2-function-map-and-improvement]] · [[core2-comparison-structure]] · [[formal-advantage-event-laws]] · [[feedback-replays-mandatory]] · [[real-match-duration-300s]] · [[cma-yaml-portable-but-knife-edge]] · [[ai-pilot-doctrine-optimizes-gun-wez-dwell]]
