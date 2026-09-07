"""공정2·3 번역기 — 문장 JSON(함수-구간 박스) → champion128.yaml (3층 BT).

②층: 문장 하나가 `custom: sentence` 가지 하나(구간 숫자가 트리에 그대로 보임).
③층(공정3): 기저를 판독 가지 6개로 분해 — 게이트 거부/empty-dive/하드덱/다이브-
대응/헤드온-덱-억제/증류트리 스냅. 표시 상수는 ledger_nodes 의 정본 테이블에서
가져오며 로드 시점에 일치가 단언된다(드리프트 검출). 구간·상수 값은 repr 전체
자릿수로 내보내 double 왕복이 보존된다.

usage: python -m research.gen_champion_yaml <rules.json> <out.yaml>
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys


def _canon():
    """agents/champion128/ledger_nodes.py 의 정본 상수 테이블 로드(단일 원천)."""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "agents", "champion128", "ledger_nodes.py")
    spec = importlib.util.spec_from_file_location("_c128_nodes", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._canon_consts()


def _block(d: dict, indent: str = "      ") -> list[str]:
    return [f"{indent}{k}: {v!r}" for k, v in d.items()]


# ①층 상황 함수 사전 — YAML 주석과 축별 단위 표기의 단일 원천
AXES = {
    "rng":     "두 기체 거리 [ft]",
    "ata":     "내 기수-조준각 [deg] (0=정조준)",
    "eata":    "적 기수-조준각 [deg] (0=적이 나를 정조준)",
    "race":    "조준 경쟁 = eata − ata [deg] (+ = 경쟁 우위)",
    "kcas":    "내 속도 [kt]",
    "alt":     "내 고도 [ft]",
    "agap":    "고도차 = 내 − 적 [ft]",
    "hp_lead": "장부 점수차 = 내HP − 적HP(부기 추정) [hp]",
    "clos":    "접근율 [kt] (+ = 가까워지는 중)",
    "pursue":  "적 추격 점유율(무장 후 12s 창) [0~1]",
    "hotrun":  "적 hot(eata<45°) 연속 지속 [s]",
    "eclimb":  "적 상승률 [fps] (− = 강하)",
    "dalt":    "내 고도변화율 [fps]",
    "es_rel":  "비에너지 차 = (h+v²/2g) 내 − 적 [ft]",
    "t":       "경과 시간 [s]",
    "fdmg":    "내가 가한 데미지(장부) [hp]",
}


def gen(rules_path: str, out_path: str) -> None:
    rules = json.load(open(rules_path))
    K = _canon()
    L = ["# 128승 조종사 — 함수-구간 3층 BT (생성: research/gen_champion_yaml.py)",
         f"# 문장 출처: {rules_path} ({len(rules)}문장). 손편집 금지 — 재생성할 것.",
         "# 표시 상수는 로드 시점에 정본 값과 일치가 단언된다(드리프트 검출).",
         "agent_name: Champion128",
         "dwell_s: 0                       # 문장·기저가 자체 래치 보유",
         "custom_module: champion128/ledger_nodes.py",
         "selector:",
         "  # ①층 — 상황 함수 계산(20Hz 부기·10Hz 결정) + 기저 선계산",
         "  #   함수 사전(ledger_book 이 매 결정틱 계산; ②층 문장의 좌표계):"] + [
         f"  #     {k:<8} {desc}" for k, desc in AXES.items()] + [
         "  #   기저는 트리가 아니라 명시 함수 2개(f_gun/f_lead — 루프32 재유도)",
         "  - custom: {name: ledger_book, refuse: auto, base_fn: gun20}",
         "  # ②층 — 함수-구간 문장 (위가 선순위; 발화 1회·dur 유지)",
         "  #   구간은 발화-구속 축만 남긴 것(축 다이어트 — 전 발화 스케줄 불변 증명,",
         "  #   research/slim_rules.py). 문장 = 함수값 구간의 교집합 국면 → 국소 풀이."]
    for i, r in enumerate(rules):
        cov = ",".join(c.split("/")[0].rsplit("_", 1)[0] + "/" + c.split("/")[1]
                       for c in r.get("covers", [])[:3])
        tw = r.get("t_width", {})
        tw_note = (f"  타이밍여유 {min(tw.values()):.0f}~{max(tw.values()):.0f}s"
                   if tw else "")
        L.append(f"  - custom:                    # 문장#{i} — 피복: {cov}"
                 + ("…" if len(r.get("covers", [])) > 3 else "") + tw_note)
        L.append(f"      name: sentence")
        L.append(f"      label: s{i}_{r['act']}")
        L.append(f"      act: {r['act']}")
        L.append(f"      dur: {r['dur']!r}")
        L.append(f"      box:")
        w = max(len(f"{k}: [{lo!r}, {hi!r}]") for k, (lo, hi) in r["box"].items())
        for k, (lo, hi) in r["box"].items():
            body = f"{k}: [{lo!r}, {hi!r}]"
            L.append(f"        {body:<{w}}   # {AXES.get(k, '')}")
    g = {k: K[k] for k in ("gate_hot", "gate_rng", "gate_edge", "lead_near",
                           "lead_hi", "lead_floor", "hurt_max", "cooldown_s",
                           "abort_off", "clear_hot", "clear_rng", "pursue_win_s",
                           "pursue_max", "pursue_min_s", "dom", "threat_hold_s")}
    dv = {k: K[k] for k in ("theta", "decay", "dive_fps", "dive_hold", "aa_extend")}
    L += ["  # ③층 — 구간 밖 일반해(기저 판독 가지; 위가 선순위 = 원본 dispatch 순서)",
          "  - custom:                    # 점수-장부 게이트 거부(효능 폐루프)",
          "      name: base_branch",
          "      when: refuse",
          "      label: gate_refuse"] + _block(g) + [
          "  - custom: {name: base_branch, when: empty_dive, label: empty_dive_response}",
          "  - custom:",
          "      name: base_branch",
          "      when: hard_deck",
          "      label: hard_deck_climb"] + _block({"hard_deck": K["hard_deck"]}) + [
          "  - custom:                    # 적 다이브-커밋 감지(c≥θ) → off 대응(수치 argmax)",
          "      name: base_branch",
          "      when: dive_response",
          "      label: dive_commit_response"] + _block(dv) + [
          "  - custom:",
          "      name: base_branch",
          "      when: deck_suppress",
          "      label: headon_deck_suppress"] + _block(
              {"suppress_alt": K["suppress_alt"], "suppress_rng": K["suppress_rng"]}) + [
          "  - custom:                    # 기저함수 f_gun — 조준 원뿔 안이면 건 추적",
          "      name: base_branch",
          "      when: f_gun",
          "      label: f_gun",
          "      gun_ata: 20.0            # ata < 이 값 → GUN_TRACK",
          "  - custom: {name: base_branch, when: f_lead, label: f_lead}   # 그 외 → LEAD_TURN",
          "  - custom: {name: base_pilot}   # 안전망(비활성 경로 preserve/deck_guard)",
          ""]
    open(out_path, "w", encoding="utf-8", newline="\n").write("\n".join(L))
    print(f"{len(rules)}문장 → {out_path}")


if __name__ == "__main__":
    gen(sys.argv[1], sys.argv[2])
