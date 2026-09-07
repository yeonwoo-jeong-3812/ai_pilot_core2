"""뷰어 자동 실행 — 서버가 안 떠 있으면 띄우고, 해당 리플레이를 브라우저로 연다.

`scripts/run_match.py --view` 가 매치 직후 부르는 진입점이고, 손으로도 쓸 수 있다:

    python tools/acmi_viewer/launch.py replays/canon/xxx/yyy.acmi [--t 40]

서버는 한 번만 뜬다(포트를 이미 물고 있으면 그걸 재사용). 매치를 여러 번 돌려도
탭만 새로 열릴 뿐 서버가 중복 기동하지 않는다.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_PORT = 7900


def _listening(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def ensure_server(port: int = DEFAULT_PORT, host: str = "127.0.0.1",
                  replays: Path | None = None, timeout_s: float = 15.0) -> bool:
    """서버가 응답하면 True. 안 떠 있으면 백그라운드로 띄우고 기다린다."""
    if _listening(host, port):
        return True
    cmd = [sys.executable, str(HERE / "server.py"), "--port", str(port), "--host", host]
    if replays is not None:
        cmd += ["--replays", str(replays)]
    # 부모(매치 스크립트)가 끝나도 살아 있어야 브라우저에서 계속 볼 수 있다.
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, cwd=str(ROOT), **kwargs)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _listening(host, port):
            return True
        time.sleep(0.25)
    return False


def _open(url: str) -> None:
    """크롬 우선, 없으면 기본 브라우저."""
    try:
        webbrowser.get("chrome").open(url)
    except webbrowser.Error:
        webbrowser.open(url)


def open_replay(acmi_path: str | Path, port: int = DEFAULT_PORT,
                t: float | None = None, skin: str | None = None) -> str | None:
    """녹화 하나를 뷰어로 연다. 열었으면 URL, 못 열었으면 None(사유는 stderr)."""
    acmi = Path(acmi_path).resolve()
    replays = (ROOT / "replays").resolve()
    try:
        rel = acmi.relative_to(replays).as_posix()
    except ValueError:
        # 서버는 replays/ 아래만 서빙한다 — 밖의 파일은 그 폴더를 루트로 띄워야 한다.
        print(f"  [뷰어] {acmi} 가 {replays} 밖이라 열 수 없습니다.", file=sys.stderr)
        return None
    if not acmi.is_file():
        print(f"  [뷰어] 녹화가 없습니다: {acmi}", file=sys.stderr)
        return None
    if not ensure_server(port):
        print(f"  [뷰어] 서버 기동 실패 (포트 {port})", file=sys.stderr)
        return None
    url = f"http://127.0.0.1:{port}/?replay={quote(rel)}"
    if t is not None:
        url += f"&t={t:g}"
    if skin:
        url += f"&skin={skin}"
    _open(url)
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description="ACMI 뷰어로 리플레이 열기")
    ap.add_argument("acmi", help="replays/ 아래의 .acmi 경로")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--t", type=float, default=None, help="열자마자 점프할 시각 [s]")
    ap.add_argument("--skin", default=None, choices=["real"],
                    help="real = 원본 F-16 도장(청/적 구분은 사라짐)")
    a = ap.parse_args()
    url = open_replay(a.acmi, port=a.port, t=a.t, skin=a.skin)
    if url:
        print(url)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
