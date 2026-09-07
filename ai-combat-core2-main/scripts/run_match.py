"""1v1 매치 실행 — Pilot(Blue) vs 스크립트 적기 또는 Pilot(자가대전) → .acmi 산출.

**용도**: 단일 페어링 × 단일 시나리오 × 단일 시드 1경기 → ACMI 복기·디버깅·재현(현미경).

전체 5계층 체인 end-to-end: L1 BT → L2 교리 조절 → 쿼터니언 shim →
결합 리미터 → L3 INDI → L4 JSBSim, WEZ 판정·judge·ACMI 로깅.

사용례:
  python scripts/run_match.py                                   # 현행(스크립트 turn)
  python scripts/run_match.py --scenario headon \
      --blue examples/textbook_headon.yaml \
      --red  examples/starter.yaml                              # 자가대전
  python scripts/run_match.py --scenario perch \
      --blue config/tactics.yaml --red scripted:straight        # 오버슈트/요요 데모
"""
from __future__ import annotations
import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# agents/champion128 등 custom_module 트리를 로스터에 편입할 수 있는 리서치/디버깅 러너 —
# custom 은 기본 봉인이므로 여기서 명시 허용(명시 =0 은 setdefault 라 우선).
os.environ.setdefault("AICOMBAT_ALLOW_CUSTOM", "1")
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.opponents.scripted import ScriptedOpponent
from aircombat.engine.match import Match, OVERTIME_S
from aircombat.engine.scenarios import SCENARIOS, initial_conditions

KST = datetime.timezone(datetime.timedelta(hours=9))   # V1 replays 파일명 규약과 동일

SCRIPTED_MANEUVERS = ("turn", "straight", "extend", "break")


def _default_acmi_path(blue: str, red: str) -> str:
    """V1 규약: replays/{YYYYMMDD_HHMMSS}_{blue}_vs_{red}.acmi (KST)."""
    ts = datetime.datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    blue_name = os.path.splitext(os.path.basename(blue))[0]
    red_name = (red.split(":", 1)[1] if red.startswith("scripted:")
                else os.path.splitext(os.path.basename(red))[0])
    return os.path.join("replays", f"{ts}_{blue_name}_vs_{red_name}.acmi")


class _Tee:
    """stdout 을 터미널+로그 파일에 동시 기록 (print 만 대상 — JSBSim C++ 배너 등
    fd 직접 출력은 제외)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def _make_pilot(color: str, yaml_path: str, ic_side: dict):
    """YAML 전술 트리로 Pilot 생성 (factory 위임). 파일럿별 트리 별도 build."""
    policy, doctrine = load_policy(yaml_path)
    return make_pilot(color, ic_side, policy, doctrine)


def run_roster(args) -> int:
    """배치 모드 — --blue 트리를 로스터 전판에 채점. 각 줄 '<상대stem>/<내진영>'."""
    text = open(args.roster, encoding="utf-8").read()
    slots = [s.strip() for chunk in text.splitlines()
             for s in chunk.split(",") if s.strip() and not s.strip().startswith("#")]
    # 녹화는 기본 저장 (끄려면 --no-acmi). 폴더 미지정 시 일시로 새 폴더 — 덮어쓰기 방지.
    if not args.no_acmi and args.acmi_dir is None:
        args.acmi_dir = os.path.join(
            "replays", "roster_" + datetime.datetime.now(KST).strftime("%Y%m%d_%H%M%S"))
    if args.no_acmi:
        args.acmi_dir = None
    ic = initial_conditions(args.scenario, range_nm=args.range_nm, seed=args.seed)
    w = d = l = 0
    fails = []
    print(f"{'상대/내진영':<34}{'결과':>4}{'HPΔ':>8}  종료")
    for slot in slots:
        stem, side = slot.rsplit("/", 1)
        # 경로-슬롯: stem 에 폴더가 있으면 저장소-상대 경로로 해석 —
        # 커스텀 모듈이 딸린 트리(예: agents/champion128)를 복사 없이 로스터에 편입.
        opp = (stem + ".yaml" if "/" in stem
               else os.path.join(args.opponents_dir, stem + ".yaml"))
        me_yaml, opp_yaml = args.blue, opp
        blue_y, red_y = (me_yaml, opp_yaml) if side == "blue" else (opp_yaml, me_yaml)
        blue = _make_pilot("Blue", blue_y, ic["blue"])
        red = _make_pilot("Red", red_y, ic["red"])
        acmi = (os.path.join(args.acmi_dir,
                             f"vs_{stem.replace('/', '__')}_{side}.acmi")
                if args.acmi_dir else None)
        if acmi:
            os.makedirs(args.acmi_dir, exist_ok=True)
        m = Match(blue, red, duration_s=args.duration, acmi_path=acmi,
                  log_hz=120.0, wall_limit_s=3600.0)
        res = m.run()
        hp_me = res.hp_blue if side == "blue" else res.hp_red
        hp_op = res.hp_red if side == "blue" else res.hp_blue
        if res.winner == "draw" or hp_me == hp_op:
            tag = "무"; d += 1
        elif (res.winner == side) or hp_me > hp_op:
            tag = "승"; w += 1
        else:
            tag = "패"; l += 1; fails.append(slot)
        print(f"{slot:<34}{tag:>4}{hp_me-hp_op:>+8.1f}  {res.condition}@{res.time_s:.0f}s",
              flush=True)
    print(f"\n합계: {w}승 {d}무 {l}패 / {len(slots)}")
    if fails:
        print("패배:", fails)
    return 0 if l == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=300.0)   # 룰북 교전 시간 (D1)
    ap.add_argument("--overtime", action="store_true",
                    help="오버타임 연습 모드 — 정규 시간에 승자가 없으면 120초 연장. "
                         "OT 에서는 WEZ 가 완화되고(6,000ft/45°) 조건 in_overtime 이 참이 된다. "
                         "대회에서는 현장 단판(준결승·결승)에만 적용된다.")
    ap.add_argument("--blue", default="config/tactics.yaml",
                    help="Blue 전술 트리 YAML")
    ap.add_argument("--red", default="scripted:turn",
                    help="Red: 전술 트리 YAML 경로(자가대전) 또는 "
                         f"scripted:{{{'|'.join(SCRIPTED_MANEUVERS)}}}")
    ap.add_argument("--scenario", default="headon",
                    choices=list(SCENARIOS) + ["perch"],
                    help="BEM 국면: headon=HABFM, perch_offense=OBFM, "
                         "perch_defense=DBFM, neutral=중립 머지 "
                         "(perch 는 perch_offense 별칭)")
    ap.add_argument("--seed", type=int, default=None,
                    help="초기조건 결정론 지터 시드 (미지정 = 기준 IC)")
    ap.add_argument("--range-nm", type=float, default=6.0,
                    help="headon 초기 분리거리 [NM]")
    ap.add_argument("--acmi", default=None,
                    help="출력 .acmi 경로 (기본: replays/{일시}_{blue}_vs_{red}.acmi)")
    ap.add_argument("--analyze", action="store_true",
                    help="매치 후 analyze_wez.py 자동 실행 (WEZ·에너지 그래프)")
    ap.add_argument("--view", action="store_true",
                    help="매치 후 브라우저 뷰어로 녹화 자동 재생 (필요하면 뷰어 서버도 기동)")
    ap.add_argument("--view-port", type=int, default=7900,
                    help="뷰어 서버 포트 (기본 7900)")
    ap.add_argument("--live", action="store_true",
                    help="실시간 중계 켜기 — Tacview 에서 Record→Real-time Telemetry 로 "
                         "127.0.0.1:42674 접속해 경기를 생중계로 본다 (시뮬 속도로 진행)")
    ap.add_argument("--roster", default=None,
                    help="배치 모드: 판 목록 파일(각 줄 '<상대stem>/<내진영>' 또는 "
                         "쉼표 구분). --blue 가 내 트리, 상대는 --opponents-dir 에서 찾음")
    ap.add_argument("--opponents-dir", default="roster",
                    help="배치 모드 상대 YAML 폴더")
    ap.add_argument("--acmi-dir", default=None,
                    help="배치 모드 녹화 폴더 (기본: replays/roster_<일시>/ 에 저장)")
    ap.add_argument("--no-acmi", action="store_true",
                    help="배치 모드에서 녹화 끄기 (결과 표만 — 속도·용량 우선일 때)")
    # 하위호환: 구 --maneuver 는 --red scripted:<m> 의 별칭
    ap.add_argument("--maneuver", default=None, choices=SCRIPTED_MANEUVERS,
                    help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.roster:
        return run_roster(args)
    if args.maneuver:
        args.red = f"scripted:{args.maneuver}"
    if args.scenario == "perch":
        args.scenario = "perch_offense"
    if args.acmi is None:
        args.acmi = _default_acmi_path(args.blue, args.red)

    os.makedirs(os.path.dirname(args.acmi) or ".", exist_ok=True)
    log_path = os.path.splitext(args.acmi)[0] + ".txt"
    sys.stdout = _Tee(sys.__stdout__, open(log_path, "w", encoding="utf-8", buffering=1))
    print(f"명령줄: python {' '.join(sys.argv)}")
    ic = initial_conditions(args.scenario, range_nm=args.range_nm, seed=args.seed)

    blue = _make_pilot("Blue", args.blue, ic["blue"])

    if args.red.startswith("scripted:"):
        m = args.red.split(":", 1)[1]
        if m not in SCRIPTED_MANEUVERS:
            ap.error(f"scripted 기동은 {SCRIPTED_MANEUVERS} 중 하나: {args.red}")
        r = ic["red"]
        red = ScriptedOpponent(init_pos_ned=r["pos"], speed_kts=r["kcas"],
                               heading_deg=r["psi"], maneuver=m, turn_rate_dps=6.0)
    else:
        red = _make_pilot("Red", args.red, ic["red"])

    live = None
    if args.live:
        from aircombat.debrief.tacview_realtime import TacviewRealtimeServer
        import time as _time
        live = TacviewRealtimeServer().start()
        print(f"실시간 중계 대기 중 — Tacview: Record → Real-time Telemetry → "
              f"127.0.0.1:{live.port} (30초 내 접속, 미접속 시 그냥 시작)")
        for _ in range(60):
            if live.client_count > 0:
                print(f"관전자 {live.client_count}명 접속 — 시작합니다")
                break
            _time.sleep(0.5)

    match = Match(blue, red, duration_s=args.duration, acmi_path=args.acmi, log_hz=120.0,
                  progress=sys.stderr.isatty(),   # 리다이렉트 시 \r 스팸 방지
                  live=live,
                  overtime_s=OVERTIME_S if args.overtime else 0.0)
    
    print(f"\n매치 시작: {args.scenario}  {args.blue} vs {args.red}  ({args.duration:.0f}s)")
    try:
        res = match.run()
    finally:
        if live is not None:
            live.stop()

    print("=" * 60)
    print("MATCH RESULT")
    print(f"  scenario  : {args.scenario}  blue={args.blue}  red={args.red}")
    print(f"  winner    : {res.winner}")
    print(f"  condition : {res.condition}")
    print(f"  time      : {res.time_s:.1f}s")
    print(f"  HP        : blue={res.hp_blue:.1f}  red={res.hp_red:.1f}")
    if res.overtime:
        wez, ata = res.wez_time or {}, res.ata_mean or {}
        print(f"  overtime  : 진입 (연장 {OVERTIME_S:.0f}s)")
        print(f"  조준시간  : blue={wez.get('blue', 0.0):.1f}s  red={wez.get('red', 0.0):.1f}s"
              "   <- 타이브레이크 1")
        print(f"  평균 ATA  : blue={ata.get('blue', 0.0):.1f}deg  red={ata.get('red', 0.0):.1f}deg"
              "   <- 타이브레이크 2")
    print(f"  ACMI      : {args.acmi}")
    print(f"  LOG       : {log_path}")
    print("=" * 60)
    # 단일 현미경 매치 → 디브리프 요약도 출력(plot 은 Match.run 이 이미 무조건 산출).
    from aircombat.debrief.replay_debrief import parse_acmi, debrief_summary
    try:
        debrief_summary(parse_acmi(args.acmi), title=os.path.basename(args.acmi))
    except Exception as e:
        print(f"  [debrief 경고] {type(e).__name__}: {e}")
    if args.view:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        from acmi_viewer.launch import open_replay
        url = open_replay(args.acmi, port=args.view_port)
        if url:
            print(f"  뷰어      : {url}")
    if args.analyze:
        # ponytail: subprocess 로 위임 — analyze_wez 내부 리팩토링 없이 재사용.
        # capture 후 print 로 흘려 로그 txt 에도 남긴다.
        # 자식은 Windows 로케일 코드페이지(cp949)로 stdout 을 쓰는데 부모가 utf-8 로
        # 강제 디코딩하면 reader 스레드가 죽는다. 자식이 utf-8 을 내도록 env 로 못박고,
        # errors="replace" 로 이상 바이트에도 크래시하지 않게 한다.
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        p = subprocess.run([sys.executable,
                            os.path.join(os.path.dirname(__file__), "analyze_wez.py"),
                            args.acmi], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        print(p.stdout, end="")
        if p.stderr:
            print(p.stderr, end="", file=sys.stderr)
        return p.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
