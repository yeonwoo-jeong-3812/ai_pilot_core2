"""Pilot 조립 팩토리 — run_match(CLI)·bridge(서버 어댑터) 공용.

과실 도메인을 두 단계로 분리한다:
  load_policy   참가자 제출물 파싱·검증 — 실패는 DISQUALIFY 사유 (참가자 과실)
  make_pilot    plant 생성·트림·5계층 조립 — 실패는 엔진 결함 (인프라 오류)
"""
from __future__ import annotations

import os

from ..fdm.plant import F16Plant
from ..guidance.bfm_guidance import BFMGuidance
from ..guidance.doctrine import Doctrine
from ..control.indi import INDIConfig
from ..tactics.policy import TacticPolicy
from .pilot import Pilot


def load_policy(yaml_path: str) -> tuple[TacticPolicy, Doctrine]:
    """참가자 에이전트 YAML → (전술 정책, 교리). 파일 없음·문법 오류·미지 노드·
    doctrine 위반은 전부 여기서 예외 — 호출자(bridge)가 DQ 로 판정한다."""
    if not os.path.isfile(yaml_path):
        raise FileNotFoundError(f"에이전트 파일 없음: {yaml_path}")
    policy = TacticPolicy.from_yaml(yaml_path)
    return policy, Doctrine.from_overrides(policy.doctrine_overrides)


def make_pilot(color: str, ic: dict, policy: TacticPolicy, doctrine: Doctrine,
               name: str = "F-16", indi_cfg: INDIConfig | None = None,
               envelope: str = "platform") -> Pilot:
    """시나리오 IC 한쪽({pos, psi, kcas, alt})으로 Pilot 조립.

    파일럿별 트리 별도 build 전제 — Commit/Cooldown 노드가 상태를 가지므로
    두 기체가 policy 를 공유하면 안 된다 (호출자 책임).
    """
    plant = F16Plant(dt=1.0 / 120.0)
    plant.set_ic(alt_ft=ic["alt"], vc_kts=ic["kcas"], psi_deg=ic["psi"])
    plant["fcs/throttle-cmd-norm"] = 0.85
    plant.trim()
    # indi_cfg/envelope 는 연구 하네스(research/indi) 전용 — 서버 경로(bridge)는 기본값.
    pilot = Pilot(plant, color=color, init_pos_ned=tuple(ic["pos"]), policy=policy,
                  guidance=BFMGuidance(doctrine=doctrine, envelope=envelope),
                  indi_cfg=indi_cfg)   # ACMI Name 은 항상 기체 모델(F-16) — Tacview 심볼/3D 모델 선택 키
    # 표시용 에이전트 이름(ACMI CallSign) — 서버 전달 이름(팀, 권위) 우선, 없으면 YAML agent_name.
    pilot.agent_name = (name if name != "F-16" else None) or getattr(policy, "agent_name", None)
    return pilot
