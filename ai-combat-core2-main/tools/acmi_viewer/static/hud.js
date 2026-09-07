// HUD — 재생 컨트롤, 타임라인(HIT 북마크), 기체별 전술 패널,
// 기하 readout·컨트롤 포지션 (tacview ai-combat-analysis addon 정합).
import { attrAt, parsePacked, indexAt } from "./acmi.js";
import { drawPipHud } from "./pip_hud.js";

const M_TO_FT = 3.28084;
const MPS_TO_KT = 1.94384; // ACMI CAS 는 m/s (Tacview 스펙) — 표시는 kts

const STAT_KEYS = [
  ["CAS", "CAS [kts]", 0, MPS_TO_KT],
  ["HDG", "HDG [°]", 0],
  ["Distance", "거리 [ft]", 0],
  ["ClosureRate", "접근율 [kts]", 0],
  ["ATA", "ATA [°]", 1],
  ["AA", "AA [°]", 1],
  ["HCA", "HCA [°]", 1],
  ["RollOff", "RollOff [°]", 1],
  ["Throttle", "스로틀", 2],
  ["Gtarget", "G 명령", 1],
  ["Gavail", "G 가용", 1],
  ["Nz", "G 실측", 1],
];

export class HUD {
  /**
   * @param {Object} handlers - {onSeek(t), onPlayToggle(), onSpeedStep(dir),
   *   onNudge(sec),
   *                            onCamera(mode), onReplay(name)}
   */
  constructor(handlers) {
    this.el = {
      replaySelect: document.getElementById("replay-select"),
      play: document.getElementById("play"),
      rev: document.getElementById("rev"),
      fwd: document.getElementById("fwd"),
      speedBadge: document.getElementById("speed-badge"),
      camera: document.getElementById("camera"),
      time: document.getElementById("time"),
      status: document.getElementById("status"),
      timeline: document.getElementById("timeline"),
      bookmarks: document.getElementById("bookmarks"),
      cardBlue: document.getElementById("card-blue"),
      cardRed: document.getElementById("card-red"),
      step: document.getElementById("step"),
      ground: document.getElementById("ground"),
      ctrlBlue: document.getElementById("ctrl-blue"),
      ctrlRed: document.getElementById("ctrl-red"),
      pipBlue: document.getElementById("pip-blue"),
      pipRed: document.getElementById("pip-red"),
      pipToggle: document.getElementById("pip-toggle"),
      tlStrip: document.getElementById("tl-strip"),
    };
    this.duration = 0;
    this.startTime = 0;

    // 스페이스 = 재생/정지. 셀렉트·슬라이더에 포커스가 있으면 그쪽 기본 동작을
    // 뺏지 않도록 비켜 준다(스페이스로 드롭다운을 여는 게 브라우저 기본이다).
    window.addEventListener("resize", () => this._drawStrip());

    document.addEventListener("keydown", (e) => {
      const tag = document.activeElement?.tagName;
      if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.code === "Space" && !e.repeat) {
        e.preventDefault(); handlers.onPlayToggle();
      } else if (e.code === "ArrowRight") {
        // 방향키 = **시점 이동**(스크럽). Shift 면 크게(5s), 아니면 1s.
        // 배속 조절은 빨리감기/되감기 버튼(⏪⏩)이 맡는다 — 역할을 나눈다.
        e.preventDefault(); handlers.onNudge(e.shiftKey ? 5 : 1);
      } else if (e.code === "ArrowLeft") {
        e.preventDefault(); handlers.onNudge(e.shiftKey ? -5 : -1);
      }
    });

    this.el.pipToggle.addEventListener("click", () => {
      const on = this.el.pipBlue.hidden; // 토글 후 상태
      this.el.pipBlue.hidden = this.el.pipRed.hidden = !on;
      this.el.pipToggle.textContent = on ? "1인칭 ON" : "1인칭 OFF";
    });

    this.el.play.addEventListener("click", handlers.onPlayToggle);
    // 빨리감기/되감기 — 누를 때마다 배속을 한 단계씩. 반대 방향을 누르면 먼저 1×로
    // 돌아온 뒤 그 방향으로 간다(카세트·미디어플레이어의 관례).
    this.el.fwd.addEventListener("click", () => handlers.onSpeedStep(+1));
    this.el.rev.addEventListener("click", () => handlers.onSpeedStep(-1));
    this.el.camera.addEventListener("change", (e) => handlers.onCamera(e.target.value));
    this.el.replaySelect.addEventListener("change", (e) => handlers.onReplay(e.target.value));
    // 지면 선택은 사람마다 취향이 갈려서(지도 vs 격자) 브라우저에 기억시킨다 —
    // 매번 고르게 하면 결국 아무도 안 바꾼다.
    this.el.ground.addEventListener("change", (e) => {
      // sandbox 된 iframe 에서는 저장이 SecurityError — 기억만 못 할 뿐 동작엔 지장 없다.
      try { localStorage.setItem("acmiGround", e.target.value); } catch { /* sandbox */ }
      handlers.onGround(e.target.value);
    });
    this.el.timeline.addEventListener("input", (e) => {
      handlers.onSeek(this.startTime + (+e.target.value / 1000) * this.duration);
    });
    this.onSeek = handlers.onSeek;
  }

  setReplayList(names, selected) {
    this.el.replaySelect.replaceChildren(
      ...names.map((n) => new Option(n.replace(/\.acmi$/, ""), n, false, n === selected)),
    );
  }

  /**
   * 타임라인 사격 구간 띠 — 위 절반 청, 아래 절반 적.
   *
   * 북마크(점)만으로는 **WEZ 가 얼마나 지속됐는지** 알 수 없다. 빠르게 스크럽하면서
   * "언제 맞았나"를 집으려면 구간이 보여야 한다. 진하기는 조준 등급을 쓴다 —
   * 룰북의 데미지는 ATA 계단(2°/10°/20°/30° → 50/37.5/25/12.5 HP/s)이라, 같은 WEZ
   * 라도 정조준이면 훨씬 아프다. 그 차이가 색 농도로 읽힌다.
   */
  _drawStrip() {
    const c = this.el.tlStrip;
    if (!c || !this.tracks) return;
    const dpr = Math.min(window.devicePixelRatio, 2);
    const w = Math.max(1, Math.round(c.clientWidth * dpr));
    const h = Math.max(1, Math.round(c.clientHeight * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const g = c.getContext("2d");
    g.clearRect(0, 0, w, h);
    const half = h / 2;
    for (const [key, track, color, y] of [
      ["blue", this.tracks.blue, "77,141,245", 0],
      ["red", this.tracks.red, "240,96,94", half],
    ]) {
      if (!track) continue;
      const n = track.times.length;
      for (let i = 0; i < n; i++) {
        if (attrAt(track, "InWEZ", i) !== true) continue;
        // 조준 등급 → 농도. ATA 가 없으면 중간값으로.
        const ata = attrAt(track, "ATA", i);
        const a = typeof ata !== "number" ? 0.6
          : ata < 2 ? 1.0 : ata < 10 ? 0.8 : ata < 20 ? 0.6 : 0.42;
        const x = ((track.times[i] - this.startTime) / this.duration) * w;
        g.fillStyle = `rgba(${color},${a})`;
        // 사격은 1~1.5초라 전체(166초) 대비 1% 도 안 된다 — 최소 폭을 줘야 보인다.
        g.fillRect(x, y, Math.max(3 * dpr, w / n), half);
      }
    }
  }

  /** 상단 배속 배지 갱신. */
  setSpeed(speed) {
    if (this.el.speedBadge) this.el.speedBadge.textContent = `${speed}×`;
  }

  /** 지면 셀렉트를 현재 모드에 맞춘다(URL·localStorage 로 이미 정해져 있다). */
  setGroundMode(mode) {
    this.el.ground.value = mode;
  }

  setStatus(text) {
    this.el.status.textContent = text;
    this.el.status.style.display = text ? "" : "none";
  }

  /** 리플레이 로드 완료 시 호출: 시간축·북마크·기체 카드 골격 구성. */
  setReplay(parsed, blue, red) {
    this.startTime = parsed.startTime;
    this.duration = Math.max(parsed.endTime - parsed.startTime, 0.001);
    this.tracks = { blue, red };
    this._drawStrip();

    // 북마크는 **뭉친다.** HIT 는 피격 프레임마다 찍혀 40개 넘게 촘촘히 서는데,
    // 지속 구간은 이제 위의 띠가 보여 주므로 점은 "여기서 사건이 시작됐다" 만
    // 표시하면 된다. 1.5초 안쪽은 한 개로 합친다.
    // 북마크에는 **세 종류**가 섞여 있다: 피격(HIT) · 승패(WIN) · 전술 전환.
    // 전부 같은 호박색으로 그리면 33개가 고르게 늘어서 "언제 맞았나"를 못 집는다.
    // 종류로 색·높이를 가르고, 같은 종류끼리만 뭉친다.
    const kindOf = (t) => (/WIN|RESULT|승|패/i.test(t) ? "win"
      : /HIT/i.test(t) ? "hit" : "tac");
    const MERGE_S = 1.5;
    const marks = [];
    for (const bm of parsed.bookmarks) {
      const kind = kindOf(bm.text);
      const last = marks[marks.length - 1];
      if (last && kind !== "win" && last.kind === kind
          && bm.time - last.time < MERGE_S) {
        last.n += 1;
        continue;
      }
      marks.push({ time: bm.time, text: bm.text, kind, n: 1 });
    }
    this.el.bookmarks.replaceChildren(...marks.map((bm) => {
      const tick = document.createElement("div");
      tick.className = `bookmark ${bm.kind}`;
      tick.dataset.text = `${bm.time.toFixed(1)}s ${bm.text}`
        + (bm.n > 1 ? ` (외 ${bm.n - 1})` : "");
      tick.style.left = `${((bm.time - this.startTime) / this.duration) * 100}%`;
      tick.addEventListener("click", () => this.onSeek(bm.time));
      return tick;
    }));

    for (const [card, track] of [[this.el.cardBlue, blue], [this.el.cardRed, red]]) {
      // 호출부호는 ACMI 파일에서 온다 — 대회 운영에서는 참가자가 정한 팀 이름이
      // 그대로 실린다. 템플릿에 끼우면 그게 곧 innerHTML 주입이고, 뷰어는 사이트와
      // same-origin iframe 이라 세션까지 닿는다. 골격만 innerHTML, 이름은 textContent.
      card.innerHTML = `
        <h2><span class="callsign"></span>
            <span class="hp-num"></span><span class="wez">IN WEZ</span></h2>
        <div class="hpbar"><i></i></div>
        <div class="stats">${STAT_KEYS.map(([, label]) =>
          `<span><b>${label}</b><span class="v"></span></span>`).join("")}</div>
        <div class="lblock"></div>`;
      card.querySelector(".callsign").textContent =
        track.meta.CallSign || track.meta.Name || track.id;
    }
  }

  setPlaying(playing) {
    this.el.play.textContent = playing ? "⏸" : "▶";
  }

  /** 1인칭 HUD 의 호출부호·아군 표시 — 리플레이 교체 때 갱신.
   *  mineSide: "blue"|"red"|null (null 이면 어느 쪽이 우리 기체인지 단정하지 않는다). */
  setPipLabels(blue, red, mineSide) {
    for (const [key, pip, track] of [["blue", this.el.pipBlue, blue],
                                     ["red", this.el.pipRed, red]]) {
      pip.dataset.callsign = track.meta.CallSign || track.meta.Name || track.id;
      pip.dataset.mine = key === mineSide ? "1" : "";
    }
  }

  /** 매 프레임 갱신. states: scene.update() 반환값, pipCams: scene.pipCams. */
  update(t, states, tracks, pipCams) {
    this.el.time.textContent = `${t.toFixed(1)} / ${(this.startTime + this.duration).toFixed(1)} s`;
    this.el.timeline.value = Math.round(((t - this.startTime) / this.duration) * 1000);

    // 비에너지 E = alt[ft] + kt²/64.4 — 상대 비교용으로 양측 선계산 (addon 정합)
    const energy = {};
    for (const key of ["blue", "red"]) {
      const state = states[key];
      const track = tracks[key];
      if (!state || !track) continue;
      const casMs = attrAt(track, "CAS", state.index);
      const cas = typeof casMs === "number" ? casMs * MPS_TO_KT : casMs;
      const altFt = track.position[state.index * 3 + 2] * M_TO_FT;
      energy[key] = { cas, altFt,
        E: typeof cas === "number" ? altFt + cas * cas / 64.4 : null };
    }

    for (const [key, foeKey, card] of [["blue", "red", this.el.cardBlue],
                                       ["red", "blue", this.el.cardRed]]) {
      const state = states[key];
      const track = tracks[key];
      if (!state || !track) continue;
      const i = state.index;

      const hp = state.health ?? 0;
      card.querySelector(".hp-num").textContent = `${hp.toFixed(1)} HP`;
      const bar = card.querySelector(".hpbar i");
      bar.style.width = `${Math.max(hp, 0)}%`;
      bar.style.background = hp > 50 ? "#45d17c" : hp > 20 ? "#e8b93e" : "#e85d4a";
      card.classList.toggle("inwez", state.inWez);

      const values = card.querySelectorAll(".stats .v");
      STAT_KEYS.forEach(([attr, , digits, scale], k) => {
        const v = attrAt(track, attr, i);
        values[k].textContent =
          typeof v === "number" ? (v * (scale ?? 1)).toFixed(digits) : "–";
      });

      card.querySelector(".lblock").textContent =
        lblockText(track, i, energy[key], energy[foeKey], states[foeKey]?.inWez);

      // 1인칭 HUD — 3D 는 뒤의 WebGL 이 그렸고, 여기서 심볼로지만 덧그린다.
      const pip = this.el[key === "blue" ? "pipBlue" : "pipRed"];
      const cam = pipCams?.get(key);
      if (cam && !pip.hidden) {
        drawPipHud(pip.querySelector("canvas"), cam, {
          state, foeState: states[foeKey], track,
          callsign: pip.dataset.callsign ?? key,
          team: key, mine: pip.dataset.mine === "1",
        });
      }

      drawControl(this.el[key === "blue" ? "ctrlBlue" : "ctrlRed"], {
        thr: attrAt(track, "Throttle", i),
        ailIn: attrAt(track, "RollControlInput", i),
        elevIn: attrAt(track, "PitchControlInput", i),
        rudIn: attrAt(track, "YawControlInput", i),
        ailPos: attrAt(track, "RollControlPosition", i),
        elevPos: attrAt(track, "PitchControlPosition", i),
        rudPos: attrAt(track, "YawControlPosition", i),
      });
    }

    // 스텝 수는 상단 시계 옆으로. (예전에는 화면 한복판에 초록 패널로
    // Distance·ATA·AA·HCA·RollOff·Closure 를 띄웠는데 전부 양쪽 카드에 이미 있는
    // 값이라, 같은 숫자를 두 군데서 읽게 만들 뿐이었다.)
    const bt = tracks.blue;
    if (bt && states.blue) {
      const steps = attrAt(bt, "StepsElapsed", states.blue.index);
      this.el.step.textContent = steps === null ? "" : `step ${steps}`;
    }
  }
}

// ── tacview addon 정합 L1~L4 블록 ─────────────────────────────────────
const fmt = (v, d) => (typeof v === "number" ? v.toFixed(d) : "–");
const rnd = (v) => (typeof v === "number" ? `${Math.round(v)}` : "–");

function lblockText(track, i, me, foe, foeInWez) {
  const l1 = parsePacked(attrAt(track, "L1", i));
  const l2 = parsePacked(attrAt(track, "L2", i));
  const l3 = parsePacked(attrAt(track, "L3", i));
  const aimV = parseFloat(l2.aim);
  const aimTag = Number.isFinite(aimV) && aimV !== 0
    ? `  aim${aimV > 0 ? "+" : ""}${l2.aim}` : "";
  const modeTag = l2.mode && l2.mode !== "-" ? `  >${l2.mode}` : "";
  // 에너지 우열 화살표: 상대 대비 ×1.1 초과 ⬆ / ×0.9 미만 ⬇
  const eTag = me?.E != null && foe?.E != null
    ? (me.E > foe.E * 1.1 ? " ⬆️" : me.E < foe.E * 0.9 ? " ⬇️" : "") : "";

  const lines = [
    `L1 | ${l1.node ?? "–"}  ${l1.pursuit ?? "–"}` +
      `${l1.maxG === "1" ? "  maxG" : ""}${modeTag}`,
    `L2 | G${fmt(attrAt(track, "Gtarget", i), 2)}` +
      `/${fmt(attrAt(track, "Gavail", i), 2)}  ${l2.gmode ?? "–"}`,
    `   | dphi ${l2.dphi ?? "–"}  ${l2.pwr ?? "–"}${aimTag}`,
    `L3 | lim ${l3.lim ?? "–"}  thr ${fmt(attrAt(track, "Throttle", i), 2)}`,
    `L4 | ${rnd(me?.cas)}kts ${rnd(me?.altFt)}ft${eTag}  ` +
      `${actualG(track, i).toFixed(1)}G ${rnd(attrAt(track, "HDG", i))}°T`,
  ];
  if (foeInWez) lines.push("⚠️ UNDER ATTACK");
  return lines.join("\n");
}

// 실측 Nz(JSBSim accelerations/Nz, 2026-07-17부터 기록) 우선.
// 없는 구 리플레이는 궤적 추정 fallback.
function actualG(track, i) {
  const nz = attrAt(track, "Nz", i);
  return typeof nz === "number" ? nz : loadFactorG(track, i);
}

// 하중배수 추정: ±0.5s 창 중앙차분 가속도 a 에서 G = |a − g⃗|/9.81.
// Tacview GetCurrentVerticalGForce 도 궤적 기반 추정 — 같은 계열.
// 인접 샘플(0.04s) 미분은 좌표 양자화 노이즈로 무의미(검증: 평균 115G)해서
// 넓은 창 필수. 검증(2026-07-17): 직선비행 1.17±0.23G, 급기동 ±1~2G.
const G_WIN_S = 0.5;
function loadFactorG(track, i) {
  const t = track.times;
  const p = track.position;
  const n = t.length;
  const a = indexAt(track, t[i] - G_WIN_S);
  const c = Math.min(indexAt(track, t[i] + G_WIN_S) + 1, n - 1);
  if (a >= i || i >= c) return 1;
  const dt1 = t[i] - t[a];
  const dt2 = t[c] - t[i];
  if (dt1 <= 0 || dt2 <= 0) return 1;
  const dtm = (t[c] - t[a]) / 2;
  const d = (k, i1, i0, dt) => (p[i1 * 3 + k] - p[i0 * 3 + k]) / dt;
  const ax = (d(0, c, i, dt2) - d(0, i, a, dt1)) / dtm;
  const ay = (d(1, c, i, dt2) - d(1, i, a, dt1)) / dtm;
  const az = (d(2, c, i, dt2) - d(2, i, a, dt1)) / dtm + 9.81;
  return Math.hypot(ax, ay, az) / 9.81;
}

// ── 컨트롤 포지션 패널 (tacview Control Position 정합) ──────────────
// 세 조종 입력을 한 칸에 모은다:
//   · 스틱 상자 — 가로=롤, 세로=피치.
//     주황 = L3(INDI)가 낸 명령 `fcs/*-cmd-norm`
//     회색 = 실제로 선 타면 `fcs/*-pos-norm`
//     ★ 둘 사이는 서보 하나가 아니라 F-16 의 fly-by-wire 제어법칙 전체다
//       (f16.xml:502-613 = 받음각 한계기 → 동압 게인 스케줄 → G·피치레이트 PID
//        → 액추에이터 레이트 제한). 그래서 "최대 당김" 을 명령해도 타면은 끝까지
//       가지 않는다 — 실측 평균이 명령 −0.80 대 실위치 −0.13 인 게 정상이다.
//       벌어짐은 **제어기의 요구가 얼마나 깎였는가**로 읽어야 한다
//       (카드의 `L3 | lim` 포화 축, `G 명령/가용/실측` 과 같은 이야기).
//   · 스로틀(좌측 세로바) — 0.5 이상이 AB 구간(붉은 띠). 아래에 % 숫자.
//   · 러더(하단 가로바) — 노랑 = 명령, 빨강 점 = 실위치.
// 가로 104px 띠에 [스로틀][스틱 상자][범례] 를 나란히. 정사각형이던 시절에는
// 두 마커(명령/실위치)에 이름을 붙일 자리가 없어 "빈 사각형은 뭐냐" 가 됐다 —
// 이제 오른쪽에 범례를 상시 표시한다.
// 좌표는 아래 격자에 그리고 캔버스 실크기·DPR 에 맞춰 스케일한다.
// 스틱 상자가 캔버스 폭의 30% 밖에 안 되고 범례가 60% 를 먹고 있었다 — 읽으라고
// 있는 것은 상자 쪽이므로 자리를 뒤집었다. 다만 그 과정에서 위아래 여백을 안 남겨
// **THR 라벨이 잘리고 "당김" 이 마커에 가렸다**. 이제 좌표계를 층으로 나눠 잡는다:
//
//   y   0…12   위 라벨 줄 (THR 값 · "밀기")
//      14…86   본체 (스로틀 바 · 스틱 상자)
//      88…94   아래 라벨 줄 ("당김")
//      96…103  러더 바
//
// 그리고 **그룹 전체를 캔버스 폭 가운데로** 옮긴다(예전에는 왼쪽에 붙고 오른쪽에
// 범례가 남아 무게중심이 한쪽으로 쏠렸다). 글자 크기는 한 값으로 통일한다.
const CTRL_H = 104;
const CTRL_FONT = "600 8px Consolas, monospace";   // 패널 전체 공통
const CTRL_THR = { x: 4, y: 14, w: 15, h: 72 };
const CTRL_BOX = { x: 32, y: 14, w: 72, h: 72 };
const CTRL_RUD = { x: 32, y: 96, w: 72, h: 7 };
const CTRL_LEGEND_X = 118;
// 어두운 계기 테마 팔레트 — index.html 의 토큰과 같은 값을 캔버스에서도 쓴다.
const CT = {
  face: "rgba(255,255,255,0.05)",      // 상자 바탕
  edge: "rgba(255,255,255,0.20)",      // 상자 테두리
  grid: "rgba(255,255,255,0.07)",      // 4분할 보조선
  cross: "rgba(255,255,255,0.16)",     // 중심 십자
  text: "rgba(221,229,240,0.72)",      // 라벨
  dim: "rgba(135,148,168,0.85)",
  cmd: "rgba(232,163,61,0.95)",        // L3 명령 (--warn)
  cmdEdge: "rgba(255,205,130,0.9)",
  ghost: "rgba(200,215,235,0.55)",     // 조종면 실위치
  thr: "rgba(240,96,94,0.62)",         // 스로틀 — 어두운 배경에선 낮춰야 안 튄다
  rud: "rgba(232,163,61,0.85)",
};
const CTRL_LEGEND_W = 104;                          // 범례가 차지하는 폭
const CTRL_GROUP_W = CTRL_LEGEND_X + CTRL_LEGEND_W; // 중앙정렬용 그룹 전체 폭

function drawControl(canvas, v) {
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight || CTRL_H;
  if (cssW < 8) return;
  const dpr = Math.min(window.devicePixelRatio, 2);
  const w = Math.round(cssW * dpr);
  const h = Math.round(cssH * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const g = canvas.getContext("2d");
  const k = h / CTRL_H;                      // 높이 기준 스케일 — 폭은 남는 대로
  const gridW = w / k;
  // 그룹을 가운데로. 범례가 안 들어갈 만큼 좁으면 범례를 빼고 본체만 가운데 둔다.
  const showLegend = gridW >= CTRL_GROUP_W;
  const groupW = showLegend ? CTRL_GROUP_W : CTRL_LEGEND_X - 8;
  const ox = Math.max(0, (gridW - groupW) / 2);
  g.setTransform(k, 0, 0, k, 0, 0);
  g.clearRect(0, 0, gridW, CTRL_H);
  g.translate(ox, 0);
  g.font = CTRL_FONT;
  g.textBaseline = "middle";
  g.lineWidth = 1;

  drawStickBox(g, v);
  drawThrottle(g, v);
  drawRudder(g, v);
  if (showLegend) drawCtrlLegend(g);
}

// 범례 — 두 마커가 무엇인지만. **설명 문장은 빼야 한다**: 계기는 라벨을 달지
// 문장을 쓰지 않는다("간격 = FBW 가 깎은 양" 같은 줄이 패널 폭의 절반을 먹고
// 있었다). 그 설명은 README 와 패널 title 속성으로 옮겼다.
function drawCtrlLegend(g) {
  const x = CTRL_LEGEND_X;
  g.save();
  g.textAlign = "left";

  g.fillStyle = CT.cmd;
  g.fillRect(x, 34 - 4.5, 9, 9);
  g.strokeStyle = CT.cmdEdge;
  g.strokeRect(x, 34 - 4.5, 9, 9);
  g.fillStyle = CT.text;
  g.fillText("명령", x + 15, 34);

  g.strokeStyle = CT.ghost;
  g.lineWidth = 1.5;
  g.strokeRect(x, 52 - 5, 10, 10);
  g.lineWidth = 1;
  g.fillStyle = CT.text;
  g.fillText("타면", x + 15, 52);
  g.restore();
}

const clamp1 = (u) => Math.max(-1, Math.min(u ?? 0, 1));

function drawStickBox(g, v) {
  const b = CTRL_BOX;
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  // 롤: 오른쪽 스틱 = 오른쪽 화면. 피치: JSBSim elevator-cmd-norm 은 당김이 음수라
  // 화면에서도 당김을 아래(조종사 쪽)로 둔다 — Tacview 표시 방향과 같다.
  const sx = (u) => cx + (b.w / 2 - 4) * clamp1(u);
  const sy = (u) => cy - (b.h / 2 - 4) * clamp1(u);

  g.fillStyle = CT.face;
  g.fillRect(b.x, b.y, b.w, b.h);
  g.strokeStyle = CT.edge;
  g.strokeRect(b.x, b.y, b.w, b.h);

  g.strokeStyle = CT.grid;                    // 4분할 보조선
  g.beginPath();
  for (const f of [0.25, 0.75]) {
    g.moveTo(b.x + b.w * f, b.y); g.lineTo(b.x + b.w * f, b.y + b.h);
    g.moveTo(b.x, b.y + b.h * f); g.lineTo(b.x + b.w, b.y + b.h * f);
  }
  g.stroke();
  g.strokeStyle = CT.cross;                   // 중심 십자
  g.beginPath();
  g.moveTo(b.x, cy); g.lineTo(b.x + b.w, cy);
  g.moveTo(cx, b.y); g.lineTo(cx, b.y + b.h);
  g.stroke();

  // 축 라벨은 **상자 밖**에. 안에 두면 스틱 마커가 그 위에 앉아 글자를 덮는다.
  g.fillStyle = CT.dim;
  g.textAlign = "center";
  g.fillText("밀기", cx, b.y - 6);
  g.fillText("당김", cx, b.y + b.h + 5);
  // 좌/우는 상자 **안쪽 위 모서리**에. 바깥 왼쪽은 스로틀 바와 붙어 눌리고,
  // 안쪽 가운데는 스틱 마커가 지나간다.
  g.textAlign = "left";
  g.fillText("L", b.x + 3, b.y + 7);
  g.textAlign = "right";
  g.fillText("R", b.x + b.w - 3, b.y + 7);

  const gx = sx(v.ailPos), gy = sy(v.elevPos);   // 조종면 실위치(고스트)
  g.strokeStyle = CT.ghost;
  g.lineWidth = 1.5;
  g.strokeRect(gx - 5, gy - 5, 10, 10);

  const ix = sx(v.ailIn), iy = sy(v.elevIn);     // 조종사 명령
  g.strokeStyle = CT.cmd;
  g.lineWidth = 2;
  g.beginPath(); g.moveTo(cx, cy); g.lineTo(ix, iy); g.stroke();
  g.fillStyle = CT.cmd;
  g.fillRect(ix - 4.5, iy - 4.5, 9, 9);
  g.strokeStyle = CT.cmdEdge;
  g.lineWidth = 1;
  g.strokeRect(ix - 4.5, iy - 4.5, 9, 9);
}

function drawThrottle(g, v) {
  const t = CTRL_THR;
  const thr = Math.max(0, Math.min(v.thr ?? 0, 1));
  const abY = t.y + t.h * 0.5;                 // 0.5 이상 = AB

  g.fillStyle = CT.face;
  g.fillRect(t.x, t.y, t.w, t.h);
  g.fillStyle = "rgba(214,58,58,0.13)";        // AB 구간 띠
  g.fillRect(t.x, t.y, t.w, t.h * 0.5);

  g.fillStyle = thr > 0.5 ? "#d63a3a" : "#2fae5b";
  g.fillRect(t.x + 1, t.y + t.h - t.h * thr, t.w - 2, t.h * thr);

  g.strokeStyle = CT.edge;
  g.strokeRect(t.x, t.y, t.w, t.h);
  g.strokeStyle = "#d63a3a";                   // AB 경계
  g.beginPath(); g.moveTo(t.x, abY); g.lineTo(t.x + t.w, abY); g.stroke();

  // 이름과 값을 한 줄로 바 **위에** — 아래에 두면 러더의 RUD 라벨과 겹친다
  g.fillStyle = CT.text;
  g.textAlign = "center";
  g.fillText(`THR ${Math.round(thr * 100)}`, t.x + t.w / 2, t.y - 6);
  g.fillStyle = "rgba(214,58,58,0.85)";
  g.textAlign = "left";
  g.fillText("AB", t.x + t.w + 2, abY);
}

function drawRudder(g, v) {
  const r = CTRL_RUD;
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
  const rx = (u) => cx + (r.w / 2 - 3) * clamp1(u);

  g.fillStyle = CT.face;
  g.fillRect(r.x, r.y, r.w, r.h);
  g.strokeStyle = CT.edge;
  g.strokeRect(r.x, r.y, r.w, r.h);
  g.strokeStyle = CT.cross;
  g.beginPath(); g.moveTo(cx, r.y); g.lineTo(cx, r.y + r.h); g.stroke();

  g.strokeStyle = "#d4a900";                   // 명령 — 중심에서 뻗는 막대
  g.lineWidth = 3;
  g.beginPath(); g.moveTo(cx, cy); g.lineTo(rx(v.rudIn), cy); g.stroke();
  g.fillStyle = "#d63a3a";                     // 실위치
  g.beginPath(); g.arc(rx(v.rudPos), cy, 2.5, 0, Math.PI * 2); g.fill();

  g.fillStyle = CT.dim;
  g.lineWidth = 1;
  g.textAlign = "right";
  g.fillText("RUD", r.x - 3, cy);
}
