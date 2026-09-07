import os
import sys

# 프로세스당 1회 감사 breadcrumb: 봉인이 **열린** 경우(임의 파이썬 실행 허용)만 stderr 로
# 경고한다. 기본(봉인)은 무출력 — silence=sealed 규약이라 대회 서버·SDK·툴 로그를 오염하지
# 않고, 위험 상태(custom 활성)일 때만 눈에 띈다. stdout(ACMI/데이터)은 어느 경우든 불침범.
if os.environ.get("AICOMBAT_ALLOW_CUSTOM", "0") == "1":
    print("AICOMBAT_ALLOW_CUSTOM=1 — custom 노드 활성(신뢰 환경 전용, 임의 파이썬 실행)",
          file=sys.stderr)
