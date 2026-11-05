"""PC3 (주혁) 본실험 자동 시작기 — TASK_RUN.md 절차를 그대로 따른다. 저장소 파일은 하나도 고치지 않는다.

1) 태그 prereg-bt-v1 이 생길 때까지 10분마다 git fetch --tags 로 확인 (TASK_RUN §0)
2) 태그가 생기면 git pull --ff-only origin bt-study → HEAD 가 태그 커밋과 다르면 멈춤 (연우에게 확인)
3) test_bt.py 통과 · --dry 경기 수 (LHS 1,024 / Morris 3,072) 확인
4) LHS → Morris 순서로 --shard 3/3 실행. 실행 중 disqualified 가 나오면 즉시 중단 (PREREG §7)
   LHS 에서 wall_clock 이 나오면 Morris 는 --procs 를 하나 줄여 돈다 (TASK_RUN §1-7). wall_clock 줄 삭제는 연우 몫.
5) 끝나면 crosscheck 출력·python --version·실행 기록을 report_PC3.md 로 정리하고 알림창을 띄운다.

시험용: python watch_and_run.py --test  (bt-smoke 접두어, 태그·pull 건너뜀, 각 설계 14경기만)
"""
import ctypes, datetime as dt, os, re, subprocess, sys, time, csv

REPO = r"C:\Users\User\ai_pilot_core2"
KIT = os.path.join(REPO, "cadet_research", "kit")
PY = r"C:\Users\User\venv-bt311\Scripts\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
TAG, SHARD, PROCS, POLL_S = "prereg-bt-v1", "3/3", 14, 600
DESIGNS = [("main_lhs64", 1024), ("main_morris_r16", 3072)]
TEST = "--test" in sys.argv
PREFIX = "bt-smoke" if TEST else "bt-main"
LOG = os.path.join(HERE, "test_log.txt" if TEST else "run_log.txt")
STATUS = os.path.join(HERE, "STATUS.txt" if not TEST else "STATUS_test.txt")
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def status(msg):
    with open(STATUS, "w", encoding="utf-8") as f:
        f.write(f"{now()}  {msg}\n")
    log("STATUS: " + msg)


def sh(args, cwd=KIT, check=False):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    if check and r.returncode:
        raise RuntimeError(f"{args} 실패:\n{r.stdout}\n{r.stderr}")
    return r


def popup(title, text):
    if TEST:
        return
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40 | 0x40000)  # info + topmost
    except Exception:
        pass


def stop(msg):
    status("멈춤 — " + msg)
    popup("BT 본실험 PC3: 멈춤", msg + "\n\n자세한 내용: " + LOG)
    sys.exit(1)


def keep_awake():
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: 이 프로세스가 사는 동안 절전 진입을 막는다 (설정은 바꾸지 않음)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)


def wait_for_tag():
    status(f"태그 {TAG} 기다리는 중 ({POLL_S // 60}분마다 확인)")
    while True:
        r = sh(["git", "fetch", "--tags", "origin"], cwd=REPO)
        if r.returncode:
            log("git fetch 실패 (네트워크?) — 다음 주기에 다시: " + r.stderr.strip()[:200])
        elif sh(["git", "tag", "-l", TAG], cwd=REPO).stdout.strip() == TAG:
            log(f"태그 {TAG} 발견")
            return
        time.sleep(POLL_S)


def sync_to_tag():
    if sh(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO).stdout.strip():
        stop("저장소에 커밋 안 된 수정이 있다 (git status 확인)")
    r = sh(["git", "pull", "--ff-only", "origin", "bt-study"], cwd=REPO)
    log("git pull: " + (r.stdout + r.stderr).strip()[-300:])
    if r.returncode:
        stop("git pull --ff-only 실패")
    head = sh(["git", "rev-parse", "HEAD"], cwd=REPO, check=True).stdout.strip()
    tagc = sh(["git", "rev-parse", TAG + "^{commit}"], cwd=REPO, check=True).stdout.strip()
    log(f"HEAD {head[:12]}  태그 커밋 {tagc[:12]}")
    if head != tagc:
        stop(f"bt-study HEAD ({head[:12]}) 가 태그 커밋 ({tagc[:12]}) 과 다르다. 세 PC 의 code_commit 이 같아야 "
             f"merge 되므로, 어느 커밋으로 돌릴지 연우에게 확인한 뒤 다시 시작할 것")


def checks():
    r = sh([PY, "bt/test_bt.py"])
    last = (r.stdout.strip().splitlines() or [""])[-1]
    log("test_bt 마지막 줄: " + last)
    if "bt 자가점검 통과" not in last:
        stop("test_bt.py 실패:\n" + (r.stdout + r.stderr)[-1500:])
    for stem, want in DESIGNS:
        r = sh([PY, "bt/run_bt.py", f"bt/thetas/{stem}.csv", "--prefix", PREFIX, "--unlock-confirm",
                "--shard", SHARD, "--procs", str(PROCS), "--dry"])
        m = re.search(r"전체 (\d+)경기", r.stdout)
        log(f"--dry {stem}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]}")
        if not m or int(m.group(1)) != want:
            stop(f"{stem} --dry 경기 수가 {want} 가 아니다")


def count_bad(path):
    if not os.path.isfile(path):
        return 0, 0, 0
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return len(rows), sum(r["end_reason"] == "wall_clock" for r in rows), sum(r["end_reason"] == "disqualified" for r in rows)


def run_design(stem, procs):
    i, n = SHARD.split("/")
    out = os.path.join(KIT, "bt", "out", PREFIX, f"games_{stem}_shard{i}of{n}.csv")
    cmd = [PY, "bt/run_bt.py", f"bt/thetas/{stem}.csv", "--prefix", PREFIX, "--unlock-confirm",
           "--shard", SHARD, "--procs", str(procs)]
    if TEST:
        cmd += ["--limit", "14"]
    t0 = now()
    status(f"{stem} 실행 중 (--procs {procs}) 시작 {t0}")
    log("명령: " + " ".join(cmd[1:]))
    out_log = open(os.path.join(HERE, f"{'test_' if TEST else ''}{stem}_stdout.txt"), "a", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=KIT, stdout=out_log, stderr=subprocess.STDOUT, env=ENV)
    while p.poll() is None:
        time.sleep(30)
        n_rows, _, n_dq = count_bad(out)
        if n_dq:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            stop(f"{stem}: disqualified {n_dq}경기 발생 → 실행 중단 (PREREG §7). 연우에게 알릴 것")
    out_log.close()
    n_rows, n_wall, n_dq = count_bad(out)
    t1 = now()
    log(f"{stem} 끝 (종료코드 {p.returncode}): 기록 {n_rows}경기, wall_clock {n_wall}, disqualified {n_dq}")
    if p.returncode:
        with open(out_log.name, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-1500:]
        stop(f"{stem} run_bt.py 가 종료코드 {p.returncode} 로 끝났다 (실행 거부 등):\n{tail}")
    if n_dq:
        stop(f"{stem}: disqualified {n_dq}경기 (PREREG §7)")
    return dict(stem=stem, procs=procs, start=t0, end=t1, rows=n_rows, wall=n_wall, dq=n_dq, path=out)


def report(results):
    cc = sh([PY, "bt/crosscheck.py"])
    cc_tail = "\n".join(cc.stdout.strip().splitlines()[-3:])
    pyv = sh([PY, "--version"]).stdout.strip()
    commit = sh(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO).stdout.strip()
    L = ["# PC3 (주혁) 본실험 실행 기록", "",
         f"- PC: PC3 주혁, shard {SHARD}, host {os.environ.get('COMPUTERNAME', '?')} (AMD Ryzen 7 4800H 8C/16T)",
         f"- code_commit: {commit}", f"- {pyv}", "", "## 실행 기록", "",
         "| 설계 | --procs | 시작 | 끝 | 경기 수 | wall_clock | disqualified | 파일 |", "|---|---|---|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['stem']} | {r['procs']} | {r['start']} | {r['end']} | {r['rows']} | {r['wall']} | {r['dq']} | "
                 f"`{os.path.relpath(r['path'], KIT)}` |")
    L += ["", "## crosscheck 출력 마지막 3줄", "", "```", cc_tail, "```", ""]
    if any(r["wall"] for r in results):
        L += ["**wall_clock 이 있다 → 연우에게 알리고 줄 삭제 지시를 기다린다 (TASK_RUN §4).**", ""]
    path = os.path.join(HERE, "test_report.md" if TEST else "report_PC3.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def main():
    keep_awake()
    log(f"=== 시작 (test={TEST}, prefix={PREFIX}, shard={SHARD}, procs={PROCS}) ===")
    if not TEST:
        wait_for_tag()
        sync_to_tag()
    status("자가점검·--dry 확인 중")
    checks()
    results, procs = [], PROCS
    for stem, _ in DESIGNS:
        r = run_design(stem, procs)
        results.append(r)
        if r["wall"]:
            procs = max(1, procs - 1)
            log(f"wall_clock {r['wall']}경기 → 다음 실행은 --procs {procs} (줄 삭제·재실행은 연우 지시 대기)")
    path = report(results)
    wall = sum(r["wall"] for r in results)
    msg = (f"완료. 결과 2개를 구글 드라이브 'BT논문/bt-main' 에 올릴 것.\n보고서: {path}" if not wall else
           f"완료했지만 wall_clock {wall}경기가 있다. 연우에게 알리고 지시를 기다릴 것.\n보고서: {path}")
    status(msg.splitlines()[0])
    popup("BT 본실험 PC3" + (" (시험)" if TEST else ""), msg)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        stop(f"예상 못 한 오류: {e!r}")
