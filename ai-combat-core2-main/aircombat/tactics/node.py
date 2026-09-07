"""경량 BT 실행기 — Sequence / Selector / Condition / Action / Inverter / Commit / Cooldown.

reactive(매 tick 루트부터 재평가). L1(20Hz) 전술 선택엔 RUNNING 상태 불필요 —
Condition→SUCCESS/FAILURE, Action→SUCCESS. Selector 는 우선순위 폴백.

Commit/Cooldown 은 국면 안정화 데코레이터(chattering 방지). 시계는 ctx.t_s
(TacticPolicy 가 자체 누적 주입 — 결정론). Preemption 은 별도 기제 없이 트리
배치로 해결: Selector 상위 브랜치가 성공하면 Commit 은 tick 되지 않고,
t0 가 절대시각이라 상위 조건 해제 시 잔여 래치로 자연 복귀한다.
"""
from __future__ import annotations

from enum import Enum
from typing import Callable


class Status(Enum):
    SUCCESS = 1
    FAILURE = 2


class Node:
    def tick(self, ctx) -> Status:
        raise NotImplementedError


class Condition(Node):
    def __init__(self, name: str, fn: Callable):
        self.name = name
        self.fn = fn    # 임계값 오버라이드는 dsl 이 functools.partial 로 바인딩

    def tick(self, ctx) -> Status:
        ok = bool(self.fn(ctx))
        ctx.trace.append((self.name, ok))   # 감사: 어떤 조건이 참이었나
        return Status.SUCCESS if ok else Status.FAILURE


class Action(Node):
    def __init__(self, pursuit: str, name: str | None = None,
                 aim_above_ft: float | None = None,
                 lead_time_s: float | None = None,
                 lag_dist_ft: float | None = None,
                 mode: str | None = None,
                 cz_range_ft: float | None = None,
                 g_burst: float | None = None,
                 g_full_ata_deg: float | None = None,
                 track_rng_ft: float | None = None,
                 track_ata_deg: float | None = None):
        self.pursuit = pursuit
        self.name = name or (f"{pursuit}+burst{g_burst:g}" if g_burst else pursuit)
        self.aim_above_ft = aim_above_ft
        self.lead_time_s = lead_time_s
        self.lag_dist_ft = lag_dist_ft
        self.mode = mode
        self.cz_range_ft = cz_range_ft
        self.g_burst = g_burst
        self.g_full_ata_deg = g_full_ata_deg
        self.track_rng_ft = track_rng_ft
        self.track_ata_deg = track_ata_deg

    def tick(self, ctx) -> Status:
        ctx.set_command(self.pursuit, self.name,
                        aim_above_ft=self.aim_above_ft,
                        lead_time_s=self.lead_time_s,
                        lag_dist_ft=self.lag_dist_ft,
                        mode=self.mode,
                        cz_range_ft=self.cz_range_ft,
                        g_burst=self.g_burst,
                        g_full_ata_deg=self.g_full_ata_deg,
                        track_rng_ft=self.track_rng_ft,
                        track_ata_deg=self.track_ata_deg)
        return Status.SUCCESS


class Sequence(Node):
    def __init__(self, children: list[Node]):
        self.children = children

    def tick(self, ctx) -> Status:
        for c in self.children:
            if c.tick(ctx) is not Status.SUCCESS:
                return Status.FAILURE
        return Status.SUCCESS


class Selector(Node):
    def __init__(self, children: list[Node]):
        self.children = children

    def tick(self, ctx) -> Status:
        for c in self.children:
            if c.tick(ctx) is Status.SUCCESS:
                return Status.SUCCESS
        return Status.FAILURE


class Inverter(Node):
    def __init__(self, child: Node):
        self.child = child

    def tick(self, ctx) -> Status:
        s = self.child.tick(ctx)
        return Status.FAILURE if s is Status.SUCCESS else Status.SUCCESS


# 스냅샷/리플레이 대상 = ctx 출력 필드 (set_command 가 쓰는 전부)
_CMD_FIELDS = ("_pursuit", "_tactic_name",
               "_aim_above_ft", "_lead_time_s", "_lag_dist_ft", "_mode",
               "_cz_range_ft", "_g_burst", "_g_full_ata_deg",
               "_track_rng_ft", "_track_ata_deg")


class Commit(Node):
    """브랜치 진입 잠금 — 요요 등 다단 기동을 duration_s 동안 유지(4.4.6.2.3).

    · 미래치 상태에서 child SUCCESS → 래치(t0=ctx.t_s), 이후 duration_s 동안:
        child 를 계속 tick — SUCCESS 면 명령 갱신(트리 분기가 국면 전환 담당),
        FAILURE 면 직전 명령 스냅샷 리플레이(기동 중단 없음).
    · 만료 → cooldown_s 동안 재진입 차단(FAILURE) — 즉시 재래치 chattering 방지.
    · trace 에 latch/hold/replay/cooldown 기록(감사).
    """

    def __init__(self, child: Node, name: str = "commit",
                 duration_s: float = 4.0, cooldown_s: float = 0.0):
        self.child = child
        self.name = name
        self.duration = float(duration_s)
        self.cooldown = float(cooldown_s)
        self._t0: float | None = None        # 래치 시작(절대시각), None=미래치
        self._cd_until: float = -1e18        # 쿨다운 종료 시각
        self._snapshot: tuple | None = None  # 래치 중 직전 명령

    def _capture(self, ctx) -> tuple:
        return tuple(getattr(ctx, f) for f in _CMD_FIELDS)

    def _replay(self, ctx) -> None:
        for f, v in zip(_CMD_FIELDS, self._snapshot):
            setattr(ctx, f, v)

    def tick(self, ctx) -> Status:
        t = ctx.t_s
        if self._t0 is not None and t - self._t0 >= self.duration:
            self._t0 = None                          # 래치 만료 → 쿨다운 개시
            self._cd_until = t + self.cooldown
            self._snapshot = None
        if self._t0 is None:
            if t < self._cd_until:
                ctx.trace.append((f"commit:{self.name}", "cooldown"))
                return Status.FAILURE
            s = self.child.tick(ctx)
            if s is Status.SUCCESS:                  # 진입 → 래치
                self._t0 = t
                self._snapshot = self._capture(ctx)
                ctx.trace.append((f"commit:{self.name}", "latch"))
            return s
        # 래치 중: child 계속 tick (국면 전환은 child 내부 분기가 담당)
        s = self.child.tick(ctx)
        if s is Status.SUCCESS:
            self._snapshot = self._capture(ctx)
            ctx.trace.append((f"commit:{self.name}", "hold"))
        else:
            self._replay(ctx)                        # 조건 일시 이탈 → 직전 명령 유지
            ctx.trace.append((f"commit:{self.name}", "replay"))
        return Status.SUCCESS


class Cooldown(Node):
    """재진입 차단 데코레이터 — child 의 성공 국면이 끝난 뒤 wait_s 동안 FAILURE.

    child 가 연속 SUCCESS 인 동안은 그대로 통과(활동 지속). SUCCESS→FAILURE
    전이(활동 종료) 시점부터 wait_s 동안 child 를 tick 하지 않고 차단 —
    경계 임계값 근처 재진입 chattering 방지(예: 에너지 회복 브랜치).
    """

    def __init__(self, child: Node, wait_s: float = 5.0, name: str = "cooldown"):
        self.child = child
        self.name = name
        self.wait = float(wait_s)
        self._active = False                 # 직전 tick 이 SUCCESS 였나
        self._cd_until: float = -1e18

    def tick(self, ctx) -> Status:
        t = ctx.t_s
        if t < self._cd_until:
            ctx.trace.append((f"cooldown:{self.name}", "blocked"))
            return Status.FAILURE
        s = self.child.tick(ctx)
        if s is Status.SUCCESS:
            self._active = True
        else:
            if self._active:                 # 활동 종료 → 쿨다운 개시
                self._cd_until = t + self.wait
                ctx.trace.append((f"cooldown:{self.name}", "start"))
            self._active = False
        return s
