"""본실험 단계를 순서대로 잇는 실행기. run.py·predict.py 를 그대로 부른다(엔진·분석 코드는 건드리지 않는다).

  python pipeline.py 14 run:E1 predict:E1 run:E2
  python pipeline.py 14 run:E3 predict:E3 run:E4 predict:E4

- 대화 세션과 분리해 돌릴 수 있다. 끊기거나 꺼지면 같은 명령을 다시 치면 이어서 돈다.
- 갑자기 꺼져 games.csv 마지막 줄이 잘렸으면 그 줄을 지우고 이어 간다 (그 판만 다시 돈다).
- 실행 중에는 Windows 절전을 막는다 (끝나면 원래대로).
- 단계마다 로그: out_<단계>.log. 전체 경과: out_pipeline.log. 한 단계가 실패하면 거기서 멈춘다.

특수 단계
  wait:<pid>  그 프로세스(앞서 띄운 파이프라인)가 끝날 때까지 기다린다
  gate:E2     등록된 E2 곡선의 D 기울기가 0 이하이면 멈춘다. 계획서 §6 "단조 관계가 없으면 RQ2·RQ3 를
              하지 않는다"를 지키려는 운영용 관문이다. 논문의 RQ1 판단은 E2 보고서를 보고 사람이 한다
"""
import ctypes
import json
import os
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.abspath(__file__))
SALT = {"E1": "cal", "E2": "main", "E3": "main", "E4": "gen"}
JUNK = ("Engine location ignored", "Engine orientation ignored", "JSBSim", "[JSBSim-ML")


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(os.path.join(KIT, "out_pipeline.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def repair_tail(exp):
    """마지막 줄이 줄바꿈 없이 끝났으면(쓰다 꺼짐) 그 줄을 잘라낸다."""
    path = os.path.join(KIT, "out", SALT[exp], "games.csv")
    if not os.path.isfile(path):
        return
    with open(path, "rb+") as f:
        data = f.read()
        if data and not data.endswith(b"\n"):
            cut = data.rfind(b"\n") + 1
            f.seek(cut)
            f.truncate()
            log(f"{path}: 잘린 마지막 줄 {len(data) - cut}바이트 제거")


def wait_pid(pid):
    SYNCHRONIZE, INFINITE = 0x00100000, 0xFFFFFFFF
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        log(f"pid {pid} 없음 (이미 끝남)")
        return 0
    log(f"pid {pid} 끝나기를 기다림")
    k32.WaitForSingleObject(h, INFINITE)
    k32.CloseHandle(h)
    log(f"pid {pid} 끝남")
    return 0


def gate_e2():
    with open(os.path.join(KIT, "out", SALT["E2"], "curve.json"), encoding="utf-8") as f:
        c = json.load(f)
    a, b = c["curve"]["D"]
    ok = b > 0
    log(f"관문 E2: D = {a:.3f} + {b:.4f}·{c['shape']}(mae) → {'통과' if ok else '기울기 ≤ 0, 멈춤'}")
    return 0 if ok else 1


def step(kind, exp, procs):
    if kind == "wait":
        return wait_pid(int(exp))
    if kind == "gate":
        return gate_e2()
    cmd = [sys.executable, "run.py", exp, "--procs", str(procs)] if kind == "run" else \
          [sys.executable, "predict.py", exp]
    if kind == "run":
        repair_tail(exp)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    log(f"시작 {' '.join(cmd[1:])}")
    with open(os.path.join(KIT, f"out_{exp}.log"), "a", encoding="utf-8") as lf:
        lf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(cmd[1:])}\n")
        p = subprocess.Popen(cmd, cwd=KIT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for raw in p.stdout:
            s = raw.decode("utf-8", "replace").rstrip()
            if s.strip() and not s.lstrip().startswith(JUNK):
                lf.write(s + "\n"); lf.flush()
        rc = p.wait()
    log(f"{'끝' if rc == 0 else '실패'} {' '.join(cmd[1:])} (종료 코드 {rc})")
    return rc


def main():
    procs, steps = int(sys.argv[1]), sys.argv[2:]
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    log(f"파이프라인 시작 (procs {procs}): {' '.join(steps)}  pid {os.getpid()}")
    for s in steps:
        kind, exp = s.split(":")
        if step(kind, exp, procs) != 0:
            log("파이프라인 중단")
            sys.exit(1)
    log("파이프라인 완료: " + " ".join(steps))


if __name__ == "__main__":
    main()
