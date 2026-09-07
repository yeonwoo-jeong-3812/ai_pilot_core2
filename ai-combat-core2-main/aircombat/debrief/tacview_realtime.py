"""L5 실시간 Tacview 텔레메트리 서버 (TCP:42674).

Tacview Advanced → Record → Real-time Telemetry 로 접속. 멀티 클라이언트.
핸드셰이크(XtraLib.Stream.0 / RealTimeTelemetry.0) 후 ACMI 헤더 + 프레임 스트림.
읽기전용 tap(D5) — 제어 루프와 분리, 전송 실패는 해당 클라만 드롭.

프레임 포맷은 acmi.format_frame 을 공유(파일과 동일 규약).
"""
from __future__ import annotations

import socket
import threading

from .acmi import ACMIObject, format_header, format_frame

TACVIEW_PORT = 42674
_HANDSHAKE = "XtraLib.Stream.0\nTacview.RealTimeTelemetry.0\naicombat-core2\n\x00"


class TacviewRealtimeServer:
    """비침습 실시간 중계 서버. start()→send_frame()*→stop()."""

    def __init__(self, port: int = TACVIEW_PORT, host: str = "0.0.0.0",
                 title: str = "ai-combat-core2"):
        self.port = port
        self.host = host
        self.title = title
        self._srv: socket.socket | None = None
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._accept_thread: threading.Thread | None = None
        self._running = False

    def start(self) -> "TacviewRealtimeServer":
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.host, self.port))
        self.port = self._srv.getsockname()[1]   # port=0 이면 실제 할당 포트 반영
        self._srv.listen(5)
        self._srv.settimeout(0.5)
        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        return self

    def _accept_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            try:
                self._handshake(conn)
            except OSError:
                conn.close()
                continue
            with self._lock:
                self._clients.append(conn)

    def _handshake(self, conn: socket.socket) -> None:
        conn.sendall(_HANDSHAKE.encode())
        conn.settimeout(2.0)
        try:
            conn.recv(1024)                       # 클라 식별 문자열(무시)
        except socket.timeout:
            pass
        # 송신 타임아웃 — 느리거나 멈춘 관전자가 경기(제어 루프)를 붙잡지 못하게.
        # 초과 시 send_frame 의 OSError 경로로 해당 클라만 드롭 (D5: 중계는 무해).
        conn.settimeout(1.0)
        conn.sendall(format_header(title=self.title).encode())

    def send_frame(self, sim_time: float, objects: list[ACMIObject]) -> None:
        """모든 클라에 한 프레임 전송(실시간은 매 프레임 재선언)."""
        data = format_frame(sim_time, objects, declared=None).encode()
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(data)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
                try:
                    c.close()
                except OSError:
                    pass

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def stop(self) -> None:
        self._running = False
        if self._accept_thread:
            self._accept_thread.join(timeout=1.0)
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._srv:
            self._srv.close()
            self._srv = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
