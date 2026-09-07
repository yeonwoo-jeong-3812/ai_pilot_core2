"""L5 ACMI 회귀 — 파일 writer 포맷 + 실시간 서버 핸드셰이크/프레임 스모크."""
import os
import socket
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from aircombat.debrief.acmi import (
    ACMIWriter, ACMIObject, combat_attrs, control_attrs, flight_attrs, format_frame,
    format_header,
)
from aircombat.debrief.tacview_realtime import TacviewRealtimeServer


def _obj(t_attrs=None):
    return ACMIObject(100, 127.0, 37.0, 3000.0, 10.0, 5.0, 180.0,
                      attrs=t_attrs or {"Health": "100.0"})


class TestACMIFile(unittest.TestCase):
    def test_write_and_parse(self):
        fd, path = tempfile.mkstemp(suffix=".acmi")
        os.close(fd)
        try:
            with ACMIWriter(path, title="test") as w:
                w.frame(0.0, [_obj(combat_attrs(2000.0, 10.0, 20.0, 5.0, 74.0, 120.0, 95.0,
                                                in_wez=True, tactic="gun_track",
                                                pursuit="lag", g_burst=0.8, dphi_deg=23.4,
                                                g_avail=8.1, limited="Q",
                                                lead_time=1.5, lag_dist=2000.0))])
                w.frame(0.03, [_obj({"Health": "90.0"})])
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        finally:
            os.remove(path)

        self.assertIn("FileType=text/acmi/tacview", text)
        self.assertIn("FileVersion=2.2", text)
        self.assertIn("#0.00", text)
        self.assertIn("#0.03", text)
        self.assertIn("T=127.0000000|37.0000000|3000.0|10.0|5.0|180.0", text)
        self.assertIn("ATA=10.0", text)
        self.assertIn("RollOff=74.0", text)             # BFM 기하
        self.assertIn("ClosureRate=120.0", text)
        # 결정은 계층당 문자열로 패킹 (측정 Gavail 등은 개별 numeric 유지)
        self.assertIn("L1=node=gun_track pursuit=lag burst=0.80", text)   # L1 전술
        self.assertIn("L2=dphi=23.4 lead=1.50 lag=2000", text)        # L2 가이드(조준 기하)
        self.assertIn("L3=lim=Q", text)                              # L3 포화 축
        self.assertIn("Gavail=8.10", text)              # 측정 = numeric 유지(그래프)
        self.assertEqual(text.count("Name=F-16"), 1)    # 정적 속성 1회만 선언

    def test_flight_control_coalition_attrs(self):
        # tacview-addons 완전 호환 속성: HDG/CAS + 조종입력·서보 + Coalition/CallSign.
        o = ACMIObject(100, 127.0, 37.0, 3000.0, 0.0, 0.0, 0.0,
                       coalition="Allies", callsign="blue_1")
        o.attrs = {**flight_attrs(270.0, 350.0),
                   **control_attrs(0.85, 0.10, -0.20, 0.0, 0.5, -0.3, 0.0)}
        s = format_frame(0.0, [o], declared=set())
        # CAS: 입력 350 kts → 기록 m/s (350 × 0.514444 = 180.06, ACMI 스펙 단위)
        for token in ("Coalition=Allies", "CallSign=blue_1", "HDG=270.00", "CAS=180.06",
                      "Throttle=0.850", "RollControlInput=0.100",
                      "RollControlPosition=0.5000", "PitchControlPosition=-0.3000"):
            self.assertIn(token, s)

    def test_header_comments_identify_match(self):
        # 리플레이가 뒤섞였다는 신고를 파일만 열어 판정하려면 헤더가 교전을 식별해야 한다.
        meta = "match=31050aaf;scenario=perch_defense;seed=991164887"
        self.assertIn(f"0,Comments={meta}\n", format_header(comments=meta))
        # 없으면 줄 자체가 없다 (구 파일·실시간 중계와 동일한 헤더 유지)
        self.assertNotIn("Comments", format_header())

    def test_realtime_frame_redeclares(self):
        # 실시간(declared=None)은 매 프레임 Name 재선언.
        s = format_frame(0.0, [_obj()], declared=None)
        self.assertIn("Name=F-16", s)
        s2 = format_frame(0.03, [_obj()], declared=None)
        self.assertIn("Name=F-16", s2)


class TestRealtimeServer(unittest.TestCase):
    def test_handshake_and_stream(self):
        srv = TacviewRealtimeServer(port=0, host="127.0.0.1").start()
        try:
            cli = socket.create_connection(("127.0.0.1", srv.port), timeout=2.0)
            cli.settimeout(2.0)
            handshake = cli.recv(1024).decode("utf-8", errors="ignore")
            self.assertIn("Tacview.RealTimeTelemetry.0", handshake)
            cli.sendall(b"pytest-client\n\x00")
            header = cli.recv(4096).decode("utf-8", errors="ignore")
            self.assertIn("FileType=text/acmi/tacview", header)

            for _ in range(100):                        # 클라 등록 대기
                if srv.client_count >= 1:
                    break
                time.sleep(0.02)
            self.assertEqual(srv.client_count, 1)

            srv.send_frame(0.0, [_obj()])
            frame = cli.recv(4096).decode("utf-8", errors="ignore")
            self.assertIn("T=127", frame)
            self.assertIn("Name=F-16", frame)
            cli.close()
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
