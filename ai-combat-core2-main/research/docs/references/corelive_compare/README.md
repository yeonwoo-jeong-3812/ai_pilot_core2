# core2 ↔ core-live 비교 작업공간

동료의 **core2**(`ai-combat-core2`, 우리 new-engine 기반 증류본)와 우리 **core-live**를 L1~L4 전계층 1:1 비교한 자료 모음.

## 1:1 매핑용 심볼릭 링크 (정션)

두 프로젝트를 이 디렉토리에서 나란히 열람·diff 하도록 정션(junction)을 걸어두었다:

| 링크 | 실제 위치 |
|---|---|
| `_core2/` | `../../../core2/aircombat/` (core2 패키지 전체) |
| `_corelive_engine/` | `../../src/engine/` (core-live 엔진) |

**1:1 파일 diff 예시(Git Bash):**
```bash
cd docs/core2_compare
diff _core2/fdm/plant.py _corelive_engine/control/plant.py          # L4
diff _core2/control/indi.py _corelive_engine/control/indi.py        # L3 INDI
diff _core2/guidance/bfm_guidance.py _corelive_engine/control/guidance.py  # L2
```
> 정션이라 관리자권한/개발자모드 불필요. 링크를 지우려면 `Remove-Item _core2 -Force`(대상 원본은 안전).

## 문서 목록

| 문서 | 내용 |
|---|---|
| `01_STRUCTURE.md` | graphify 구조분석 — core2=증류본, core-live=연구엔진 |
| `02_L4.md` | 물리/FDM — 동률(plant 바이트-동일) |
| `03_L3.md` | 오토파일럿/제어 — 제어공학 core2 / 검증 core-live |
| `04_L2.md` | 가이던스(연구본체) — 지능위치 분기 |
| `05_L1.md` | 전술/BT — 역할분담 |
| `06_SUMMARY.md` | 전계층 종합 우열 + 흡수 로드맵 |
| `07_FUNCTION_MAP.md` | **코드별 기능 분석 — 파일·함수 1:1 대응표** |
| `08_IMPROVEMENT.md` | 양측 부족분 반영 통합 개선안(best-of-both) |
| `09_INSPECTION.md` | core2 결함 감사 상세 — F1~F7 증거·반례·코드 |
| `10_REDTEAM_ANALYSIS.md` | **Red Team 종합 — 계층구조 + 문제진단(두 축) + 개선 로드맵** |

> **읽는 순서:** 구조부터 보려면 `01`~`06`(계층별 상세) 또는 `10` Part A(요약). 결함·개선만 보려면 `10`(종합) → `09`(증거 상세). `10`이 이 세션의 정본 요약이다(구 10~12를 목적별로 하나로 통합).
