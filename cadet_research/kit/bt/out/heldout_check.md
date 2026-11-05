# heldout 상대 묶음 합격 점검

기준 θ × 48경기 (bt-smoke 시드, `--opponents heldout`). 기준은 `bt/analysis/opponent_patch_rules.md` 와 같다 (상대 행동만).

| 기준 | 값 | 한도 | 판정 |
|---|---|---|---|
| 상대 하드덱 비율 (전체) | 0.000 | ≤ 0.05 | O |
| 상대 하드덱 비율 (상대별 최대) | 0.000 (A1_PurePursuer_00) | ≤ 0.1 | O |
| 상대 고도 회복 노드 실행 비율 (평균) | 0.101 | ≤ 0.2 | O |

**판정: 합격**

| 상대 | 경기 | 상대 하드덱 | 회복 노드 비율 | 청 하드덱 | 청 승률 | wall_clock |
|---|---|---|---|---|---|---|
| A1_PurePursuer_00 | 12 | 0.000 | 0.187 | 0.000 | 0.333 | 0 |
| A3_LagAngler_00 | 12 | 0.000 | 0.203 | 0.000 | 0.417 | 0 |
| B1_EnergyFighter_00 | 12 | 0.000 | 0.003 | 0.000 | 0.167 | 0 |
| red_prime | 12 | 0.000 | 0.011 | 0.000 | 0.000 | 0 |

승리 방식 (청 승 11): shootdown 2, opp_hard_deck 0, opp_stall 0, judge 9, other 0
종료 사유: {'timeout': 26, 'health_zero': 20, 'no_contact': 2}

