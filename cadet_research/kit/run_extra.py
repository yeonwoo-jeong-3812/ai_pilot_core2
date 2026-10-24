"""본실험 뒤 추가 실험 실행기 (ASYM, E3X). 사전 등록은 ../PREREG_EXTRA.md.

  python run_extra.py            # ASYM → E3X 순서로 돈다. 끊기면 다시 치면 이어서 돈다
  python run_extra.py --dry      # 판 수만 센다
  python run_extra.py --install  # 로그인할 때 자동으로 이어 돌기 (다 끝나면 스스로 빠진다)
  python run_extra.py --remove

- run.py 는 고치지 않는다. 그 주입·기록(run.play)과 판 만들기(run.build_jobs)를 그대로 쓴다.
- 원자료 out/main 과 섞지 않고 out/<실험>/games.csv 에 쓴다. 짝이 되는 BASE 는 out/main 에 이미 있어서 돌리지 않는다.
- wall_clock(실시간 120초 안전장치)으로 끝난 판은 실행 인공물이다. 실험이 끝나면 지우고(wallclock_removed.csv 에 보관)
  한 번 다시 돈다.
- 로그: out_extra.log. 끝나면 "추가 실험 완료" 한 줄을 남긴다.
"""
import csv
import ctypes
import json
import os
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import run  # noqa: E402  (Pilot.setup 패치 포함)
from experiments import EXPERIMENTS  # noqa: E402

ORDER = ["ASYM", "E3X"]
PROCS = 14
LOG = os.path.join(KIT, "out_extra.log")
DONE_MARK = "추가 실험 완료"
STARTUP = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                       "cadet_research_extra.cmd")
NO_WINDOW = 0x08000000


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def jobs_of(name):
    exp = EXPERIMENTS[name]
    js = [j for j in run.build_jobs(exp, exp["salts"]) if j["cond"] != "BASE"]
    if exp.get("targets"):
        js = [j for j in js if j["target"] in exp["targets"]]
    return js


def path_of(name):
    return os.path.join(KIT, "out", EXPERIMENTS[name]["out"], "games.csv")


def read_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, "rb+") as f:                       # 쓰다 꺼져 잘린 마지막 줄 정리
        data = f.read()
        if data and not data.endswith(b"\n"):
            f.seek(data.rfind(b"\n") + 1); f.truncate()
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def play_all(name, todo, pool):
    path = path_of(name)
    new = not os.path.isfile(path)
    t0 = time.time()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(run.play, todo, chunksize=1), 1):
            w.writerow(row); f.flush()
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                log(f"  {name} {i}/{len(todo)}  {el:.0f}s 경과, 남은 예상 {el / i * (len(todo) - i):.0f}s")


def repair_wallclock(name, pool):
    path = path_of(name)
    rows = read_rows(path)
    bad = [r for r in rows if r["condition"] == "wall_clock"]
    if not bad:
        log(f"{name}: wall_clock 판 없음")
        return
    keep = [r for r in rows if r["condition"] != "wall_clock"]
    arch = os.path.join(os.path.dirname(path), "wallclock_removed.csv")
    with open(arch, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        if f.tell() == 0:
            w.writeheader()
        w.writerows(bad)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=run.FIELDS)
        w.writeheader(); w.writerows(keep)
    log(f"{name}: wall_clock {len(bad)}판을 지우고(wallclock_removed.csv 에 보관) 다시 돈다")
    agents = EXPERIMENTS[name]["agents"]
    todo = [dict({k: r[k] for k in ("cond", "target", "blue", "red", "scenario", "salt")},
                 blue_path=agents[r["blue"]], red_path=agents[r["red"]]) for r in bad]
    play_all(name, todo, pool)


def main_run(dry=False):
    import multiprocessing as mp
    plan = {}
    for name in ORDER:
        js = jobs_of(name)
        done = {run._key(r) for r in read_rows(path_of(name))}
        plan[name] = [j for j in js if run._key(j) not in done]
        log(f"{name}: 전체 {len(js)}판, 기록됨 {len(js) - len(plan[name])}, 남음 {len(plan[name])}")
    if dry:
        return
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # 실행 중 자동 절전 막기
    with open(os.path.join(KIT, "ENGINE_VERSION.txt"), encoding="utf-8") as f:
        engine = f.read()
    with mp.Pool(PROCS) as pool:
        for name in ORDER:
            os.makedirs(os.path.dirname(path_of(name)), exist_ok=True)
            with open(os.path.join(os.path.dirname(path_of(name)), f"manifest_{name}.json"), "w", encoding="utf-8") as f:
                json.dump({"exp": name, "jobs": len(jobs_of(name)), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                           "prereg": "PREREG_EXTRA.md", "engine": engine}, f, ensure_ascii=False, indent=1)
            if plan[name]:
                log(f"시작 {name} ({len(plan[name])}판)")
                play_all(name, plan[name], pool)
            repair_wallclock(name, pool)
    log(DONE_MARK)
    remove()


# ---------------------------------------------------------------- 자동 재개
def finished():
    return os.path.isfile(LOG) and any(DONE_MARK in s for s in open(LOG, encoding="utf-8"))


def running_elsewhere():
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
                          "Where-Object { $_.CommandLine -match 'run_extra\\.py' -and $_.CommandLine -notmatch '--resume' } | "
                          "ForEach-Object { $_.ProcessId }"],
                         capture_output=True, text=True, creationflags=NO_WINDOW).stdout.split()
    return [p for p in out if p.strip() and int(p) != os.getpid()]


def launch_detached():
    py = os.path.join(os.path.dirname(sys.executable), "python.exe")
    cmd = f'"{py}" "{os.path.abspath(__file__)}"'
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                          "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
                          f"@{{CommandLine='{cmd}'; CurrentDirectory='{KIT}'}}; \"$($r.ReturnValue) $($r.ProcessId)\""],
                         capture_output=True, text=True, creationflags=NO_WINDOW).stdout.strip()
    log(f"자동 재개: 띄움 (코드 pid) {out}")


def resume_if_idle():
    if finished():
        remove(); return
    if running_elsewhere():
        log("자동 재개: 이미 돌고 있음 → 아무것도 하지 않음"); return
    launch_detached()


def install():
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    with open(STARTUP, "w", encoding="utf-8") as f:
        f.write(f'@start "" "{pyw}" "{os.path.abspath(__file__)}" --resume\n')
    print("등록:", STARTUP)


def remove():
    if os.path.isfile(STARTUP):
        os.remove(STARTUP)
        log("시작프로그램 등록 삭제")


if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    elif "--remove" in sys.argv:
        remove()
    elif "--resume" in sys.argv:
        resume_if_idle()
    else:
        main_run(dry="--dry" in sys.argv)
