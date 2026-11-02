# 예비 실험 (관문 2) 판단 규칙

**이 문서는 실행 전에 커밋했다.** 결과를 본 뒤 바꾼 것은 `bt/out/pilot_report.md`의 "규칙과 다르게 처리한 것"에 따로 적는다.

## 실험

- θ: `bt/thetas/pilot_lhs50.csv` = `designs.lhs(50, seed=20261102)`. `params.yaml` 범위 안 라틴 하이퍼큐브 50점, dummy 포함 11차원.
- 시드: `bt-pilot` (`bt-pilot-0..3`). θ 하나 = 48경기 (기하 3 × 상대 4 × 시드 4), 모든 θ 가 같은 48셀을 쓴다.
- 실행: `python bt/run_bt.py bt/thetas/pilot_lhs50.csv --prefix bt-pilot --procs 6` → `bt/out/bt-pilot/games.csv`.
- 지표 (경기 하나의 값): **승** = 청 승 1, 그 외 0 (무승부 0). **wez 차** = `wez_blue − wez_red` [s].
- 분석 대상 경기: `end_reason == "wall_clock"` 경기는 뺀다 (CONTRACT §5). 뺀 수는 (4)에 적는다.

## (1) θ 신호 — 관문 2 판정

지표마다:
- θ 평균 `m_i` = θ i 의 48경기 평균. 경기 간 분산 `s_i²` = θ i 안의 48경기 표본분산.
- 잡음 몫 `N = mean_i(s_i² / n_i)` (n_i = θ i 의 분석 대상 경기 수, 보통 48).
- θ 분산 `V = var_i(m_i) − N` (var 는 표본분산, 분모 50 − 1).
- 비율 `R = V / N`.
- **부트스트랩 95% CI:** θ 50개를 복원추출해 (θ 단위 군집 부트스트랩, θ 안의 경기는 그대로) V 와 R 을 다시 계산.
  2,000회, 난수 seed 20261102, 백분위 2.5–97.5%.
- **관문 2 통과:** (2)에서 고른 1차 지표의 V 의 CI 하한 > 0.
- 참고: 모든 θ 가 같은 48셀을 쓰므로 셀(기하·상대·시드) 효과는 θ 평균에 똑같이 들어가 var(m_i)에 기여하지 않는다.
  그런데 `s_i²`에는 셀 효과가 들어가므로 N 은 θ 평균의 실제 잡음보다 크게 잡힌다 (보수적). 규칙은 위 정의 그대로 쓴다.

## (2) 1차 지표 선택

- (1)의 R (점추정) 이 큰 쪽을 1차 지표로 한다.
- 큰 쪽 R / 작은 쪽 R ≤ 1.5 이면 (또는 승률 R 이 더 커도 그 비가 1.5 이내면) **wez 차**를 택한다. 근거: R0 에서 승률은 상대 자멸(실속·하드덱)에 흔들렸다.
- 한쪽 R ≤ 0 이면 다른 쪽을 택한다. 둘 다 ≤ 0 이면 wez 차를 1차 지표로 두고 관문 2 는 불통과.

## (3) 범위 점검 — 노드 작동

- 파라미터 → 걸린 노드 (`params.yaml`의 node 를 실제 action 노드로):

  | 파라미터 | 노드 (node_frac 키) |
  |---|---|
  | merge_range_ft, threat_aspect_deg, break_g_burst | break_defense |
  | gun_range_ft, gun_ata_deg | gun_track |
  | fight_kcas | energy_recover |
  | energy_min_ft, lead_time_s | press_offense |
  | closing_min_fps | yoyo_pull_up |
  | floor_ft | recover_altitude |
  | dummy | (없음, 점검 안 함) |

- "실행 안 됨" = 그 경기의 `node_frac`에 노드가 없거나 0 (20 Hz 표본에 한 번도 안 잡힘).
- 파라미터 범위를 θ 값 기준 3등분 (lo–1/3, 1/3–2/3, 2/3–hi) 하고 구간마다 "실행 안 됨" 경기 비율을 낸다.
- **비활성:** 세 구간 모두에서 "실행 안 됨" 경기 비율 ≥ 90%. 일부 구간만 ≥ 90% 이면 "구간 비활성"으로 따로 표시한다.
- 노드의 평균 node_frac 도 구간별로 낸다.
- 범위 수정 제안은 이 노드 작동 근거로만 한다. 승패·wez 결과는 근거로 쓰지 않는다.

## (4) 품질

- wall_clock 경기 수, 실패 경기 수 (= `end_reason`이 `wall_clock` 또는 `disqualified`이거나, 실행 중 예외로 기록되지 않은 경기 = 2,400 − 기록 수), 경기당 wall_s 평균·최대.

## (5) 탐색적 분석

- 파라미터별 θ 평균과의 상관 (스피어만) 이나 순위는 계산해도 표에 **"탐색적, 확증 아님"**으로 표시한다.
- 이것을 범위나 설계 변경의 근거로 쓰지 않는다. dummy 의 상관을 잡음 기준선으로 함께 보인다.

## 보고에 함께 넣는 것

- win_mode 분포 (shootdown 격추승, opp_hard_deck 상대 하드덱, opp_stall 상대 실속, judge 판정, other).
- 기하별·상대별 평균 (승률, wez 차).
