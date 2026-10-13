"""병렬 경기 수 자동 결정 — 코어 수와 메모리 중 작은 쪽. 환경변수 INDI_WORKERS 가 있으면 그 값.

경기 1개(JSBSim 2대)는 약 0.85 GB 를 쓴다. 8 GB 노트북에서 3개를 돌리다 메모리 부족으로 종료된 적이 있어
OS·기타 몫으로 4 GB 를 남기고 경기당 1.5 GB 로 잡는다 (8 GB → 2, 16 GB → 8, 32 GB → 코어 수 − 1).
aircombat 를 import 하지 않는다 — cross_partner 가 파트너 엔진을 불러오기 전에 쓰기 때문.
"""
from __future__ import annotations

import os


def ram_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (AttributeError, ValueError, OSError):        # Windows
        import ctypes

        class M(ctypes.Structure):
            _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ("tot", "av", "tp", "ap", "tv", "av2", "ext")]
        m = M()
        m.len = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.tot / 2 ** 30


def auto_workers() -> int:
    if os.environ.get("INDI_WORKERS"):
        return int(os.environ["INDI_WORKERS"])
    return max(1, min((os.cpu_count() or 2) - 1, int((ram_gb() - 4.0) / 1.5)))
