"""9부 P1 — 가족-제외 교차검증(LOFO) 드라이버.

각 가족 f 에 대해: 귀납 재료(증인·구름·검증)에서 f 를 완전 봉인하고 문장을
재귀납(관계형 → 미해결분 절대-포함 2단계, 루프29 절차 동일) → f 전 슬롯에
배포 채점 → (이월, 회귀) 기록. 산출: lofo_matrix.csv + 요약.

전제: 기저 = 플레인 게이트(96-32, obsdump_plain_all_es.log), 증인 =
replays/bs_*.log (기저 32패 전 케이스, 플레인 기저 수확).

usage: python -m research.lofo_driver [fam ...]   # 무인자 = 전 가족
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PM = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PM)
LBL = os.path.join(PM, "data", "blueteam")
REP = os.path.join(PM, "campaigns")
# 캠페인 분리(루프31): LOFO_TAG 지정 시 산출 폴더·파일이 태그-접두로 격리돼
# 정본(lofo/) 행렬을 덮어쓰지 않는다. LOFO_DUMP·LOFO_FEATS 로 좌표계 실험.
TAG = os.environ.get("LOFO_TAG", "")
LOFO = os.path.join(REP, "lofo" + (f"_{TAG}" if TAG else ""))
PLAIN_LOG = os.path.join(REP, "logs", os.environ.get("LOFO_BASELOG", "obsdump_plain_all_es.log"))
PLAIN_DUMP = os.path.join(LBL, os.environ.get("LOFO_DUMP", "obs_dump_plain_all_es.csv"))
REL_FEATS = os.environ.get(
    "LOFO_FEATS", "rng,ata,eata,agap,hp_lead,clos,pursue,hotrun,eclimb,dalt,es_rel")

RE_RESULT = re.compile(r"\s+(\S+)/(blue|red)\s+(승|무|패)\s+([+-][\d.]+)")


def fam_of(stem: str) -> str:
    return stem.rsplit("_", 1)[0] if not stem.startswith("anchor") else "anchor"


def baseline() -> dict:
    """플레인 기저 128판 결과: case -> (승|무|패, Δ)."""
    res = {}
    for ln in open(PLAIN_LOG, encoding="utf-8"):
        m = RE_RESULT.match(ln)
        if m:
            res[f"{m.group(1)}/{m.group(2)}"] = (m.group(3), float(m.group(4)))
    # 로스터 크기 동적(train/val 분리 캠페인은 128 이 아니다 — 루프36 수리)
    assert len(res) >= 8, f"기저 파싱 {len(res)}건 — 로그 형식 확인: {PLAIN_LOG}"
    return res


def run(cmd_env: dict, args: list, log: str) -> None:
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")   # 결정론(심층 방어)
    env.pop("LG_IC_SEED", None)          # LOFO 는 정본 IC
    env.update({k: str(v) for k, v in cmd_env.items()})
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run([sys.executable] + args, cwd=ROOT, env=env,
                       stdout=f, stderr=subprocess.STDOUT, check=False)


def induct(fold: str, wit_dir: str, dump: str, feats: str | None, out_json: str,
           log: str) -> list[str]:
    """rule_induct 1회 실행 → 미해결 케이스 목록 반환."""
    env = dict(LG_RULESEL="0", RI_SCRATCH=wit_dir, RI_PREFIX="bs_",
               RI_DUMPS=os.path.basename(dump), RI_OUT=os.path.basename(out_json))
    if feats:
        env["RI_FEATS"] = feats
    run(env, ["-m", "research.rule_induct"], log)
    unresolved = []
    for ln in open(log, encoding="utf-8"):
        m = re.search(r"\[미해결 반례\] (\S+) —", ln)
        if m:
            unresolved.append(m.group(1))
    return unresolved


def main():
    base = baseline()
    losses = [c for c, (r, _) in base.items() if r == "패"]
    all_wit = {}   # case -> 증인 로그 경로
    for p in glob.glob(os.path.join(REP, "witness", "bs_*.log")):
        b = os.path.basename(p)[3:-4]
        if "@" in b:
            continue                      # 시드 증인 제외 (루프30)
        stem, side = b.rsplit("_", 1)
        all_wit[f"{stem}/{side}"] = p
    missing = [c for c in losses if c not in all_wit]
    assert not missing, f"증인 없는 기저 패배: {missing}"

    fams = sorted({fam_of(c.split("/")[0]) for c in base})
    todo = sys.argv[1:] or fams
    os.makedirs(LOFO, exist_ok=True)
    mat_path = os.path.join(LOFO, "lofo_matrix.csv")
    done = set()
    if os.path.exists(mat_path):
        done = {r["fam"] for r in csv.DictReader(open(mat_path))}
    mode = "a" if done else "w"
    with open(mat_path, mode, newline="") as mf:
        w = csv.writer(mf)
        if not done:
            w.writerow(["fam", "base_loss", "base_win", "conv", "regr",
                        "rules_rel", "rules_abs", "unres_nonfam"])
        for fam in todo:
            if fam in done:
                print(f"[{fam}] 이미 완료 — 스킵", flush=True)
                continue
            fd = os.path.join(LOFO, fam)
            wd = os.path.join(fd, "wit")
            os.makedirs(wd, exist_ok=True)
            # ① 봉인: 증인은 f-외 패배만
            targets = [c for c in losses if fam_of(c.split("/")[0]) != fam]
            for c in targets:
                shutil.copy(all_wit[c], os.path.join(
                    wd, "bs_" + c.replace("/", "_") + ".log"))
            # ② 봉인: 구름도 f-외 궤적만
            dump = os.path.join(LBL, f"obs_dump_lofo_{TAG + '_' if TAG else ''}{fam}.csv")
            with open(PLAIN_DUMP) as fi, open(dump, "w", newline="") as fo:
                rd = csv.reader(fi); hdr = next(rd)
                wr = csv.writer(fo); wr.writerow(hdr)
                for row in rd:
                    if fam_of(row[0].split("/")[0]) != fam:
                        wr.writerow(row)
            # ③ 2단계 귀납 (관계형 → 잔여 절대-포함)
            rel_j = os.path.join(LBL, f"lofo_{TAG + '_' if TAG else ''}{fam}_rel.json")
            unres = induct(fam, wd, dump, REL_FEATS, rel_j,
                           os.path.join(fd, "induct_rel.log"))
            abs_rules = []
            if unres:
                wd2 = os.path.join(fd, "wit_abs")
                os.makedirs(wd2, exist_ok=True)
                for c in unres:
                    src = os.path.join(wd, "bs_" + c.replace("/", "_") + ".log")
                    if os.path.exists(src):
                        shutil.copy(src, os.path.join(
                            wd2, "bs_" + c.replace("/", "_") + ".log"))
                abs_j = os.path.join(LBL, f"lofo_{TAG + '_' if TAG else ''}{fam}_abs.json")
                unres2 = induct(fam, wd2, dump, None, abs_j,
                                os.path.join(fd, "induct_abs.log"))
                if os.path.exists(abs_j):
                    abs_rules = json.load(open(abs_j))
                unres = unres2
            rel_rules = json.load(open(rel_j)) if os.path.exists(rel_j) else []
            rules = abs_rules + rel_rules
            merged = os.path.join(LBL, f"lofo_{TAG + '_' if TAG else ''}{fam}_rules.json")
            json.dump(rules, open(merged, "w"), indent=1)
            # ④ 봉인 가족 전 슬롯 채점 (문장은 f 를 본 적이 없다)
            slots = [c for c in base if fam_of(c.split("/")[0]) == fam]
            ev_log = os.path.join(fd, "eval.log")
            run(dict(LG_ONLY=",".join(slots), LG_SURGICAL="1",
                     LG_RULEBOX=os.path.relpath(merged, ROOT)),
                [os.path.join("research", "proto_ledger_gate.py")], ev_log)
            res = {}
            for ln in open(ev_log, encoding="utf-8"):
                m = RE_RESULT.match(ln)
                if m:
                    res[f"{m.group(1)}/{m.group(2)}"] = m.group(3)
            bl = [c for c in slots if base[c][0] == "패"]
            bw = [c for c in slots if base[c][0] == "승"]
            conv = sum(1 for c in bl if res.get(c) == "승")
            regr = sum(1 for c in bw if res.get(c) != "승")
            w.writerow([fam, len(bl), len(bw), conv, regr,
                        len(rel_rules), len(abs_rules), len(unres)])
            mf.flush()
            print(f"[{fam}] 기저 {len(bl)}패/{len(bw)}승 → 이월 {conv}/{len(bl)} "
                  f"회귀 {regr}  (문장 rel{len(rel_rules)}+abs{len(abs_rules)})",
                  flush=True)
    print("LOFO 완료:", mat_path)


if __name__ == "__main__":
    raise SystemExit(main())
