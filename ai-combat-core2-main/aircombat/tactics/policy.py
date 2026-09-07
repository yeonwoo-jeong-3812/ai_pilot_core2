"""L1 전술 정책 — BT 를 tick 해 (pursuit, g_burst 등) 명령 산출 + dwell 히스테리시스.

BT 는 매 tick reactive 하게 전술을 고르지만, 너무 잦은 전환은 기동을 흔든다.
dwell(최소 유지시간) 동안은 새 명령을 채택하지 않는다(V1 관행 0.3s).
"""
from __future__ import annotations

from .node import Node
from .context import TacticContext, TacticCommand
from .dsl import build_default, load_agent_yaml


class TacticPolicy:
    def __init__(self, root: Node | None = None, dwell_s: float = 0.3, dt: float = 1.0 / 20.0):
        self.root = root or build_default()
        # YAML 최상위 dwell_s: 오버라이드 (dsl.load_agent_yaml 이 루트에 실어 전달)
        self.dwell = float(getattr(self.root, "_dwell_s", dwell_s))
        self.dt = float(dt)
        self.doctrine_overrides: dict | None = None   # 에이전트 YAML doctrine: 블록 (원본)
        self.agent_name: str | None = None            # 에이전트 YAML agent_name: (표시용)
        self._cur = TacticCommand("lead", False, "default")
        self._t_since = 1e9   # 첫 tick 은 즉시 채택
        self._t = 0.0         # 자체 누적 시계 (Commit/Cooldown 용, 결정론)

    @classmethod
    def from_yaml(cls, path: str, **kw) -> "TacticPolicy":
        overrides, root, agent_name, dwell_s = load_agent_yaml(path)
        if dwell_s is not None:
            kw["dwell_s"] = dwell_s      # YAML 명시값이 호출부 기본값을 이긴다
        pol = cls(root=root, **kw)
        pol.doctrine_overrides = overrides
        pol.agent_name = agent_name
        return pol

    def tick(self, ctx: TacticContext) -> TacticCommand:
        ctx.trace.clear()
        ctx.t_s = self._t     # Commit/Cooldown 시계 주입 (매치 시간 불필요)
        ctx.dt_s = self.dt
        self._t += self.dt
        self.root.tick(ctx)
        proposed = TacticCommand(ctx._pursuit, ctx._tactic_name,
                                 ctx._aim_above_ft, ctx._lead_time_s, ctx._lag_dist_ft,
                                 ctx._mode, ctx._cz_range_ft, ctx._g_burst,
                                 ctx._g_full_ata_deg, ctx._track_rng_ft, ctx._track_ata_deg)
        self._t_since += self.dt
        if proposed != self._cur and self._t_since >= self.dwell:
            self._cur = proposed
            self._t_since = 0.0
        return self._cur
