"""ACMI 브라우저 뷰어 로컬 서버 — 정적 파일 + replays/ 목록·파일 서빙.

실행 (repo 루트 기준):
    python tools/acmi_viewer/server.py [--replays replays] [--port 7900]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# Windows 레지스트리가 .js를 text/plain으로 돌려줘 ES 모듈 로드가 거부됨 → 강제 등록
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("model/gltf+json", ".gltf")  # F-16 기체 모델 (static/models/)
mimetypes.add_type("application/octet-stream", ".bin")

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_REPLAYS = Path(__file__).resolve().parents[2] / "replays"


def _safe_child(root: Path, relative: str) -> Path | None:
    """root 내부의 파일 경로만 허용 (경로 탈출 차단)."""
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def make_handler(replays_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path == "/api/replays":
                # 하위 폴더까지 훑는다 — 녹화가 세대별 폴더(canon/…, archive/…)로
                # 정리돼 있어 최상위만 보면 목록이 비어 보이던 결함 수정.
                # 항목은 replays/ 기준 상대경로(슬래시)로 내보내 그대로 요청 가능.
                files = sorted(
                    (p.relative_to(replays_dir).as_posix()
                     for p in replays_dir.rglob("*.acmi")), reverse=True
                )
                self._send(
                    json.dumps({"replays": list(files)}).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
            elif path.startswith("/replays/"):
                self._send_file(replays_dir, path[len("/replays/"):])
            else:
                if path == "/":
                    path = "/index.html"
                self._send_file(STATIC_DIR, path.lstrip("/"))

        def _send_file(self, root: Path, relative: str) -> None:
            file_path = _safe_child(root, relative)
            if file_path is None:
                self.send_error(404)
                return
            mime, _ = mimetypes.guess_type(str(file_path))
            self._send(file_path.read_bytes(), mime or "application/octet-stream")

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _open_browser(url: str) -> None:
    """크롬 우선, 없으면 기본 브라우저. 헤드리스 등 실패해도 서버는 계속 돈다."""
    import webbrowser
    try:
        webbrowser.get("chrome").open(url)
    except webbrowser.Error:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="ACMI browser viewer server")
    parser.add_argument("--replays", default=str(DEFAULT_REPLAYS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7900)
    # 기본으로 브라우저를 연다 — 대부분 바로 보려고 띄운다. 열기 싫으면 --no-open
    # (헤드리스·원격에서 유용). 이미 그 포트에 서버가 있으면 새로 안 띄우고 탭만 연다.
    parser.add_argument("--no-open", action="store_true",
                        help="브라우저 자동 열기 끄기")
    args = parser.parse_args()

    replays_dir = Path(args.replays).expanduser().resolve()
    url = f"http://{args.host}:{args.port}"

    # 이미 그 포트에 서버가 떠 있으면(내가 아까 띄웠거나 다른 창) 새로 바인딩하지 않고
    # 브라우저 탭만 연다 — "주소가 이미 사용 중" 에러 대신 그냥 열리는 게 자연스럽다.
    import socket
    with socket.socket() as probe:
        probe.settimeout(0.3)
        if probe.connect_ex((args.host, args.port)) == 0:
            print(f"이미 실행 중 — 브라우저만 엽니다: {url}")
            if not args.no_open:
                _open_browser(url)
            return

    server = ThreadingHTTPServer(
        (args.host, args.port), make_handler(replays_dir)
    )
    print(f"ACMI viewer: {url}")
    print(f"Replays dir: {replays_dir}")
    if not args.no_open:
        # 서버가 요청을 받을 수 있게 된 뒤 살짝 지연시켜 연다(즉시 열면 간혹 첫
        # 요청이 바인딩 전에 떨어진다). 서버는 아래 serve_forever 가 돌린다.
        import threading
        threading.Timer(0.4, _open_browser, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
