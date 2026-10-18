"""로그인할 때 본실험을 자동으로 이어 가는 실행기 (Windows 시작프로그램에서 부른다).

  python resume.py            # 돌고 있는 실험이 없으면 남은 단계를 이어서 띄운다
  python resume.py --dry      # 무엇을 할지 보여 주기만 한다
  python resume.py --install  # 시작프로그램에 등록한다
  python resume.py --remove   # 시작프로그램에서 뺀다
  python resume.py --after <pid>  # 그 파이프라인이 끝나기를 기다렸다가, 본실험이 다 끝났으면 정리한다

- run.py 나 pipeline.py 가 이미 돌고 있으면 아무것도 하지 않는다 (같은 games.csv 에 두 번 쓰지 않도록).
- 띄우는 단계는 E2 이후 전체다. 끝난 run 단계는 기록된 판을 건너뛰어 바로 끝나고, predict 는 같은 원자료로
  같은 결과를 다시 쓴다. 관문(gate:E2)에서 멈춘 적이 있으면 다시 멈춘다.
- out_pipeline.log 에 "파이프라인 완료 ... predict:E4" 가 있으면 할 일이 없으므로 정리한다: 시작프로그램에서
  빠지고, 무인 실행 때문에 바꾼 덮개 닫기 동작(전원 연결 시)을 원래 값 "절전"으로 되돌린다.
"""
import os
import subprocess
import sys
import time

KIT = os.path.dirname(os.path.abspath(__file__))
STEPS = "run:E2 predict:E2 gate:E2 run:E3 predict:E3 run:E4 predict:E4"
PROCS = 14
STARTUP = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup",
                       "cadet_research_resume.cmd")
PY = os.path.join(os.path.dirname(sys.executable), "python.exe")
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
NO_WINDOW = 0x08000000


def log(msg):
    with open(os.path.join(KIT, "out_pipeline.log"), "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] resume: {msg}\n")


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW).stdout


def running():
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
             "Where-Object { $_.CommandLine -match 'pipeline\\.py|run\\.py' } | "
             "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }")
    return [s for s in out.splitlines() if s.strip()]


def finished():
    path = os.path.join(KIT, "out_pipeline.log")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        return any("파이프라인 완료" in s and "predict:E4" in s for s in f)


def install():
    with open(STARTUP, "w", encoding="utf-8") as f:
        f.write(f'@start "" "{PYW}" "{os.path.abspath(__file__)}"\n')
    print("등록:", STARTUP)


def remove():
    if os.path.isfile(STARTUP):
        os.remove(STARTUP)
        print("삭제:", STARTUP)


LID = "4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936"   # SUB_BUTTONS LIDACTION
LID_ORIGINAL_AC = 1                                                                    # 절전 (2026-10-16 바꾸기 전 값)


def restore_lid():
    subprocess.run(f"powercfg /setacvalueindex SCHEME_CURRENT {LID} {LID_ORIGINAL_AC}", creationflags=NO_WINDOW)
    subprocess.run("powercfg /setactive SCHEME_CURRENT", creationflags=NO_WINDOW)
    import re
    out = subprocess.run(f"powercfg /qh SCHEME_CURRENT {LID}", capture_output=True,
                         creationflags=NO_WINDOW).stdout.decode("ascii", "ignore")
    v = re.findall(r"0x[0-9a-fA-F]+", out)[-2:]      # 마지막 두 값 = 현재 AC, DC 색인
    return f"AC {v[0]}, DC {v[1]}" if len(v) == 2 else "확인 실패"


def wait_pid(pid):
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if h:
        k32.WaitForSingleObject(h, 0xFFFFFFFF)
        k32.CloseHandle(h)


def main():
    dry = "--dry" in sys.argv
    if "--install" in sys.argv:
        return install()
    if "--remove" in sys.argv:
        return remove()
    if "--after" in sys.argv:
        pid = int(sys.argv[sys.argv.index("--after") + 1])
        log(f"pid {pid} 이 끝나면 정리 여부를 본다")
        wait_pid(pid)
        if not finished():
            log(f"pid {pid} 끝남. 본실험이 아직 안 끝났으므로 정리하지 않는다")
            return
    if finished():
        print("본실험 전체 완료. 시작프로그램에서 빼고 덮개 설정을 되돌린다")
        if not dry:
            remove()
            log(f"본실험 전체 완료 → 시작프로그램에서 뺐음, 덮개 닫기 동작 되돌림 ({restore_lid()})")
        return
    now = running()
    if now:
        print("이미 돌고 있다. 아무것도 하지 않는다:\n  " + "\n  ".join(now))
        if not dry:
            log(f"이미 돌고 있음 (pid {', '.join(s.split()[0] for s in now)}) → 아무것도 하지 않음")
        return
    cmd = f'"{PY}" "{os.path.join(KIT, "pipeline.py")}" {PROCS} {STEPS}'
    print("띄울 명령:", cmd)
    if dry:
        return
    log("돌고 있는 실험이 없음 → 이어서 띄움")
    out = ps("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
             f"@{{CommandLine='{cmd}'; CurrentDirectory='{KIT}'}}; \"$($r.ReturnValue) $($r.ProcessId)\"")
    log(f"Win32_Process.Create 결과 (코드 pid): {out.strip()}")
    print(out.strip())


if __name__ == "__main__":
    main()
