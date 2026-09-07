"""M2 — CEGIS 메타-드라이버 (AUTOMATION_PLAN §S7).

무인 반복: 채점 → 반례 → (증인 수확) → (배포-구성 덤프) → 귀납(관계형→절대 2단계,
후행-선두 배치) → 재채점, 반례 0 또는 증인 소진까지. 사람 개입 0.

usage: CD_RULES=<시작 문장 json> CD_TAG=<캠페인명> python -m research.cegis_daemon
env:
  CD_RULES   시작 문장 파일 (기본: 빈 목록에서 시작)
  CD_TAG     캠페인명 — 산출물 접두 (필수)
  CD_ROUNDS  최대 라운드 (기본 4)
  CD_REUSE_WIT=1  기존 bs_*.log 증인 재사용 허용 (기본 1; 수확 생략 가능 시 생략)
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import shutil
import subprocess
import time as _time
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from research import pipeline_invariants as I

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
LBL = I.LBL
REP = I.REP
# CD_ROSTER: 재채점 대상 로스터(기본 128판; train/val 캠페인은 train 목록 지정)
ALL128 = ",".join(s.strip() for s in open(
    os.path.join(ROOT, os.environ.get("CD_ROSTER", "roster/all_128.txt")),
    encoding="utf-8").read().replace(chr(13), "").replace(chr(10), ",")
    .split(",") if s.strip())
# CD_FEATS 로 관계형 좌표 오버라이드(루프31 F-좌표 캠페인: +race,vdiff)
REL_FEATS = os.environ.get(
    "CD_FEATS", "rng,ata,eata,agap,hp_lead,clos,pursue,hotrun,eclimb,dalt,es_rel")
RE_RES = re.compile(r"\s+(\S+)/(blue|red)\s+(승|무|패)\s+([+-][\d.]+).*?@(\d+)s")


def run(env_extra: dict, args: list, log: str) -> None:
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")   # 결정론(심층 방어)
    basefn = env.get("LG_BASEFN")           # 루프32: 기저함수 캠페인은 전 단계 공유
    for k in list(env):
        if k.startswith(("LG_", "RI_", "BS_")):
            env.pop(k)                      # 구성 오염 방지 — 명시 전달만
    if basefn:
        env["LG_BASEFN"] = basefn
    env.update({k: str(v) for k, v in env_extra.items()})
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run([sys.executable] + args, cwd=ROOT, env=env,
                       stdout=f, stderr=subprocess.STDOUT, check=False)


def spawn(env_extra: dict, args: list, log: str):
    """run() 과 같은 환경 위생으로 프로세스를 띄우되 기다리지 않는다(격자 병렬용)."""
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    basefn = env.get("LG_BASEFN")
    for k in list(env):
        if k.startswith(("LG_", "RI_", "BS_")):
            env.pop(k)
    if basefn:
        env["LG_BASEFN"] = basefn
    env.update({k: str(v) for k, v in env_extra.items()})
    f = open(log, "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable] + args, cwd=ROOT, env=env,
                         stdout=f, stderr=subprocess.STDOUT)
    return p, f


def ic_grid() -> list[tuple[str, str]]:
    """(국면, 시드) 격자. 시드 "0" = 지터 없는 기준 IC.

    루프38 실측: 고정 IC 하나 위에서 유도한 문장은 IC 를 흔들면 순손해였다
    (챔프 65.2% vs 문장 끈 기저 70.2%, 3,000판). 원인은 문장이 아니라 **합성 절차의
    표본 공간**이므로, 반례 수집부터 격자 위에서 해야 한다.
    """
    scs = [x.strip() for x in os.environ.get("CD_SCENARIOS", "headon").split(",")
           if x.strip()]
    sds = [x.strip() for x in os.environ.get("CD_IC_SEEDS", "0").split(",")
           if x.strip()]
    return [(sc, sd) for sc in scs for sd in sds]


def cell_env(sc: str, sd: str) -> dict:
    """격자 한 칸의 IC 환경. 시드 0 은 기준 IC(지터 없음)."""
    env = {"LG_SCENARIO": sc}
    if sd not in ("0", ""):
        env["LG_IC_SEED"] = sd
    return env


def cell_key(slot: str, sc: str, sd: str) -> str:
    """반례 식별자 — 슬롯만으로는 IC 를 구분하지 못한다."""
    return slot + ("" if sc == "headon" else f"@{sc}") + ("" if sd in ("0", "") else f"@s{sd}")


def _parse_res(log: str) -> dict:
    out = {}
    for ln in open(log, encoding="utf-8", errors="replace"):
        m = RE_RES.match(ln)
        if m:
            out[f"{m.group(1)}/{m.group(2)}"] = (m.group(3), float(m.group(4)),
                                                 int(m.group(5)))
    return out


def rescore(rules: str, log: str, dump: str | None = None) -> dict:
    """IC 격자 전 칸을 채점해 하나의 결과 사전으로 합친다(칸마다 병렬 프로세스).

    덤프도 칸마다 따로 쓰고 하나로 잇는다 — 엄격분리가 덤프 위에서 돌므로, 덤프에
    전 IC 가 담겨야 상자가 **다른 IC 의 승리 자취**까지 침범하지 않게 된다.
    """
    grid = ic_grid()
    base = os.path.splitext(log)[0]
    procs, cells = [], []
    for sc, sd in grid:
        clog = log if len(grid) == 1 else f"{base}__{sc}_s{sd}.log"
        cdump = None
        if dump:
            cdump = dump if len(grid) == 1 else                 f"{os.path.splitext(dump)[0]}__{sc}_s{sd}.csv"
        env = dict(LG_ONLY=ALL128, LG_SURGICAL="1",
                   LG_RULEBOX=os.path.relpath(rules, ROOT))
        env.update(cell_env(sc, sd))
        if cdump:
            env["LG_OBSDUMP"] = os.path.relpath(cdump, ROOT)
        procs.append(spawn(env, [os.path.join("research", "proto_ledger_gate.py")], clog))
        cells.append((sc, sd, clog, cdump))
    for p, f in procs:
        p.wait(); f.close()

    res, dumps = {}, []
    n_slot = len([s for s in ALL128.split(",") if s.strip()])
    for sc, sd, clog, cdump in cells:
        r = _parse_res(clog)
        assert len(r) == n_slot, f"채점 파싱 {len(r)}/{n_slot} — {clog}"
        for slot, v in r.items():
            res[cell_key(slot, sc, sd)] = v
        if cdump and os.path.exists(cdump):
            dumps.append(cdump)
    if dump and len(dumps) > 1:            # 칸 덤프를 헤더 1회로 이어붙인다
        with open(dump, "w", encoding="utf-8", newline="") as out:
            for i, d in enumerate(dumps):
                with open(d, encoding="utf-8") as f:
                    for j, ln in enumerate(f):
                        if j == 0 and i > 0:
                            continue
                        out.write(ln)
    return res


def _canon_durs(spec: str) -> str:
    """지속시간 목록의 표준형 — 숫자 정렬 + %g 포맷(2.0 과 2 를 같은 것으로)."""
    return ",".join(f"{float(x):g}" for x in sorted(
        (float(v) for v in spec.split(",") if v.strip()), key=float))


def harvest_sig() -> str:
    """현 캠페인의 수확 조건 서명 — 증인 재사용 가능 여부 판정 기준.

    양쪽(기록/대조)이 같은 표준형을 쓰지 않으면 영원히 불일치가 된다
    (루프36 2차 결함: 기록 "durs=2.0,4.0" vs 대조 "durs=12,2,4,8")."""
    acts = os.environ.get("CD_ACTS", "gun_pure,dive,extend,break")
    durs = os.environ.get("CD_DURS", "4,8")
    return (f"acts={','.join(sorted(acts.split(',')))}"
            f" durs={_canon_durs(durs)}")


def witness_matches(path: str) -> bool:
    """기존 증인 로그가 현 수확 조건으로 만들어졌는지(서명 대조).

    서명이 없거나(구 파일) 어휘·지속이 다르면 False → 재수확.
    루프36 함정 두 겹의 교정:
      ① JSBSim C++ 배너가 파일 디스크립터로 먼저 쓰여 서명이 1행이 아니다
         → 파일 앞부분을 스캔한다(첫 줄만 보면 항상 불일치).
      ② 기록/대조의 수치 포맷이 다르면 영원히 불일치 → 표준형(_canon_durs)."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = None
            for i, ln in enumerate(f):
                if ln.startswith("#HARVEST "):
                    head = ln
                    break
                if i > 200:            # 서명은 헤더 영역에만 온다
                    break
    except OSError:
        return False
    if not head:
        return False
    want = harvest_sig()
    # 기록된 durs 도 표준형으로 정규화해 비교
    parts = dict(tok.split("=", 1) for tok in head.split()[1:] if "=" in tok)
    if "durs" in parts:
        parts["durs"] = _canon_durs(parts["durs"])
    got = " ".join(f"{k}={parts[k]}" for k in ("acts", "durs") if k in parts)
    return got == want


def split_cell(cell: str) -> tuple[str, str, str]:
    """반례 식별자 → (슬롯, 국면, 시드). cell_key 의 역함수."""
    parts = cell.split("@")
    slot, sc, sd = parts[0], "headon", "0"
    for p in parts[1:]:
        if p.startswith("s") and p[1:].isdigit():
            sd = p[1:]
        else:
            sc = p
    return slot, sc, sd


def harvest_spawn(cell: str, te: int, rules: str, out: str):
    """반례 한 칸의 되감기 증인 수확 — **그 칸의 IC 를 재현해서** 수색한다.

    프로세스만 띄우고 기다리지 않는다. 수확은 반례 수만큼(수백 건) 돌아야 하는데
    건당 2~3분이라 순차로는 한 라운드에 14시간이 걸렸다 — 채점은 이미 격자 병렬인데
    수확만 단일 스레드로 남아 있던 것이 병목이었다. 되감기도 매치가 서로 독립이고
    엔진에 자생 난수가 없어 병렬화가 결정론을 깨지 않는다.
    """
    case, sc, sd = split_cell(cell)
    # 경로-슬롯(agents/champion128/blue)은 슬래시가 둘 — 마지막만 진영 구분자다.
    stem, side = case.rsplit("/", 1)
    w1 = max(26, min(60, te - 4))
    # 루프34: 수확 창 하한 22s(≈armed 이후) — 가드가 차단할 pre-armed 증인 배제
    return spawn(
        dict(LG_SURGICAL="1", LG_RULEBOX=os.path.relpath(rules, ROOT),
             BS_CASE=case, BS_WIN=f"22,{w1}", BS_STEP=4 if w1 <= 40 else 6,
             BS_DURS=os.environ.get("CD_DURS", "4,8"),
             BS_ACTS=os.environ.get("CD_ACTS", "gun_pure,dive,extend,break"),
             BS_DRAW_OK=os.environ.get("CD_ALLOW_DRAW", "0"),
             **cell_env(sc, sd)),
        [os.path.join("research", "branch_search.py")], out)


def induct(wit_dir: str, dump_rel: str, feats: str | None, out_json: str,
           log: str, deploy_rules: str) -> list[str]:
    env = dict(LG_RULESEL="0", LG_SURGICAL="1",
               LG_RULEBOX=os.path.relpath(deploy_rules, ROOT),
               RI_SCRATCH=wit_dir, RI_PREFIX="bs_", RI_DUMPS=dump_rel,
               RI_OUT=os.path.basename(out_json),
               RI_ARMED_ONLY="1",          # 루프34: 가드-호환 문장만 귀납
               RI_DRAW_OK=os.environ.get("CD_ALLOW_DRAW", "0"),  # ③층 연동
               RI_ROBUST=os.environ.get("CD_ROBUST", "0"))       # 시간창-강건 증인
    if feats:
        env["RI_FEATS"] = feats
    run(env, ["-m", "research.rule_induct"], log)
    return [m.group(1) for ln in open(log, encoding="utf-8")
            if (m := re.search(r"\[미해결 반례\] (\S+) —", ln))]


def main():
    tag = os.environ["CD_TAG"]
    rounds = int(os.environ.get("CD_ROUNDS", "4"))
    reuse = os.environ.get("CD_REUSE_WIT", "1") == "1"
    work = os.path.join(REP, f"daemon_{tag}")
    I.claim_generation_dir(work)
    cur = os.path.join(work, "rules_r0.json")
    src = os.environ.get("CD_RULES")
    json.dump(json.load(open(src)) if src else [], open(cur, "w"), indent=1)

    for rnd in range(1, rounds + 1):
        dump = os.path.join(LBL, f"obs_dump_daemon_{tag}_r{rnd}.csv")
        log = os.path.join(work, f"rescore_r{rnd}.log")
        res = rescore(cur, log, dump)
        # CD_ALLOW_DRAW=1(루프35 ③층): 무승부는 반례 아님 — 불패(패=0)가 수렴 기준.
        bad = ("승", "무") if os.environ.get("CD_ALLOW_DRAW") == "1" else ("승",)
        losses = {c: v for c, v in res.items() if v[0] not in bad}
        print(f"[r{rnd}] {len(res)-len(losses)}승 / 반례 {len(losses)}"
              f"  (격자 {len(ic_grid())}칸 × 슬롯 {len(res)//max(len(ic_grid()),1)})",
              flush=True)
        if not losses:
            fp = I.save_fingerprint(cur, dump)
            print(f"수렴: {cur}\n지문: {fp}")
            return 0
        # 증인: 재사용 or 수확 (배포-구성)
        wd = os.path.join(work, f"wit_r{rnd}")
        os.makedirs(wd, exist_ok=True)
        todo = []
        for c, (_, _, te) in losses.items():
            # 경로-슬롯(agents/champion128/blue)의 "/" 를 "_" 로 바꾸면 되돌릴 수
            # 없다(어느 밑줄이 원래 슬래시였는지 모른다). 파일명에 못 쓰는 문자가
            # 아니면서 슬롯 이름에 안 나오는 "~" 로 인코딩한다.
            name = "bs_" + c.replace("/", "~") + ".log"
            dst = os.path.join(wd, name)
            prior = os.path.join(REP, "witness", name)
            if reuse and os.path.exists(prior) and witness_matches(prior):
                shutil.copy(prior, dst)              # 조건 일치 증인만 재사용
            elif not os.path.exists(dst):
                if reuse and os.path.exists(prior):
                    print(f"[r{rnd}] 재수확(조건 불일치): {c}", flush=True)
                todo.append((c, te, dst))
        # 격자를 고르게 섞는다 — 사전순으로 두면 한 국면(headon)이 앞을 다 차지해
        # 방어 국면 반례가 끝까지 밀린다(실측: 122건 수확 중 perch_defense 0건).
        todo.sort(key=lambda x: (x[0].split("@")[-1], x[0]))
        nw = int(os.environ.get("CD_WORKERS", max(1, (os.cpu_count() or 8) // 2)))
        print(f"[r{rnd}] 수확 {len(todo)}건 · 워커 {nw}", flush=True)
        pend, run_, done_n = list(todo), {}, 0
        t0 = _time.time()
        while pend or run_:
            while pend and len(run_) < nw:
                c, te, dst = pend.pop(0)
                run_[harvest_spawn(c, te, cur, dst)] = c
            for pf in list(run_):
                proc, fh = pf
                if proc.poll() is not None:
                    fh.close(); c = run_.pop(pf); done_n += 1
                    print(f"[r{rnd}] 수확 {done_n}/{len(todo)} {c} "
                          f"({(_time.time()-t0)/60:.1f}분)", flush=True)
            if run_:
                _time.sleep(0.5)
        # 특징 사다리 귀납 (M3) → 신규 문장 선두 배치
        # 관계형 → +장기지속 → 절대-포함 순으로, 미해결이 남는 동안만 다음 단.
        # ※ rule_induct 는 RI_OUT 을 항상 data/ 에 쓴다 — 태그-접두 basename
        #   으로 충돌을 막고, 읽기도 그 경로에서 한다 (r1 오탐 사고의 교정).
        LADDER = [("rel", REL_FEATS), ("relt", REL_FEATS + ",t,fdmg")]
        new_rules = []
        unres = None
        for lname, lfeats in LADDER:
            src_wd = wd
            if unres is not None:          # 이전 단의 미해결분만 다음 단으로
                src_wd = os.path.join(work, f"wit_{lname}_r{rnd}")
                os.makedirs(src_wd, exist_ok=True)
                for c in unres:
                    s = os.path.join(wd, "bs_" + c.replace("/", "_") + ".log")
                    if os.path.exists(s):
                        shutil.copy(s, src_wd)
                if not os.listdir(src_wd):
                    break
            lj = os.path.join(LBL, f"daemon_{tag}_r{rnd}_{lname}.json")
            unres = induct(src_wd, os.path.basename(dump), lfeats, lj,
                           os.path.join(work, f"induct_{lname}_r{rnd}.log"), cur)
            if os.path.exists(lj):
                new_rules = json.load(open(lj)) + new_rules
            if not unres:
                break
        if unres:
            wd2 = os.path.join(work, f"wit_abs_r{rnd}")
            os.makedirs(wd2, exist_ok=True)
            for c in unres:
                s = os.path.join(wd, "bs_" + c.replace("/", "_") + ".log")
                if os.path.exists(s):
                    shutil.copy(s, wd2)
            abs_j = os.path.join(LBL, f"daemon_{tag}_r{rnd}_abs.json")
            unres = induct(wd2, os.path.basename(dump), None, abs_j,
                           os.path.join(work, f"induct_abs_r{rnd}.log"), cur)
            if os.path.exists(abs_j):
                new_rules = json.load(open(abs_j)) + new_rules
        if not new_rules:
            print(f"[r{rnd}] 신규 문장 0 — 증인 소진 {len(unres)}건, 중단")
            return 1
        nxt = os.path.join(work, f"rules_r{rnd}.json")
        json.dump(new_rules + json.load(open(cur)), open(nxt, "w"), indent=1)
        print(f"[r{rnd}] 문장 +{len(new_rules)} (선두 배치) → {nxt}", flush=True)
        cur = nxt
    print("최대 라운드 도달 — 미수렴")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
