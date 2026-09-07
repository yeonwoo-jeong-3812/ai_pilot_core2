"""프레임워크 단일 진입점 — 교전 데이터 → 전승 함수형 F → BT(YAML) 전 과정.

M1~M3 자동화(불변식·CEGIS 데몬·지표 스캐너)와 루프31·32의 함수형 공정(관계 좌표
race·함수 기저 f_gun/f_lead·문장 다이어트·YAML 번역)을 한 명령으로 잇는다.
각 단계는 산출물이 이미 있으면 건너뛴다(멱등 — 중단 지점부터 재개).

usage:
  python -m research.framework run   --agent agents/champion128.yaml --roster roster/all_128.txt
      [--tag f32] [--replay] [--lofo] [--dry] [--fresh]
      전 파이프라인: 불변식 → 플레인 기저 → 폐루프(데몬) → 다이어트 → YAML 번역
                     → 128 게이트+패리티 → (--replay 녹화 세대) → (--lofo 일반화)
  python -m research.framework gate  --agent <yaml> --roster <txt> [--tag f32]
      게이트만: YAML 128판 + 연구 런타임 패리티 + 통계
  python -m research.framework stats --log <결과.log>
      승/무/패 · 격추/판정 · HPΔ 분포 · 격추 시각
  python -m research.framework diff  --a <결과A.log> --b <결과B.log>
      두 결과 로그 전판 대조(결과·HPΔ·종료) — 회귀 검사
  python -m research.framework schedule --rules <문장.json> --dump <배포덤프.csv>
      전-발화 스케줄(2차 발화 포함) · 문장별 발화 판 · 사문 후보

캠페인 상수(정본): F-좌표 = 관계형 11축 + race, 기저 = gun20(f_gun/f_lead).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics as st
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
LBL = os.path.join(PM, "data", "blueteam")
REP = os.path.join(PM, "campaigns")
LOG = os.path.join(REP, "logs")

# ── 캠페인 정본 상수 (루프31·32 판정 결과) ─────────────────────────────────────
# 루프38: 롤 축 2개 추가(roff·eroff) — LOS 기준 당김면 방향. 기존 어휘엔 각도·거리·
# 고도차만 있어 방어 기동의 브레이크 방향을 표현할 수 없었다.
FEATS = ("rng,ata,eata,agap,hp_lead,clos,pursue,hotrun,eclimb,dalt,es_rel,race,"
         "roff,eroff")
BASE_FN = "gun20"
RE_RES = re.compile(r"\s*(\S+/(?:blue|red))\s+(승|무|패)\s+([+-][\d.]+)\s+.*?(\S+)@(\d+)s")


def _run(args_, env_extra=None, log=None) -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")   # 결정론(심층 방어)
    env.update({k: str(v) for k, v in (env_extra or {}).items()})
    out = open(log, "w", encoding="utf-8") if log else None
    r = subprocess.run([sys.executable] + args_, cwd=ROOT, env=env,
                       stdout=out or None, stderr=subprocess.STDOUT if out else None)
    if out:
        out.close()
    return r.returncode


def load_results(path: str) -> dict:
    d = {}
    for ln in open(path, encoding="utf-8"):
        m = RE_RES.match(ln)
        if m:
            d[m.group(1)] = (m.group(2), float(m.group(3)), m.group(4), int(m.group(5)))
    return d


# ── 서브커맨드: stats / diff / schedule ────────────────────────────────────────
def cmd_stats(log: str) -> int:
    r = load_results(log)
    if not r:
        print(f"결과 없음: {log}")
        return 1
    hp = [v[1] for v in r.values()]
    w = sum(1 for v in r.values() if v[0] == "승")
    d = sum(1 for v in r.values() if v[0] == "무")
    kill = [v for v in r.values() if v[2] == "health_zero"]
    print(f"판수 {len(r)}  {w}승 {d}무 {len(r)-w-d}패")
    print(f"격추승 {len(kill)} / 판정 {len(r)-len(kill)}")
    print(f"HPΔ 평균 {st.mean(hp):+.1f}  중앙 {st.median(hp):+.1f}  "
          f"최소 {min(hp):+.1f}  최대 {max(hp):+.1f}")
    if kill:
        t = [v[3] for v in kill]
        print(f"격추 시각 평균 {st.mean(t):.0f}s  중앙 {st.median(t):.0f}s")
    losses = [c for c, v in r.items() if v[0] != "승"]
    if losses:
        print("비승리:", losses)
    return 0


def cmd_diff(a: str, b: str) -> int:
    ra, rb = load_results(a), load_results(b)
    bad = [(c, ra.get(c), rb.get(c)) for c in sorted(set(ra) | set(rb))
           if ra.get(c) != rb.get(c)]
    print(f"{os.path.basename(a)} {len(ra)}판  vs  {os.path.basename(b)} {len(rb)}판"
          f"  — 불일치 {len(bad)}건")
    for c, va, vb in bad[:20]:
        print(f"  {c}: {va} → {vb}")
    return 0 if not bad else 1


def cmd_schedule(rules_p: str, dump_p: str) -> int:
    from research.slim_rules import load_dump, schedule
    rules = json.load(open(rules_p))
    for r in rules:
        r["_box"] = {k: tuple(v) for k, v in r["box"].items()}
    ev = schedule(rules, load_dump(dump_p))
    print(f"발화 {len(ev)}건 / 문장 {len(rules)}")
    for i in range(len(rules)):
        cases = [(tag, t) for tag, t, j in ev if j == i]
        mark = "" if cases else "  ← 사문 후보(제거는 128 실측으로 판정)"
        print(f"  #{i:<2} {rules[i]['act']:<9} {len(cases)}건 {cases[:3]}{mark}")
    return 0


def cmd_timing(wit_dir: str) -> int:
    """발화시각-성능 분석: 케이스별 승리-시간창 최장 폭 — 강건성/일반화 예측 지표.
    (좁은 창 = 타이밍-특이 해 → 분포 밖 취약; 루프35 실측: E1·E2 좁음 ↔ 이월 최약)"""
    import glob
    from collections import defaultdict
    RE_W = re.compile(r"\s*t0=\s*([\d.]+)\s+(\w+)\s+d=\s*([\d.]+) → (★승|★무|  패)")
    rows = []
    for pth in sorted(glob.glob(os.path.join(ROOT, wit_dir, "bs_*.log"))):
        case = os.path.basename(pth)[3:-4]
        if "@" in case:
            continue
        by_act = defaultdict(list)
        for ln in open(pth, encoding="utf-8"):
            m = RE_W.match(ln)
            if m:
                by_act[m.group(2)].append((float(m.group(1)), m.group(4) == "★승"))
        best = 0.0
        for act, lst in by_act.items():
            wins = sorted({t for t, w in lst if w})
            if not wins:
                continue
            ts = sorted({t for t, _ in lst})
            step = min((b - a for a, b in zip(ts, ts[1:])), default=4.0) or 4.0
            run0 = prev = wins[0]
            for t_ in wins[1:] + [None]:
                if t_ is None or t_ - prev > step + 0.1:
                    best = max(best, prev - run0 + step)
                    if t_ is not None:
                        run0 = t_
                if t_ is not None:
                    prev = t_
        rows.append((best, case))
    rows.sort()
    if not rows:
        print("증인 없음:", wit_dir)
        return 1
    ws = [w for w, _ in rows]
    print(f"케이스 {len(rows)} — 승리-시간창 폭: 중앙 {st.median(ws):.0f}s "
          f"최소 {min(ws):.0f}s 최대 {max(ws):.0f}s")
    for w, c in rows:
        mark = " ← 면도날(분포밖 취약 후보)" if w <= 12 else ""
        print(f"  {c:<30} {w:4.0f}s{mark}")
    return 0


def cmd_audit(tag: str, roster: str, val: str) -> int:
    """산출물 사슬 감사 — 단계 간 데이터가 누수·정체 없이 이어지는지 전수 점검.

    각 항목은 "앞 단계의 출력이 뒷 단계의 입력으로 온전히 들어갔는가"를 본다.
    루프36 실측 결함(증인 재사용 구 어휘, LOFO 128 고정 단언, 지문 미갱신,
    문자열 정렬 라운드)이 이 감사가 잡아야 할 유형이다."""
    import glob as _glob
    ok = True

    def chk(cond, name, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'OK ' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print(f"=== 산출물 사슬 감사: 태그 {tag} ===")
    work = os.path.join(REP, f"daemon_{tag}")
    rules_final = os.path.join(LBL, f"induced_rules_{tag}.json")
    rules_slim = os.path.join(LBL, f"induced_rules_{tag}_slim.json")
    base_log = os.path.join(LOG, f"obsdump_plain_{BASE_FN}_{tag}.log")
    base_dump = os.path.join(LBL, f"obs_dump_plain_{BASE_FN}_{tag}.csv")

    slots = [x.strip() for x in open(os.path.join(ROOT, roster), encoding="utf-8")
             .read().replace(chr(13), "").replace(chr(10), ",").split(",") if x.strip()]

    # 1) 로스터 -> 기저 채점: 판 수 일치
    if os.path.exists(base_log):
        base = load_results(base_log)
        chk(len(base) == len(slots), "로스터→기저 판 수",
            f"로스터 {len(slots)} vs 기저 {len(base)}")
    else:
        chk(False, "기저 로그 존재", base_log)

    # 2) 기저 덤프 헤더 = 런타임 좌표 계약
    if os.path.exists(base_dump):
        hdr = tuple(open(base_dump, encoding="utf-8").readline().strip().split(","))
        from research.proto_ledger_gate import LedgerPilot as _LP
        want = ("tag", "t") + tuple(_LP._DUMP_KEYS)
        chk(hdr == want, "덤프 헤더 = 런타임 _DUMP_KEYS", f"{len(hdr)}열")

    # 3) 증인 수확 조건 신선도 (재사용이 구 어휘를 물지 않았는가)
    wits = _glob.glob(os.path.join(work, "wit_r*", "bs_*.log"))
    if wits:
        from research.cegis_daemon import witness_matches, harvest_sig
        stale = [w for w in wits if not witness_matches(w)]
        chk(not stale, "증인 수확 조건 일치(재사용 신선도)",
            f"{len(wits)-len(stale)}/{len(wits)} 일치 · 서명 {harvest_sig()}")

    # 4) 데몬 최종 라운드 -> 문장 정본
    if os.path.isdir(work) and os.path.exists(rules_final):
        rounds = sorted((f for f in os.listdir(work)
                         if re.fullmatch(r"rules_r\d+\.json", f)),
                        key=lambda f: int(re.search(r"\d+", f).group()))
        if rounds:
            last = json.load(open(os.path.join(work, rounds[-1])))
            fin = json.load(open(rules_final))
            chk(last == fin, "데몬 최종 라운드 → 문장 정본",
                f"{rounds[-1]} ({len(last)}문장)")

    # 5) 다이어트: 문장 수 보존 · 축 부분집합 · 메타데이터 전달
    if os.path.exists(rules_final) and os.path.exists(rules_slim):
        a = json.load(open(rules_final))
        b = json.load(open(rules_slim))
        chk(len(a) == len(b), "다이어트 문장 수 보존", f"{len(a)}→{len(b)}")
        chk(all(set(y["box"]) <= set(x["box"]) for x, y in zip(a, b)),
            "다이어트 축 부분집합",
            f"{sum(len(x['box']) for x in a)}→{sum(len(y['box']) for y in b)}축")
        chk(sum(1 for y in b if y.get("t_width")) ==
            sum(1 for x in a if x.get("t_width")), "시간창 메타데이터 전달(t_width)")

    # 6) 배포본 지문 존재 · 드리프트 0
    if os.path.exists(rules_slim):
        fp = rules_slim.replace(".json", ".fingerprint.json")
        chk(os.path.exists(fp), "배포본 지문 존재(slim 기준)")
        dumps = sorted((f for f in os.listdir(LBL)
                        if re.fullmatch(rf"obs_dump_daemon_{tag}_r\d+\.csv", f)),
                       key=lambda f: int(re.search(r"_r(\d+)\.csv$", f).group(1)))
        if os.path.exists(fp) and dumps:
            import research.pipeline_invariants as _I
            drift = _I.fingerprint_drift(rules_slim, os.path.join(LBL, dumps[-1]))
            chk(not drift, "지문 드리프트 없음", f"이탈 {len(drift)}건")

    # 7) YAML <-> 연구 런타임 패리티
    gl = os.path.join(LOG, f"framework_{tag}_gate.log")
    rl = os.path.join(LOG, f"framework_{tag}_research.log")
    if os.path.exists(gl) and os.path.exists(rl):
        g, r = load_results(gl), load_results(rl)
        chk(g == r, "YAML ↔ 연구 런타임 패리티", f"{len(g)}판")

    # 8) 훈련/검증 격리 · 검증 상대 증인 미유입
    if val and os.path.exists(os.path.join(ROOT, val)):
        vslots = {x.strip() for x in open(os.path.join(ROOT, val), encoding="utf-8")
                  .read().replace(chr(13), "").replace(chr(10), ",").split(",") if x.strip()}
        chk(not (vslots & set(slots)), "훈련/검증 격리(교집합 0)",
            f"train {len(slots)} · val {len(vslots)}")
        vstems = {v.rsplit("/", 1)[0] for v in vslots}
        wit_stems = set()
        for w in wits:
            b = os.path.basename(w)[3:-4]
            wit_stems.add(b.rsplit("_", 1)[0])
        leak = {v for v in vstems if v.replace("/", "_") in wit_stems or v in wit_stems}
        chk(not leak, "검증 상대 증인 미유입(누수 차단)",
            f"유출 {sorted(leak)[:3]}" if leak else "")

    print(f"=== 감사 {'통과' if ok else '실패'} ===")
    return 0 if ok else 1


def cmd_split(roster: str, holdout: float, seed: int) -> int:
    """상대 단위·가족-층화·시드 추첨으로 train/val 로스터 분리.

    ML 관행의 무작위 추첨이되 시드를 선언·기록해 재현 가능(결정론 원칙과 양립).
    같은 상대의 blue/red 슬롯은 같은 버킷(기전 누출 방지). 가족마다 비율 추첨
    (층화 — 순수 랜덤은 소수 가족이 train 에서 통째로 빠져 LOFO 와 동일해짐)."""
    import random
    slots = [s.strip() for s in open(os.path.join(ROOT, roster), encoding="utf-8")
             .read().replace("\r", "").replace("\n", ",").split(",") if s.strip()]
    stems = sorted({s.rsplit("/", 1)[0] for s in slots})
    fam = lambda st: st.rsplit("_", 1)[0] if not st.startswith("anchor") else "anchor"
    rng = random.Random(seed)                      # 선언된 시드 — 재현 가능
    val_stems = set()
    from collections import defaultdict
    by_fam = defaultdict(list)
    for st_ in stems:
        by_fam[fam(st_)].append(st_)
    for f, members in sorted(by_fam.items()):
        k = max(1, round(len(members) * holdout))
        val_stems |= set(rng.sample(sorted(members), k))
    tr = [s for s in slots if s.rsplit("/", 1)[0] not in val_stems]
    va = [s for s in slots if s.rsplit("/", 1)[0] in val_stems]
    base = os.path.join(ROOT, "roster")
    tp = os.path.join(base, f"train_s{seed}.txt")
    vp = os.path.join(base, f"val_s{seed}.txt")
    open(tp, "w", encoding="utf-8", newline="\n").write("\n".join(tr) + "\n")
    open(vp, "w", encoding="utf-8", newline="\n").write("\n".join(va) + "\n")
    print(f"시드 {seed} · 홀드아웃 {holdout:.0%} — train {len(tr)}판({len(stems)-len(val_stems)}상대) "
          f"/ val {len(va)}판({len(val_stems)}상대)")
    print(f"  {os.path.relpath(tp, ROOT)}  {os.path.relpath(vp, ROOT)}")
    print("  val 상대:", sorted(val_stems))
    return 0


# ── run: 전 파이프라인 ────────────────────────────────────────────────────────
def stage(dry: bool, name: str, done: bool, why: str):
    mark = "건너뜀(완료)" if done else ("실행 예정" if dry else "실행")
    print(f"[{name}] {mark} — {why}", flush=True)
    return not done and not dry


def cmd_run(agent: str, roster: str, tag: str, replay: bool, lofo: bool,
            dry: bool, fresh: bool, scan: bool = False, minproof: bool = False,
            seed_rules: str = "", val: str = "", expand: bool = False) -> int:
    all_slots = open(os.path.join(ROOT, roster), encoding="utf-8").read().strip()
    all_env = all_slots.replace("\r", "").replace("\n", ",")
    rules_final = os.path.join(LBL, f"induced_rules_{tag}.json")
    rules_slim = os.path.join(LBL, f"induced_rules_{tag}_slim.json")
    base_log = os.path.join(LOG, f"obsdump_plain_{BASE_FN}_{tag}.log")
    base_dump = os.path.join(LBL, f"obs_dump_plain_{BASE_FN}_{tag}.csv")
    gate_log = os.path.join(LOG, f"framework_{tag}_gate.log")

    # 1) M1 불변식
    if stage(dry, "M1 불변식", False, "파이프라인 함정 기계검사(항상 실행)"):
        if _run(["-m", "pytest", "-q", "research/test_pipeline_invariants.py"]) != 0:
            print("불변식 실패 — 중단")
            return 1

    # 2) 플레인 기저 (게이트만 + 함수기저) — 결과와 덤프
    done = os.path.exists(base_log) and os.path.exists(base_dump) and not fresh
    if stage(dry, "플레인 기저", done, f"{BASE_FN} 기저 128판 + 구름 덤프"):
        _run([os.path.join("research", "proto_ledger_gate.py")],
             dict(LG_ONLY=all_env, LG_RULESEL="0", LG_BASEFN=BASE_FN,
                  LG_OBSDUMP=os.path.relpath(base_dump, ROOT)), base_log)

    # 2b) M3 지표 스캔 (선택) — 좌표 후보 판별력 보고(신축 채택/탈락 근거)
    if scan and stage(dry, "M3 지표", False, "지표은행 × AUC 전수(보고서)"):
        _run(["-m", "research.metric_scanner"],
             dict(MS_LOG=os.path.relpath(base_log, ROOT),
                  MS_DUMP=os.path.relpath(base_dump, ROOT)),
             os.path.join(LOG, f"scan_{tag}.log"))
        for ln in open(os.path.join(LOG, f"scan_{tag}.log"), encoding="utf-8"):
            print("  " + ln.rstrip())

    # 3) 폐루프 (M2 데몬: 채점→수확→귀납→재채점, 128-0 까지)
    done = os.path.exists(rules_final) and not fresh
    if stage(dry, "폐루프(데몬)", done, "F-좌표 문장 귀납·무인 수렴"):
        denv = dict(CD_TAG=tag, CD_ROUNDS="6", CD_FEATS=FEATS, LG_BASEFN=BASE_FN,
                    CD_ROSTER=roster,
                    CD_ROBUST=os.environ.get("CD_ROBUST", "0"))  # 시간창-강건 증인
        if seed_rules:
            denv["CD_RULES"] = seed_rules   # 웜스타트(검증 경로) — 미지정=콜드스타트
        rc = _run(["-m", "research.cegis_daemon"], denv,
                  os.path.join(LOG, f"daemon_{tag}.log"))
        if rc != 0:
            print("데몬 미수렴 — 로그 확인:", os.path.join(LOG, f"daemon_{tag}.log"))
            return 1
        work = os.path.join(REP, f"daemon_{tag}")
        rounds = sorted((f for f in os.listdir(work)
                         if re.fullmatch(r"rules_r\d+\.json", f)),
                        key=lambda f: int(re.search(r"\d+", f).group()))
        import shutil
        shutil.copy(os.path.join(work, rounds[-1]), rules_final)

    # 4) 다이어트 (발화-무관 축 제거 + 경계 정리)
    done = os.path.exists(rules_slim) and not fresh
    if stage(dry, "다이어트", done, "발화 스케줄 불변 증명 하의 축 축소"):
        work = os.path.join(REP, f"daemon_{tag}")
        dumps = sorted((f for f in os.listdir(LBL)
                        if re.fullmatch(rf"obs_dump_daemon_{tag}_r\d+\.csv", f)),
                       key=lambda f: int(re.search(r"_r(\d+)\.csv$", f).group(1)))
        _run(["-m", "research.slim_rules", os.path.relpath(rules_final, ROOT),
              os.path.relpath(os.path.join(LBL, dumps[-1]), ROOT),
              os.path.relpath(rules_slim, ROOT)],
             log=os.path.join(LOG, f"slim_{tag}.log"))

    # 4b) 최소성 증명 (선택) — z3 충돌그래프 MIS 로 문장 수 하한
    if minproof and stage(dry, "최소성(z3)", False, "문장 수 하한 증명서"):
        _run(["-m", "research.min_rules_bound"],
             dict(MB_DUMP=os.path.basename(base_dump),
                  MB_BASELOG=os.path.basename(base_log), MB_FEATS=FEATS),
             os.path.join(LOG, f"minproof_{tag}.log"))
        for ln in list(open(os.path.join(LOG, f"minproof_{tag}.log"),
                            encoding="utf-8"))[-6:]:
            print("  " + ln.rstrip())

    # 4b) 다이어트 실측 검증 — 시뮬(덤프 %.2f)이 못 보는 면도날을 재롤아웃으로
    #     재판. 범인 문장만 원본 축으로 되돌린 하이브리드를 정본 슬림으로 채택.
    #     (루프36 사고: 축 제거가 배포에서 한 판을 승 +19.5 → 패 -53.6 으로 뒤집음)
    if not dry and os.path.exists(rules_slim) and os.path.exists(rules_final):
        work = os.path.join(REP, f"daemon_{tag}")
        refs = sorted((f for f in os.listdir(work)
                       if re.fullmatch(r"rescore_r\d+\.log", f)),
                      key=lambda f: int(re.search(r"\d+", f).group()))             if os.path.isdir(work) else []
        ver = rules_slim.replace("_slim.json", "_verified.json")
        rc = _run(["-m", "research.verify_slim",
                   "--full", os.path.relpath(rules_final, ROOT),
                   "--slim", os.path.relpath(rules_slim, ROOT),
                   "--roster", roster,
                   "--ref", os.path.relpath(os.path.join(work, refs[-1]), ROOT) if refs else "",
                   "--out", os.path.relpath(ver, ROOT)],
                  dict(LG_BASEFN=BASE_FN),
                  os.path.join(LOG, f"verify_slim_{tag}.log"))
        for ln in list(open(os.path.join(LOG, f"verify_slim_{tag}.log"),
                            encoding="utf-8", errors="ignore"))[-3:]:
            print("  " + ln.rstrip())
        if rc == 0 and os.path.exists(ver):
            rules_slim = ver          # 이후 지문·번역·게이트는 검증본으로

    # 4c) 배포본 지문 — slim 후 문장으로 발화 기록을 재저장(회귀 검출 기준선).
    #     데몬 지문은 slim 이전 기준이라 배포본과 인덱스·경계가 다르다(루프36 수리).
    if not dry and os.path.exists(rules_slim):
        dumps = sorted((f for f in os.listdir(LBL)
                        if re.fullmatch(rf"obs_dump_daemon_{tag}_r\d+\.csv", f)),
                       key=lambda f: int(re.search(r"_r(\d+)\.csv$", f).group(1)))
        if dumps:
            import research.pipeline_invariants as _I
            fp = _I.save_fingerprint(rules_slim, os.path.join(LBL, dumps[-1]))
            print(f"[지문] 배포본 발화 기록 저장 → {os.path.relpath(fp, ROOT)}")

    # 4d) 검증된 팽창 (선택) — 상자를 자취 안으로 넓히되 보존을 롤아웃 검증
    if expand and stage(dry, "검증된 팽창", False, "일반성 극대화(롤아웃 예산 소모)"):
        dumps = sorted((f for f in os.listdir(LBL)
                        if re.fullmatch(rf"obs_dump_daemon_{tag}_r\d+\.csv", f)),
                       key=lambda f: int(re.search(r"_r(\d+)\.csv$", f).group(1)))
        if dumps:
            exp = rules_slim.replace("_slim.json", "_expanded.json")
            _run(["-m", "research.expand_rules",
                  "--rules", os.path.relpath(rules_slim, ROOT),
                  "--dump", os.path.relpath(os.path.join(LBL, dumps[-1]), ROOT),
                  "--out", os.path.relpath(exp, ROOT)],
                 log=os.path.join(LOG, f"expand_{tag}.log"))
            if os.path.exists(exp):
                rules_slim = exp          # 이후 번역·게이트는 팽창본으로
                print(f"[팽창] 채택본 → {os.path.relpath(exp, ROOT)}")

    # 5) YAML 번역 (함수-구간 3층 BT)
    if stage(dry, "YAML 번역", False, f"{agent} 재생성(항상 — 문장 정본과 동기화)"):
        _run(["-m", "research.gen_champion_yaml",
              os.path.relpath(rules_slim, ROOT), agent])

    # 6) 게이트: YAML 전판 + 연구 런타임 패리티 + 통계
    if stage(dry, "게이트", False, "YAML 128판 실측 + 패리티(항상 실행)"):
        rc = _run([os.path.join("scripts", "run_match.py"), "--blue", agent,
                   "--roster", roster, "--no-acmi"], log=gate_log)
        research_log = os.path.join(LOG, f"framework_{tag}_research.log")
        _run([os.path.join("research", "proto_ledger_gate.py")],
             dict(LG_ONLY=all_env, LG_RULESEL="0", LG_BASEFN=BASE_FN,
                  LG_SURGICAL="1",
                  LG_RULEBOX=os.path.relpath(rules_slim, ROOT)), research_log)
        print("— 게이트 통계:")
        cmd_stats(gate_log)
        print("— 패리티(YAML vs 연구):")
        parity = cmd_diff(gate_log, research_log)
        if rc != 0 or parity != 0:
            print("게이트 실패 — 전승/패리티 미달")
            return 1

    # 6b) 검증 로스터 (선택) — 추출에 쓰지 않은 홀드아웃 상대의 성적(엄격 격리:
    #     여기 패배는 데몬 수리에 유입하지 않는다 — 일반화 측정 전용)
    if val and stage(dry, "검증(val)", False, f"{val} 홀드아웃 성적(훈련 미유입)"):
        val_log = os.path.join(LOG, f"framework_{tag}_val.log")
        _run([os.path.join("scripts", "run_match.py"), "--blue", agent,
              "--roster", val, "--no-acmi"], log=val_log)
        print("— 검증(홀드아웃) 통계:")
        cmd_stats(val_log)

    # 7) 녹화 세대 (replay 규약)
    gen_dir = os.path.join(ROOT, "replays", f"roster_{tag}_final")
    done = os.path.isdir(gen_dir) and not fresh
    if replay and stage(dry, "녹화", done, f"{gen_dir} — 판당 acmi+복기"):
        _run([os.path.join("scripts", "run_match.py"), "--blue", agent,
              "--roster", roster, "--acmi-dir",
              os.path.relpath(gen_dir, ROOT)],
             log=os.path.join(LOG, f"framework_{tag}_replay.log"))

    # 8) LOFO 일반화 (가족-제외 교차검증)
    lofo_mat = os.path.join(REP, f"lofo_{tag}", "lofo_matrix.csv")
    done = os.path.exists(lofo_mat) and not fresh
    if lofo and stage(dry, "LOFO", done, "14가족 이월·회귀 행렬"):
        _run(["-m", "research.lofo_driver"],
             dict(LOFO_TAG=tag, LOFO_BASELOG=os.path.basename(base_log),
                  LOFO_DUMP=os.path.basename(base_dump), LOFO_FEATS=FEATS,
                  LG_BASEFN=BASE_FN),
             os.path.join(LOG, f"lofo_{tag}.log"))
    if lofo and os.path.exists(lofo_mat):
        import csv as _csv
        rows = list(_csv.DictReader(open(lofo_mat)))
        conv = sum(int(r["conv"]) for r in rows)
        loss = sum(int(r["base_loss"]) for r in rows)
        regr = sum(int(r["regr"]) for r in rows)
        print(f"— LOFO: 이월 {conv}/{loss} = {conv/max(loss,1)*100:.1f}%  회귀 {regr}")

    if not dry:
        print()
        cmd_audit(tag, roster, val)   # 사슬 감사 자동 실행(루프36)
        print(f"\n완료 — 문장 정본 {os.path.relpath(rules_slim, ROOT)}, "
              f"실행형 {agent}, 게이트 로그 {os.path.relpath(gate_log, ROOT)}")
    return 0


def _gate_only(agent: str, roster: str, tag: str) -> int:
    all_env = open(os.path.join(ROOT, roster), encoding="utf-8").read() \
        .strip().replace("\r", "").replace("\n", ",")
    gate_log = os.path.join(LOG, f"framework_{tag}_gate.log")
    rc = _run([os.path.join("scripts", "run_match.py"), "--blue", agent,
               "--roster", roster, "--no-acmi"], log=gate_log)
    cmd_stats(gate_log)
    rules_slim = os.path.join(LBL, f"induced_rules_{tag}_slim.json")
    if os.path.exists(rules_slim):                 # usage 약속대로 패리티까지
        research_log = os.path.join(LOG, f"framework_{tag}_research.log")
        _run([os.path.join("research", "proto_ledger_gate.py")],
             dict(LG_ONLY=all_env, LG_RULESEL="0", LG_BASEFN=BASE_FN,
                  LG_SURGICAL="1",
                  LG_RULEBOX=os.path.relpath(rules_slim, ROOT)), research_log)
        print("— 패리티(YAML vs 연구):")
        rc = rc or cmd_diff(gate_log, research_log)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--agent", default="agents/champion128.yaml")
    p.add_argument("--roster", default="roster/all_128.txt")
    p.add_argument("--tag", default="f32")
    p.add_argument("--replay", action="store_true", help="녹화 세대 생성")
    p.add_argument("--lofo", action="store_true", help="일반화 행렬까지")
    p.add_argument("--dry", action="store_true", help="계획·단계 상태만 출력")
    p.add_argument("--fresh", action="store_true", help="산출물 있어도 전 단계 재실행")
    p.add_argument("--scan", action="store_true", help="M3 지표 스캔 보고 포함")
    p.add_argument("--minproof", action="store_true", help="z3 문장수 하한 증명 포함")
    p.add_argument("--seed-rules", default="", help="데몬 웜스타트 문장 json(미지정=콜드)")
    p.add_argument("--val", default="", help="검증 로스터(홀드아웃 — 훈련 미유입, 성적 보고만)")
    p.add_argument("--expand", action="store_true", help="검증된 팽창(일반성 극대화)")
    p = sub.add_parser("split")
    p.add_argument("--roster", default="roster/all_128.txt")
    p.add_argument("--holdout", type=float, default=0.25)
    p.add_argument("--seed", type=int, required=True, help="추첨 시드(선언·기록 — 재현 가능)")
    p = sub.add_parser("gate")
    p.add_argument("--agent", default="agents/champion128.yaml")
    p.add_argument("--roster", default="roster/all_128.txt")
    p.add_argument("--tag", default="f32")
    p = sub.add_parser("stats")
    p.add_argument("--log", required=True)
    p = sub.add_parser("diff")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p = sub.add_parser("schedule")
    p.add_argument("--rules", required=True)
    p.add_argument("--dump", required=True)
    p = sub.add_parser("timing")
    p.add_argument("--witness", default="research/campaigns/witness")
    p = sub.add_parser("audit")
    p.add_argument("--tag", required=True)
    p.add_argument("--roster", default="roster/all_128.txt")
    p.add_argument("--val", default="")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run(a.agent, a.roster, a.tag, a.replay, a.lofo, a.dry,
                       a.fresh, a.scan, a.minproof, a.seed_rules, a.val, a.expand)
    if a.cmd == "split":
        return cmd_split(a.roster, a.holdout, a.seed)
    if a.cmd == "gate":
        return _gate_only(a.agent, a.roster, a.tag)
    if a.cmd == "stats":
        return cmd_stats(a.log)
    if a.cmd == "diff":
        return cmd_diff(a.a, a.b)
    if a.cmd == "schedule":
        return cmd_schedule(a.rules, a.dump)
    if a.cmd == "timing":
        return cmd_timing(a.witness)
    if a.cmd == "audit":
        return cmd_audit(a.tag, a.roster, a.val)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
