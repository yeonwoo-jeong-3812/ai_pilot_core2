# 코딩 계획 — INDI 최적화 연구 (2026-09-23 → 09-29 코드 동결)

근거: `paper.md` §0 결정 사항, §7 공통 변수·실험.
원칙: 기존 코드 재사용(`tournament.play_game`, `sweep_doctrine.py` 구조, `joblib` 병렬), 신규 의존성 0,
**기본값 = 현행과 비트 동일**(플랫폼·159 회귀 테스트 보존), 연구 하네스에서만 새 설정 사용.

## 실측 예산

매치 1회 ≈ 20 s(격추 종료), 최대 ≈ 40 s. 8코어 → 7 워커 ≈ **시간당 700~1,200경기**.

| 실험 | 규모 | 예상 |
|---|---|---|
| E2 Dogfight 민감도 | 6변수 × 5수준 = 30 config × 40경기 | ≈ 1–2 h |
| E3 기준 vs 최적 | 2 config × 4 대항군 × 64전 | ≈ 0.5–1 h |
| E4 PSO | 추종 벤치 비용(≈ 5 s/평가) × 20입자 × 30세대 | ≈ 1 h |
| E5 강건성 | 3 조건 × 2 config × 128전 + MC | ≈ 1–2 h |

→ 9/29 까지 **코드 + 스모크 실행**, 본 실행은 이후 배치.

## 일정

### 9/23 (수) — 준비 ✅
- [x] 프로젝트·논문 6편 분석 → `paper.md`
- [x] 결정: 교범 한계 봉투, 변수 6개
- [x] 실측: 매치 소요시간, 코어 수

### 9/24 (목) — 제어기 설정 주입 + 한계 봉투 ✅
- [x] `INDIConfig` (기본 = 현행), k_ff(동기화 LPF 평활 후 미분), λ(LM 채널별 스케일)
- [x] `Pilot(indi_cfg=)` → shim `k_att`·INDI 게인 주입, `make_pilot(indi_cfg=, envelope=)`
- [x] `LimiterConfig.envelope="manual"` — 교범 고정값(330/440 KCAS), 교리 코너 오버라이드 무시
- [x] **변경**: bridge·tournament 대신 `research/indi/runner.py` 가 직접 조립 — 서버 계약 무수정
- [x] 검증: 기본 설정 매치 결과 변경 전과 비트 동일, `tests/test_indi_study.py` 11건, 전체 235 통과
  (기존 실패 3건 `research/test_pipeline_invariants.py` 는 데이터 파일 부재 — 무관)
- 발견: 단일 tr(GᵀG) 스케일 λ 는 약한 yaw 채널 수렴 실패 → 채널별 스케일로 교체.
  무잡음 합성 플랜트에서 λ 는 "평활"이 아니라 **내곽 지연**으로 작용(λ=1 → 1 s 시점 롤 +32% 오버슈트)

### 9/25 (금) — E1 추종 벤치 + 한계 로거 + E6 시나리오
- `research/indi/bench.py` : 더블릿·3211·스텝(p, q 채널) × 운용점 6개(250/350/450 KCAS × 15k/25k ft)
  → 정규화 ISE, RMSE, 오버슈트, 정착시간, 승강타 포화율
- `research/indi/limits.py` : 달성 Nz max/min, G 오버슈트, G onset, AoA max, p max → 봉투 위반량(매치·벤치 공용)
- **추가(건의 채택)**: 센서 모델 옵션 `sensor="truth"|"gyro"` — gyro = 자이로 잡음 + 각가속도 차분 추정
  (`INDIRateController` 의 기존 `ang_accel=None` 경로). 참값 각가속도에서는 filt_hz·λ 의 존재 이유
  (잡음↔지연 상충)가 사라져 최적화가 filt_hz→상한, λ→0 으로 자명하게 수렴하기 때문 (논문 4·5 모두 잡음 포함)
- `scenarios.py` 에 `p1_neutral` (고도 5–20 kft/500, 속도 300–450, 거리 2–3 kft/100, 시드 결정론)

### 9/26 (토) — E2 단일 변수 민감도 드라이버
- `research/indi/sweep.py` : 변수당 5수준(기준 대비 ×0.5, ×0.75, ×1, ×1.5, ×2 / k_ff·λ 는 절대값), joblib 병렬
- 출력: 추종 벤치 비율 + Dogfight(고정 blue 트리, red = 기준 INDI 대항군 배터리) 승률·HP차·WEZ(ATA<2°) 체류 → JSON
- 실패 300% 절단, 봉투 위반 config 실격 플래그. 스모크(변수 1개 × 2수준)

### 9/27 (일) — E4 PSO 복합 최적화
- `research/indi/optimize.py` : numpy PSO(≈40줄, 논문 4 결과로 선택), 6차원 박스 = `paper.md` §7-C 범위
- 비용 = 정규화 ISE(E1) + γ·봉투위반량. γ ∈ {0, 0.1, 1, 10} → 파레토 JSON
- 스모크: 5입자 × 3세대

### 9/28 (월) — E3 Dogfight ablation + E5 강건성
- `research/indi/duel.py` : config A(기준) vs B(최적) — 대항군 4종 × 시나리오 5종(+p1_neutral) × 시드, 대항당 ≥ 64전
  → 승률(Wilson 95% CI), HP차, 교전시간, WEZ 체류, 한계 지표
- 강건성: G0 ×0.7/×1.3(`identify_G0` 결과 스케일), JSBSim 난류(`atmosphere/turb-type`), 측정 지연(n틱 버퍼)
- 몬테카를로: 초기 연료·G0 스케일 무작위, 시드 결정론

### 9/29 (화) — 통합·동결
- 전체 파이프라인 드라이런(E1→E2→E4→E3→E5 소규모), `pytest -q` 전체 통과
- `research/indi/README.md` : 실행 명령·출력 스키마 한 페이지
- **코드 동결** → 본 실행 배치 시작

## 산출물 트리

```
aircombat/control/indi.py      INDIConfig, λ, k_ff          (수정)
aircombat/control/limiter.py   envelope="manual"            (수정)
aircombat/engine/{pilot,factory}.py, guidance/bfm_guidance.py (인자 관통 ✅)
aircombat/engine/scenarios.py                                (p1_neutral)
research/indi/{runner,bench,limits,sweep,optimize,duel}.py  (신규, runner ✅)
tests/test_indi_study.py                                    (신규)
```

## 리스크

| 리스크 | 대응 |
|---|---|
| 교범 봉투로 기존 트리 성능 변화 | 양측 동일 봉투 적용 — 비교는 상대적, 플랫폼 기본값은 불변 |
| FLCS 경유로 게인 효과가 작게 나올 수 있음 | E1 포화율·G 오버슈트로 원인 분리, 그 자체가 결과 |
| 계산 시간 초과 | E4 는 추종 벤치 비용만(매치 제외), Dogfight 는 E2·E3 에 한정 |
