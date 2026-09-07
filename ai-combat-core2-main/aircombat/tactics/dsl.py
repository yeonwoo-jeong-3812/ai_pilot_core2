"""전술 트리 DSL(Domain Specific Language) — dict/YAML → BT 노드.

노드 형식(단일 키 dict):
  {"selector": [child, ...]}     우선순위 폴백
  {"sequence": [child, ...]}     모두 성공해야 성공
  {"condition": "name"}          conditions.CONDITIONS 참조 (기본 임계값)
  {"condition": {"name": "overshoot_risk", "closure_fps": 120}}   임계값 오버라이드
  {"action": {"pursuit": "lag", "g_burst": 0.8, "name": "break",
              "aim_above_ft": 750, "lead_time_s": 1.5, "lag_dist_ft": 2000}}
  {"inverter": child}
  {"commit": {"name": "high_yoyo", "duration_s": 4.0, "cooldown_s": 3.0, "child": {...}}}
  {"cooldown": {"wait_s": 5.0, "child": {...}}}

조건 임계값 검증은 함수 시그니처가 단일 진실 — inspect.signature 로 키워드
파라미터를 대조하고 functools.partial 로 바인딩한다(별도 스펙표 없음).
액션 키는 화이트리스트 — 미지 키는 ValueError(오타를 조용히 무시하지 않음).
액션 숫자 파라미터는 _ACTION_BOUNDS 범위 밖이면 거부한다(클램프하지 않음).

기본 트리(DEFAULT_SPEC)는 config/tactics.yaml 없이도 동작한다.
"""
from __future__ import annotations

import functools
import inspect
import os

from .node import Node, Sequence, Selector, Condition, Action, Inverter, Commit, Cooldown
from .conditions import CONDITIONS

# 액션 숫자 파라미터의 허용 범위 — 검증과 자동 문서(agent.schema.json)의 단일 진실.
# doctrine.DOCTRINE_BOUNDS 와 같은 철학: 범위 밖은 조용히 클램프하지 않고 제출 거부.
_ACTION_BOUNDS = {
    "aim_above_ft":   (-5000.0, 5000.0),
    "lead_time_s":    (0.0, 3.0),
    "lag_dist_ft":    (0.0, 8000.0),
    "cz_range_ft":    (500.0, 6000.0),
    "g_burst":        (0.0, 1.0),        # 지속↔순간 봉투 보간 = 지령 G 천장 (구 max_g 대체)
    "g_full_ata_deg": (20.0, 90.0),      # 명목 G 에 포화하는 ATA
    "track_rng_ft":   (1000.0, 3000.0),  # 건 추적 하한 G 창 — 상한 = WEZ 사거리
    "track_ata_deg":  (10.0, 30.0),      # 동 ATA 게이트 — 상한 = WEZ 원뿔
}
_ACTION_KEYS = set(_ACTION_BOUNDS) | {"pursuit", "name", "mode"}
_PURSUITS = {"lead", "pure", "lag"}
_MODES = {"stable", "control_zone"}   # L2 가이드 모드 (None=기본 조절)
_COMMIT_KEYS = {"name", "duration_s", "cooldown_s", "child"}
_COOLDOWN_KEYS = {"name", "wait_s", "child"}


# 우선순위: 방어 > 오버슈트회피 > 연장추격 > 건조준 > 기수당김 > 기본 pure
DEFAULT_SPEC = {
    "selector": [
        {"sequence": [{"condition": "foe_threat"},
                      {"action": {"pursuit": "lag", "g_burst": 0.8, "name": "break_defense"}}]},
        {"sequence": [{"condition": "overshoot_risk"},
                      {"action": {"pursuit": "lag", "name": "lag_reposition"}}]},
        {"sequence": [{"condition": "foe_extending"},
                      {"action": {"pursuit": "lead", "g_burst": 0.8, "name": "lead_rundown"}}]},
        {"sequence": [{"condition": "in_gun_envelope"},
                      {"action": {"pursuit": "pure", "name": "gun_track"}}]},
        {"sequence": [{"condition": "nose_far"},
                      {"action": {"pursuit": "lead", "name": "lead_pull"}}]},
        {"action": {"pursuit": "pure", "name": "pure_default"}},
    ]
}


def _num(key: str, v) -> float:
    """숫자 강제 — bool 거부. YAML 1.1 은 따옴표 없는 no/off 를 False 로 읽어
    float(False)=0.0 이 무증상 통과한다(예: floor_ft: no → 하드덱 회피 브랜치
    영구 비활성). doctrine.from_overrides 의 bool 검사와 동일 철학."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key}={v!r} — 숫자여야 함 "
                         "(따옴표 없는 yes/no/on/off 는 YAML 이 boolean 으로 읽음)")
    return float(v)


def _build_condition(val) -> Condition:
    """문자열(기본 임계값) 또는 dict(오버라이드) → Condition.

    dict 파라미터는 조건 함수의 키워드 인자와 inspect 로 대조 —
    시그니처가 파라미터 스펙의 단일 진실.
    """
    if isinstance(val, str):
        name, params = val, {}
    elif isinstance(val, dict):
        if "name" not in val:
            raise ValueError(f"condition dict 에 name 필요: {val}")
        name = val["name"]
        params = {k: v for k, v in val.items() if k != "name"}
    else:
        raise ValueError(f"condition 은 문자열 또는 dict: {val!r}")
    if name not in CONDITIONS:
        from .custom import CUSTOM_CONDITIONS
        if name not in CUSTOM_CONDITIONS:
            raise KeyError(f"알 수 없는 조건: {name} (있는 것: {list(CONDITIONS)}"
                           f" + 커스텀 {list(CUSTOM_CONDITIONS)})")
        fn = CUSTOM_CONDITIONS[name]
    else:
        fn = CONDITIONS[name]
    if params:
        allowed = {p.name for p in inspect.signature(fn).parameters.values()
                   if p.kind is inspect.Parameter.KEYWORD_ONLY}
        unknown = set(params) - allowed
        if unknown:
            raise ValueError(f"조건 {name} 의 미지 파라미터 {sorted(unknown)} "
                             f"(허용: {sorted(allowed)})")
        fn = functools.partial(fn, **{k: _num(k, v) for k, v in params.items()})
        # trace 에 오버라이드가 보이게 이름에 병기(감사)
        name = f"{name}({','.join(f'{k}={v}' for k, v in params.items())})"
    return Condition(name, fn)


def _build_action(val: dict) -> Action:
    if "max_g" in val:
        # 2026-08-24 폐지. 미지 키 일반 메시지로 두면 원인을 못 찾으므로 전용 안내.
        raise ValueError(
            "max_g 는 폐지되었습니다 — g_burst (0.0~1.0) 로 대체하십시오. "
            "권장 전환은 true→0.8 / false→0.0 이지만 조절 법칙이 바뀌어 "
            "거동은 동일하지 않습니다 (RULEBOOK §10.1).")
    unknown = set(val) - _ACTION_KEYS
    if unknown:
        raise ValueError(f"action 의 미지 키 {sorted(unknown)} (허용: {sorted(_ACTION_KEYS)})")
    if "pursuit" not in val:
        raise ValueError(f"action 에 pursuit 필요: {val}")
    if val["pursuit"] not in _PURSUITS:
        raise ValueError(f"알 수 없는 pursuit: {val['pursuit']} (허용: {sorted(_PURSUITS)})")
    mode = val.get("mode")
    if mode is not None and mode not in _MODES:
        raise ValueError(f"알 수 없는 mode: {mode} (허용: {sorted(_MODES)})")

    # 범위 검증 — doctrine.from_overrides 와 동일하게 에러를 모아 한 번에 던진다
    # (한 필드씩 고쳐 재제출하는 왕복을 없앤다).
    errors = []
    nums = {}
    for key, (lo, hi) in _ACTION_BOUNDS.items():
        if val.get(key) is None:
            continue
        try:
            v = _num(key, val[key])
        except ValueError as e:
            errors.append(str(e))
            continue
        if not (lo <= v <= hi):
            errors.append(f"{key}={val[key]!r} — 허용 범위 [{lo}, {hi}]")
        else:
            nums[key] = v
    if errors:
        raise ValueError("action 검증 실패: " + "; ".join(errors))

    return Action(val["pursuit"], val.get("name"), mode=mode, **nums)


def build_node(spec: dict) -> Node:
    if not isinstance(spec, dict) or len(spec) != 1:
        raise ValueError(f"노드 dict 는 단일 키여야 함: {spec!r}")
    key, val = next(iter(spec.items()))
    if key == "selector":
        return Selector([build_node(c) for c in val])
    if key == "sequence":
        return Sequence([build_node(c) for c in val])
    if key == "condition":
        return _build_condition(val)
    if key == "action":
        return _build_action(val)
    if key == "inverter":
        return Inverter(build_node(val))
    if key == "commit":
        unknown = set(val) - _COMMIT_KEYS
        if unknown:
            raise ValueError(f"commit 의 미지 키 {sorted(unknown)} (허용: {sorted(_COMMIT_KEYS)})")
        if "child" not in val:
            raise ValueError(f"commit 에 child 필요: {val}")
        return Commit(build_node(val["child"]),
                      name=val.get("name", "commit"),
                      duration_s=_num("duration_s", val.get("duration_s", 4.0)),
                      cooldown_s=_num("cooldown_s", val.get("cooldown_s", 0.0)))
    if key == "cooldown":
        unknown = set(val) - _COOLDOWN_KEYS
        if unknown:
            raise ValueError(f"cooldown 의 미지 키 {sorted(unknown)} (허용: {sorted(_COOLDOWN_KEYS)})")
        if "child" not in val:
            raise ValueError(f"cooldown 에 child 필요: {val}")
        return Cooldown(build_node(val["child"]),
                        wait_s=_num("wait_s", val.get("wait_s", 5.0)),
                        name=val.get("name", "cooldown"))
    if key == "custom":
        # 커스텀 상태-보유 노드 (custom.py 등록물; Commit/Cooldown 선례의 개방형).
        from .custom import CUSTOM_NODES
        if not isinstance(val, dict) or "name" not in val:
            raise ValueError(f"custom 노드는 {{name: ..., 파라미터}} dict: {val!r}")
        cname = val["name"]
        if cname not in CUSTOM_NODES:
            raise KeyError(f"미등록 커스텀 노드: {cname} "
                           f"(등록됨: {list(CUSTOM_NODES)}; custom_module 로드 확인)")
        params = {k: v for k, v in val.items() if k != "name"}
        return CUSTOM_NODES[cname](**params)
    raise ValueError(f"알 수 없는 노드 타입: {key}")


def build_default() -> Node:
    return build_node(DEFAULT_SPEC)


def load_agent_yaml(path: str) -> tuple[dict | None, Node, str | None, float | None]:
    """에이전트 YAML → (doctrine 오버라이드 | None, 트리 루트, agent_name | None,
    dwell_s | None).

    최상위 `doctrine:`(매핑)·`agent_name:`(문자열)·`dwell_s:`(수) 는 트리에서 분리한다 —
    나머지 단일 키가 전술 트리 루트. doctrine 값 검증·개방 여부 판정은
    guidance.doctrine.Doctrine.from_overrides 소관(L1/L2 계층 분리, 순환 import 회피).
    agent_name 은 리플레이(ACMI CallSign)에 찍히는 참가자 자기식별용 표시 이름.
    dwell_s 는 명령 히스테리시스 오버라이드(미지정이면 TacticPolicy 기본 0.3s).
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"에이전트 파일 없음: {path}")
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not spec:
        # 빈 파일을 기본 트리로 대체하면 참가자는 "검증 통과" 를 받고 기본 기동으로
        # 배터리를 소진한다 (2026-07-29 실사고). 제출물 결손은 반드시 실패로 알린다.
        raise ValueError("빈 에이전트 파일입니다 (전술 트리 없음)")
    doctrine = agent_name = None
    dwell_s = None
    if isinstance(spec, dict) and ("doctrine" in spec or "agent_name" in spec
                                   or "custom_module" in spec or "dwell_s" in spec):
        spec = dict(spec)
        doctrine = spec.pop("doctrine", None)
        agent_name = spec.pop("agent_name", None)
        dwell_s = spec.pop("dwell_s", None)
        if dwell_s is not None:
            dwell_s = float(dwell_s)
            if dwell_s < 0:
                raise ValueError("dwell_s 는 0 이상이어야 합니다")
        custom_module = spec.pop("custom_module", None)
        if custom_module is not None:
            from .custom import load_custom_module
            if not isinstance(custom_module, str):
                raise ValueError("custom_module 은 상대경로 문자열이어야 합니다")
            load_custom_module(custom_module,
                               os.path.dirname(os.path.abspath(path)))
        if doctrine is not None and not isinstance(doctrine, dict):
            raise ValueError("doctrine 블록은 {필드: 값} 매핑이어야 합니다")
        if agent_name is not None and not isinstance(agent_name, str):
            raise ValueError("agent_name 은 문자열이어야 합니다")
        if not spec:
            raise ValueError("전술 트리가 없습니다 (doctrine/agent_name 만 있음)")
    root = build_node(spec)
    if dwell_s is not None:
        # 명령 히스테리시스 오버라이드 (기본 0.3s) — 자체 래치/히스테리시스를 내장한
        # 트리(commit·상태 보유 커스텀 노드)는 0 으로 꺼서 이중 지연을 피한다.
        # 반환 시그니처 보존을 위해 루트에 실어 TacticPolicy.__init__ 이 읽는다.
        root._dwell_s = dwell_s
    return doctrine, root, agent_name, dwell_s


def build_from_yaml(path: str) -> Node:
    """config/tactics.yaml → 트리. 파일 없거나 yaml 미설치면 기본 트리."""
    return load_agent_yaml(path)[1]
