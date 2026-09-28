# 코딩 계획 — INDI 최적화 연구 (2026-09-23 → 09-29 코드 동결)

근거: `paper.md` §0 결정 사항, §7 공통 변수·실험.
원칙: 기존 코드 재사용(`tournament.play_game`, `sweep_doctrine.py` 구조, `joblib` 병렬), 신규 의존성 0,
**기본값 = 현행과 비트 동일**(플랫폼·159 회귀 테스트 보존), 연구 하네스에서만 새 설정 사용.

## 실측 예산 (본 실행, 7 워커)

| 실험 | 명령 | 규모 | 예상 |
|---|---|---|---|
| E4 PSO | `optimize.py --out results/indi/e4.json` | γ 4 × 20입자 × 30세대 = 2,400 평가(13 s) | ≈ 1.3 h |
| E2 민감도 | `sweep.py --out results/indi/e2.json` | 25 config × 50경기 + bench | ≈ 1.5–2 h |
| E3 명목 | `duel.py --best …e4.json --conds nominal --seeds 1…13` | 2 × 325경기 (대항당 65) | ≈ 1 h |
| E5 강건성 | `duel.py --best …e4.json --conds stress delay30 delay90 g0_lo g0_hi turb mc` | 7 × 2 × 100경기 | ≈ 2 h |

결과는 `results/indi/` (gitignore — 논문 확정본만 별도 보관).

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

### 9/25 (금) — E1 추종 벤치 + 한계 로거 + E6 시나리오 ✅
- [x] `research/indi/limits.py` 한계 기록기(Nz vs 교범 봉투, G onset, AoA, 롤레이트, 승강타 포화, 실격)
- [x] `research/indi/bench.py` E1: 6 운용점 × {bank, p3211, q_dbl, q_step}, 공통 난수, 1회 평가 13 s
- [x] `scenarios.py` `p1_neutral` (논문 1 조건)
- [x] **연구용 수정 모델 `jsbsim_data/aircraft/f16fix`** (사용자 결정) — 원본 f16 무수정
- 발견: JSBSim 공식 F-16(pip 1.3.1 동일)의 flaperon 혼합 `left=−tef−ail, right=+tef−ail` → 합 −2·ail →
  **롤 명령이 대칭 양력·항력 생성** (5,000 ft/400 KCAS 에일러론 단독: 오른쪽 −2.1G / 왼쪽 +4.1G, 좌우 비대칭).
  원본 모델에선 기준 제어기도 교범 봉투 초과 36기체 중 28(최대 10.7G).
  수정: 오른쪽 aileron 부호 반전 → aileron 도 tef 처럼 좌우 상쇄(CLDflaps·CDDflaps ≡ 0 = 원본의 무롤 물리).
  롤레이트 ±84.7°/s 대칭(원본 85.8/85.3). **f16fix 에선 보호 없이 60기체·경기 초과 0, 최대 Nz 7.83G**
- Nz 보호(`nz_protect`)는 옵션으로만 유지, 연구 기본 **끔** — 켜면 튜닝 제어기 오버슈트를 가림
- 기준 벤치(f16fix, gyro 0.1°/s): J = 0.229, 실격 없음

### 9/26–9/28 — E2·E4·E3+E5 드라이버 ✅ (9/28 일괄 작성, 일정 2일 지연분 흡수)
- [x] `runner.py` 공용: 평가조건 `cond`(G0 스케일·MIL-SPEC 난류, 측별 시드 고정 — setup 래핑, 엔진 무수정),
      대응비교 배터리(blue 트리 고정 × red 5종 × 시나리오 5종 × 시드), `pmap` 병렬, `game`(잡음 시드 = 경기 시드 = CRN)
- [x] `sweep.py` E2: 6변수 × 5수준(filt_hz 3/6/12/25/40), bench J/J₀(실격 3.0 절단) + 기준과의 **대응 차이**
      Δ승점·ΔHP + 부트스트랩 95% CI. 스모크 73 s — k_q ×2 → J ×6(잡음 증폭), ΔHP −62
- [x] `optimize.py` E4: numpy PSO(w .7, c1=c2 1.5), filt_hz 로그축, 비용 J/J₀ + γ·A/A₀ + 실격 10,
      전 평가점 비지배 전선 = 파레토. **변경**: g_x 를 봉투 위반 → 조종면 활동량 A 로 (f16fix 에서 위반이 항상 0 이라
      파레토 불성립; 교범 "신속함과 부드러움"). 스모크 8평가 만에 J/J₀ 0.97·A/A₀ 0.16 (filt ≈ 4 Hz, λ ≈ 0.35)
- [x] `duel.py` E3+E5 통합: A(기준) vs B(E4 최적 또는 직접 지정) × 조건 8종
      {nominal, stress 0.3°/s, delay 33/92 ms, G0 ×0.7/×1.3, 난류 sev 4, MC(G0 U(0.7,1.3)·난류 0–4)},
      승률 Wilson CI·대응 Δ·격추 수·한계 실격. 스모크 2분
- [x] 순수 함수 테스트 5건(파레토, 로그축 왕복, Wilson, MC 결정론, 대응 차이) — 전체 249 통과

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
research/indi/{runner,bench,limits,sweep,optimize,duel}.py  (신규 ✅)
tests/test_indi_study.py                                    (신규)
```

## 리스크

| 리스크 | 대응 |
|---|---|
| 교범 봉투로 기존 트리 성능 변화 | 양측 동일 봉투 적용 — 비교는 상대적, 플랫폼 기본값은 불변 |
| FLCS 경유로 게인 효과가 작게 나올 수 있음 | E1 포화율·G 오버슈트로 원인 분리, 그 자체가 결과 |
| 계산 시간 초과 | E4 는 추종 벤치 비용만(매치 제외), Dogfight 는 E2·E3 에 한정 |
