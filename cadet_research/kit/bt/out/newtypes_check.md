# newtypes 상대 묶음 합격 점검

기준 θ × 72경기 (bt-smoke 시드, `--opponents newtypes`). 기준은 `bt/analysis/opponent_patch_rules.md` 와 같다 (상대 행동만).

| 기준 | 값 | 한도 | 판정 |
|---|---|---|---|
| 상대 하드덱 비율 (전체) | 0.000 | ≤ 0.05 | O |
| 상대 하드덱 비율 (상대별 최대) | 0.000 (C2_OneCircleRad_00) | ≤ 0.1 | O |
| 상대 고도 회복 노드 실행 비율 (평균) | 0.125 | ≤ 0.2 | O |

**판정: 합격**

| 상대 | 경기 | 상대 하드덱 | 회복 노드 비율 | 청 하드덱 | 청 승률 | wall_clock |
|---|---|---|---|---|---|---|
| C2_OneCircleRad_00 | 12 | 0.000 | 0.116 | 0.000 | 0.000 | 0 |
| C3_Lufbery_00 | 12 | 0.000 | 0.003 | 0.000 | 0.167 | 0 |
| D2_LastDitch_00 | 12 | 0.000 | 0.299 | 0.000 | 0.833 | 0 |
| E1_AdaptiveAce_00 | 12 | 0.000 | 0.094 | 0.000 | 0.000 | 0 |
| red_energy | 12 | 0.000 | 0.212 | 0.000 | 0.417 | 0 |
| red_tracker | 12 | 0.000 | 0.025 | 0.000 | 0.000 | 0 |

승리 방식 (청 승 17): shootdown 1, opp_hard_deck 0, opp_stall 0, judge 16, other 0
종료 사유: {'timeout': 36, 'health_zero': 30, 'no_contact': 6}

