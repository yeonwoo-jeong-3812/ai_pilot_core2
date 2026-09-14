# 탐색 단계 프로브 (2026-09-14)

`docs/FINDINGS_2026-09-14.md` 와 `docs/EXPERIMENT_PLAN.md` §0 에 인용된 수치를 낸 일회성 계측 스크립트.
결과 파일을 쓰지 않고 표준출력으로만 보고한다. 논문 본실행에는 쓰지 않는다 — 같은 측정은
`research/l3_indi/` 하네스로 다시 한다.

| 스크립트 | 인용처 | 측정 |
|---|---|---|
| `diag_indi.py` | FINDINGS [4] | 뱅크 60° 정상상태 INDI 증분 분해 (러더 적분 와인드업) |
| `rud_travel.py` | FINDINGS [4] | 러더 명령 0.25/0.5/1.0 → 실제 타면각 (1초 안정화) |
| `rud_step.py` | FINDINGS [4] | 러더 명령 1.0 스텝의 과도 타면각, yaw-load-pid |
| `max_nz.py` | FINDINGS [5] | INDI 없이 풀애프트 스틱 최대 Nz (300~450 KCAS) |
| `fbw_probe.py` | PLAN F4, F5, F6 | fbw-override 0/1 개루프 안정성, 최대 Nz, G0, INDI 당김 |
| `trace_probe.py` | PLAN F7, F8, F9, F11 | 자가대전 1경기(duel, seed 1) L3 지령·포화·대역폭 분포 |
