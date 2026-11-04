"""여러 PC 의 games.csv (shard) 를 검사하고 문제가 없을 때만 합친다. 입력 파일은 읽기만 한다.

  python bt/merge.py bt/thetas/x.csv --prefix bt-main --out bt/out/bt-main/games.csv \\
      bt/out/bt-main/games_shard1of3.csv pc2/games_shard2of3.csv pc3/games_shard3of3.csv

검사: 열 (지금 계약 FIELDS), 중복 경기, 누락 경기 (θ 목록·접두어·상대 묶음으로 만든 전체 경기와 비교), 계획 밖 경기,
code_commit·engine_sha·opponent_set 불일치 (파일 사이 포함), wall_clock, disqualified.
하나라도 있으면 합치지 않고 종료 코드 1. 보고서는 화면과 --report (기본 <out>.merge_report.md) 에 쓴다.

--equivalent-commits C1 C2 ...: code_commit 이 태그 prereg-bt-v1 커밋과 다른 shard 를 받아들이는 옵션.
각 커밋과 태그 사이 git diff 가 시뮬레이션 결과에 영향을 주는 파일 (IMPACT) 을 건드리지 않을 때만 태그 커밋과 같은 것으로 본다.
run_bt.py 는 결과 폴더 함수 out_dir_for 와 그 호출 줄 밖의 변경이 있으면 거부한다. 보고서에 사용 사실과 검사 결과를 적는다.
"""
from __future__ import annotations

import argparse
import collections as C
import csv
import os
import re
import subprocess
import sys

BT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BT)
import run_bt  # noqa: E402


TAG = run_bt.PREREG_TAG
# 시뮬레이션 결과에 영향을 주는 파일 (kit 기준). run_bt.py 는 따로 (out_dir_for 밖 변경만 영향으로 본다)
IMPACT_DIRS = ("aircombat/", "jsbsim_data/", "config/", "bt/opponents_patched/")
IMPACT_FILES = ("bt/make_tree.py", "bt/params.yaml", "bt/tree_template.yaml")
IMPACT_RE = re.compile(r"^bt/thetas/main_[^/]*\.csv$")
RUN_BT = "bt/run_bt.py"


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=BT, capture_output=True, check=True).stdout.decode("utf-8")


def _normalize_run_bt(text: str) -> str:
    """out_dir_for 함수 정의를 지우고, 결과 폴더를 정하는 'out_dir = ...' 줄을 자리표시자로 바꾼다."""
    text = re.sub(r"\ndef out_dir_for\(.*?(?=\ndef |\Z)", "\n", text, flags=re.S)
    text = re.sub(r"(?m)^(\s*)out_dir = .*$", r"\1out_dir = <OUT_DIR>", text)
    return re.sub(r"\n{3,}", "\n\n\n", text).rstrip() + "\n"        # 함수를 지운 자리의 빈 줄 수를 맞춘다


def equivalence_check(commits, base=TAG):
    """[(커밋, 통과 여부, 이유)]. base 는 태그 (기본 prereg-bt-v1). 커밋은 짧은 해시도 된다."""
    kit = _git("rev-parse", "--show-prefix").strip()                 # 저장소 안 kit 경로, 예: cadet_research/kit/bt/
    kit = kit[:-len("bt/")] if kit.endswith("bt/") else kit
    base_c = _git("rev-parse", f"{base}^{{commit}}").strip()
    out = []
    for c in commits:
        try:
            full = _git("rev-parse", f"{c}^{{commit}}").strip()
        except subprocess.CalledProcessError:
            out.append((c, False, "git 에 없는 커밋"))
            continue
        changed = [f[len(kit):] for f in _git("diff", "--name-only", base_c, full).split() if f.startswith(kit)]
        hit = [f for f in changed if f.startswith(IMPACT_DIRS) or f in IMPACT_FILES or IMPACT_RE.match(f)]
        if RUN_BT in changed:
            a = _normalize_run_bt(_git("show", f"{base_c}:{kit}{RUN_BT}"))
            b = _normalize_run_bt(_git("show", f"{full}:{kit}{RUN_BT}"))
            if a != b:
                hit.append(RUN_BT + " (out_dir_for 밖 변경)")
        out.append((c, not hit, ("영향 파일 변경: " + ", ".join(hit)) if hit else
                    f"영향 파일 변경 없음 (바뀐 kit 파일 {len(changed)}개" + (", run_bt.py 는 out_dir_for 만" if RUN_BT in changed else "") + ")"))
    return out


def check(paths, thetas, prefix, r0=False, opponent_set=run_bt.DEFAULT_SET, nseeds=run_bt.SEEDS, equivalent=()):
    """(합칠 행, 보고 줄, 문제 수). equivalent: 태그 커밋과 같은 것으로 볼 커밋들 (equivalence_check 통과해야 함)."""
    expected = {tuple(str(j[k]) for k in run_bt.KEY)
                for j in run_bt.build_jobs(run_bt.read_thetas(thetas, r0), prefix, r0, opponent_set, nseeds)}
    L, problems, rows = [], 0, []
    L += ["| 파일 | 경기 | code_commit | engine_sha | opponent_set | wall_clock | disqualified |", "|---|---|---|---|---|---|---|"]
    for p in paths:
        with open(p, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            got = list(rd)
            if rd.fieldnames != run_bt.FIELDS:
                L.append(f"| {p} | 열이 계약과 다름 | | | | | |")
                problems += 1
                continue
        rows += [(p, r) for r in got]
        val = lambda k: ", ".join(sorted({r[k] for r in got})) or "—"
        L.append(f"| {os.path.basename(p)} | {len(got)} | {val('code_commit')} | {val('engine_sha')} | {val('opponent_set')} "
                 f"| {sum(r['end_reason'] == 'wall_clock' for r in got)} | {sum(r['end_reason'] == 'disqualified' for r in got)} |")
    commit_kinds = {r["code_commit"] for _, r in rows}
    if equivalent:
        base12 = _git("rev-parse", f"{TAG}^{{commit}}").strip()[:12]
        res = equivalence_check(equivalent)
        L += ["", f"**--equivalent-commits 사용:** 태그 {TAG} ({base12}) 와 같은 것으로 볼 커밋 {', '.join(equivalent)}", "",
              "| 커밋 | 검사 | 결과 |", "|---|---|---|"]
        L += [f"| {c} | {'O' if ok else 'X'} | {why} |" for c, ok, why in res]
        problems += sum(not ok for _, ok, _ in res)
        alias = {base12} | {_git("rev-parse", f"{c}^{{commit}}").strip()[:12] for c, ok, _ in res if ok}
        commit_kinds = {base12 if k in alias else k for k in commit_kinds}
        L += ["", f"code_commit 은 원래 값 그대로 합친 파일에 남긴다. 검사용으로만 {', '.join(sorted(alias))} 를 한 종류로 센다.", ""]
    keys = C.Counter(tuple(r[k] for k in run_bt.KEY) for _, r in rows)
    dup = [k for k, v in keys.items() if v > 1]
    missing = expected - set(keys)
    extra = set(keys) - expected
    issues = [("중복 경기", len(dup)), ("누락 경기", len(missing)), ("계획 밖 경기", len(extra)),
              ("code_commit 종류" + (" (동등 커밋 묶음 뒤)" if equivalent else ""), len(commit_kinds)),
              ("engine_sha 종류", len({r["engine_sha"] for _, r in rows})),
              ("opponent_set 종류", len({r["opponent_set"] for _, r in rows})),
              ("wall_clock", sum(r["end_reason"] == "wall_clock" for _, r in rows)),
              ("disqualified", sum(r["end_reason"] == "disqualified" for _, r in rows))]
    L += ["", f"계획 경기 {len(expected)}, 입력 경기 {len(rows)}", "", "| 검사 | 값 | 판정 |", "|---|---|---|"]
    for name, v in issues:
        ok = v == 1 if "종류" in name else v == 0
        if name == "opponent_set 종류":
            ok = ok and {r["opponent_set"] for _, r in rows} == {opponent_set}
        problems += not ok
        L.append(f"| {name} | {v} | {'O' if ok else 'X'} |")
    for name, ks in (("중복", dup), ("누락", sorted(missing)), ("계획 밖", sorted(extra))):
        if ks:
            L += ["", f"{name} 예 (앞 5개): " + "; ".join("/".join(k) for k in list(ks)[:5])]
    return [r for _, r in rows], L, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("thetas")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--prefix", required=True, choices=run_bt.PREFIXES)
    ap.add_argument("--opponents", default=run_bt.DEFAULT_SET, choices=list(run_bt.OPPONENT_SETS))
    ap.add_argument("--r0", action="store_true")
    ap.add_argument("--nseeds", type=int, default=run_bt.SEEDS)
    ap.add_argument("--out", required=True, help="합친 games.csv (이미 있으면 덮어쓰지 않는다)")
    ap.add_argument("--report", help="보고서 경로 (기본 <out>.merge_report.md)")
    ap.add_argument("--equivalent-commits", nargs="+", default=[],
                    help=f"태그 {TAG} 커밋과 같은 것으로 볼 커밋 (영향 파일을 안 건드린 것만 통과)")
    a = ap.parse_args()
    if os.path.exists(a.out):
        sys.exit(f"{a.out} 가 이미 있다. 덮어쓰지 않는다")
    rows, L, problems = check(a.inputs, a.thetas, a.prefix, a.r0, a.opponents, a.nseeds, a.equivalent_commits)
    L = ["# merge 보고서", "", f"θ 목록 `{a.thetas}`, 접두어 {a.prefix}, 상대 묶음 {a.opponents}", ""] + L
    L += ["", f"**{'합침: ' + a.out if not problems else f'문제 {problems}건 — 합치지 않음'}**"]
    if not problems:
        order = {k: i for i, k in enumerate(tuple(str(j[k]) for k in run_bt.KEY) for j in run_bt.build_jobs(
            run_bt.read_thetas(a.thetas, a.r0), a.prefix, a.r0, a.opponents, a.nseeds))}
        rows.sort(key=lambda r: order[tuple(r[k] for k in run_bt.KEY)])     # build_jobs 순서로 정렬
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=run_bt.FIELDS)
            w.writeheader()
            w.writerows(rows)
    with open(a.report or a.out + ".merge_report.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
