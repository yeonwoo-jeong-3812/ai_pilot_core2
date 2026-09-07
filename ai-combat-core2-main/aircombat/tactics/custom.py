"""커스텀 조건·노드 확장 — core-live 공유상태 idiom 의 core2 이식 (2026-07-18).

동기: 점수-장부(적 HP 부기)류 **상태 보유** 전술 로직은 무상태 조건 화이트리스트로
표현이 불가하다. core2 에는 이미 상태 보유 노드 선례(Commit/Cooldown)가 있으므로,
같은 원리를 참가자/연구자 정의 노드로 개방하는 등록 메커니즘을 제공한다.

**기본 봉인(fail-closed)**: custom_module 로드는 기본 거부된다. 임의 파이썬을
실행하므로 신뢰된 환경(리서치/블루팀)만 `AICOMBAT_ALLOW_CUSTOM=1` 로 명시적으로
켠다. 대회 서버·SDK 는 무설정으로 안전(거부) — 메커니즘(이 파일)과 정책의 분리.

사용법:
  # my_custom.py (에이전트 YAML 과 같은 폴더 또는 하위)
  from aircombat.tactics.custom import custom_condition, custom_node
  from aircombat.tactics.node import Node, Status

  @custom_condition("hp_lead_between")          # 무상태 조건: fn(ctx, **kw)->bool
  def hp_lead_between(ctx, *, lo=1.0, hi=8.0):
      ...

  @custom_node("score_ledger")                  # 상태 보유 노드: Node 서브클래스
  class ScoreLedger(Node):
      def __init__(self, *, dps=50.0):          # 파라미터는 YAML 에서 주입
          self.foe_dmg = 0.0                    # 상태는 인스턴스에 (Commit 선례)
      def tick(self, ctx):
          ...
          return Status.SUCCESS

  # agent.yaml
  custom_module: my_custom.py
  selector:
    - {"custom": {"name": "score_ledger", "dps": 50}}
    - sequence: [{condition: {name: hp_lead_between, lo: 1, hi: 8}}, ...]

감사(auditability): 커스텀 조건도 Condition 래퍼를 거치므로 trace 에 이름·결과가
기록되고, 커스텀 노드는 ctx.trace 에 스스로 기록할 것을 권장한다.
"""
from __future__ import annotations

import importlib.util
import os

# 등록 레지스트리 — custom_module 이 import 되는 시점에 데코레이터가 채운다.
CUSTOM_CONDITIONS: dict = {}   # name -> fn(ctx, **kw) -> bool
CUSTOM_NODES: dict = {}        # name -> Node 서브클래스 (인스턴스가 상태 보유)
_LOADED: set = set()           # 로드된 모듈 절대경로 — 같은 파일 재실행 방지
                               # (배치에서 매 판 트리를 다시 빌드해도 등록은 1회)


def custom_condition(name: str):
    def deco(fn):
        if name in CUSTOM_CONDITIONS:
            raise ValueError(f"커스텀 조건 중복 등록: {name}")
        CUSTOM_CONDITIONS[name] = fn
        return fn
    return deco


def custom_node(name: str):
    def deco(cls):
        from .node import Node
        if not (isinstance(cls, type) and issubclass(cls, Node)):
            raise TypeError(f"커스텀 노드는 Node 서브클래스여야 함: {name}")
        if name in CUSTOM_NODES:
            raise ValueError(f"커스텀 노드 중복 등록: {name}")
        CUSTOM_NODES[name] = cls
        return cls
    return deco


def allowed() -> bool:
    return os.environ.get("AICOMBAT_ALLOW_CUSTOM", "0") == "1"


def load_custom_module(rel_path: str, base_dir: str) -> None:
    """에이전트 YAML 의 custom_module: 항목 로드.

    · 봉인 스위치: AICOMBAT_ALLOW_CUSTOM≠1 이면 명시 거부 (조용히 무시하지
      않는다 — DSL 화이트리스트 철학과 동일). 기본은 거부(fail-closed).
    · 경로 규율: include 와 동일 — 상대경로만, `..` 거부
    """
    if not allowed():
        raise ValueError(
            "custom_module 이 봉인된 환경입니다 (AICOMBAT_ALLOW_CUSTOM≠1). "
            "이 트리는 커스텀 허용 환경(리서치)에서만 실행할 수 있습니다.")
    if os.path.isabs(rel_path) or ".." in rel_path.replace("\\", "/").split("/"):
        raise ValueError(f"custom_module 은 상대경로(.. 없이)만 허용: {rel_path}")
    path = os.path.join(base_dir, rel_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"custom_module 미발견: {path}")
    ap = os.path.abspath(path)
    if ap in _LOADED:
        return                                 # 동일 파일 재로드 — 등록 유지
    _LOADED.add(ap)
    mod_name = "aircombat_custom_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)            # import 시점에 데코레이터가 등록


def reset() -> None:
    """등록 초기화 (테스트·재로드용)."""
    CUSTOM_CONDITIONS.clear()
    CUSTOM_NODES.clear()
    _LOADED.clear()
