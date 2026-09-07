// 1인칭 뷰 HUD — F-16 심볼로지. PIP 캔버스에 2D 로 겹쳐 그린다.
//
// 각도를 갖는 심볼(피치 사다리·FPM·TD 박스)은 화면에 눈대중으로 찍지 않고
// **PIP 카메라로 실제 투영**한다. 그래서 FOV(firstperson.js PIP_FOV_DEG)를 바꿔도
// 심볼과 3D 장면이 어긋나지 않는다. 반대로 테이프·수치는 화면 고정이라 FOV 무관.
//
// 실기와 다른 점(의도적):
//  · 실 F-16 HUD 시야는 25°인데 여기는 복기용이라 훨씬 넓다. 사다리·FPM 이 투영식
//    이라 넓은 시야에서도 각도는 정확하다.
//  · 건 크로스를 화면 중앙(보어사이트)에 둔다 — 이 엔진의 ATA 가 기수 기준이라
//    "중앙 = ATA 0" 이 성립해야 복기에 쓸모가 있다.
import * as THREE from "three";
import { attrAt, parsePacked, indexAt } from "./acmi.js";

const DEG = Math.PI / 180;
const M_TO_FT = 3.28084;
const MPS_TO_KT = 1.94384;

const GREEN = "#39ff9a";      // HUD 기본
const WARN = "#ff5a3c";       // 피격·사격 경고
const FAR = 1e5;              // 방향 심볼을 찍을 가상 거리 [m]

// 기총 피해 등급 경계 (RULEBOOK §4) — 2° 안이 최대 피해, 30° 밖은 0.
const PIPPER_DEG = 2;
const WEZ_DEG = 30;

const _v = new THREE.Vector3();

/** 월드 좌표 → 캔버스 CSS 픽셀. behind=true 면 카메라 뒤(그리면 안 됨). */
export function project(cam, x, y, z, w, h) {
  _v.set(x, y, z).applyMatrix4(cam.matrixWorldInverse);
  const behind = _v.z > -1e-3; // 카메라는 로컬 −Z 를 본다
  _v.applyMatrix4(cam.projectionMatrix);
  return {
    x: (_v.x * 0.5 + 0.5) * w,
    y: (-_v.y * 0.5 + 0.5) * h,
    behind,
  };
}

/** 화면 중심에서 각도 deg 에 해당하는 반경 [px] (수직 FOV 기준). */
function angleRadius(cam, deg, h) {
  return (h / 2) * (Math.tan(deg * DEG) / Math.tan((cam.fov / 2) * DEG));
}

// FPM 평활 창 [s]. **인접 샘플 미분은 쓸 수 없다** — ACMI 위경도가 소수점 7자리로
// 양자화돼 있어 40ms 간격 차분은 좌표 잡음이 지배한다(hud.js loadFactorG 가 같은
// 이유로 ±0.5s 창을 쓴다. 좁은 창으로 두면 FPM 이 눈에 띄게 떤다).
// 0.25s 면 5G 선회에서 방향 지연이 약 1° — 떨림보다 이쪽이 훨씬 읽기 좋다.
const VEL_WIN_S = 0.25;

/** i번째 샘플의 속도 벡터 [m/s] (±VEL_WIN_S 창 차분). 산출 불가면 null. */
function velocityAt(track, i) {
  const t = track.times;
  const a = indexAt(track, t[i] - VEL_WIN_S);
  const b = Math.min(indexAt(track, t[i] + VEL_WIN_S) + 1, t.length - 1);
  const dt = t[b] - t[a];
  if (dt <= 0) return null;
  const p = track.position;
  return {
    x: (p[b * 3] - p[a * 3]) / dt,
    y: (p[b * 3 + 1] - p[a * 3 + 1]) / dt,
    z: (p[b * 3 + 2] - p[a * 3 + 2]) / dt,
  };
}

/**
 * PIP HUD 한 장.
 * @param {HTMLCanvasElement} canvas
 * @param {THREE.Camera} cam - 이 뷰의 1인칭 카메라 (matrixWorld 갱신된 상태)
 * @param {Object} ctx2 - {state, foeState, track, callsign, firing}
 */
const TEAM_TEXT = { blue: "#8fc0ff", red: "#ff9d8d" };

export function drawPipHud(canvas, cam,
  { state, foeState, track, callsign, team, mine }) {
  const cssW = canvas.clientWidth;
  const cssH = canvas.clientHeight;
  if (cssW < 8 || cssH < 8) return;
  const dpr = Math.min(window.devicePixelRatio, 2);
  if (canvas.width !== Math.round(cssW * dpr)) {
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  }
  const g = canvas.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, cssW, cssH);

  const i = state.index;
  const dead = state.health !== null && state.health <= 0;
  g.font = "500 11px Consolas, monospace";
  g.textBaseline = "middle";
  g.lineWidth = 1.25;
  // 위성 영상 위에서도 읽히도록 전 심볼에 어두운 외곽 그림자
  g.shadowColor = "rgba(0,0,0,0.85)";
  g.shadowBlur = 3;
  g.strokeStyle = dead ? "#9aa4b0" : GREEN;
  g.fillStyle = g.strokeStyle;

  drawPitchLadder(g, cam, state, cssW, cssH);
  drawFpm(g, cam, state, track, i, cssW, cssH);
  drawGunReticle(g, cam, state, cssW, cssH);
  drawTd(g, cam, state, foeState, track, i, cssW, cssH);
  drawTapes(g, track, i, state, cssW, cssH);
  drawReadouts(g, track, i, state, { callsign, team, mine }, cssW, cssH, dead);
  g.shadowBlur = 0;
  drawDamageVignette(g, track, i, cssW, cssH);
}

// ── 피치 사다리 ──────────────────────────────────────────────────────
// 기수 방위(yaw) 를 담은 수직면에 10° 간격 바. 오름=실선, 내림=파선(F-16 관례).
// 바의 양 끝을 방위 ±10° 두 점으로 잡아 투영하므로 롤이 저절로 실린다.
function drawPitchLadder(g, cam, s, w, h) {
  const point = (pitchDeg, dAz) => {
    const p = ladderPoint(s, pitchDeg, dAz);
    return project(cam, p.x, p.y, p.z, w, h);
  };

  for (let p = -80; p <= 80; p += 10) {
    const half = p === 0 ? 26 : 14;   // 수평선은 길게
    const a = point(p, -half);
    const b = point(p, half);
    if (a.behind || b.behind) continue;
    // 화면 밖 바는 건너뛴다(양끝 모두 밖)
    if ((a.y < -40 && b.y < -40) || (a.y > h + 40 && b.y > h + 40)) continue;

    g.save();
    g.setLineDash(p < 0 ? [5, 4] : []);
    const gap = p === 0 ? 0 : 0.16;   // 중앙을 비워 FPM 을 가리지 않게
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const dx = (b.x - a.x) / 2, dy = (b.y - a.y) / 2;
    g.beginPath();
    if (gap > 0) {
      g.moveTo(a.x, a.y); g.lineTo(mx - dx * gap, my - dy * gap);
      g.moveTo(mx + dx * gap, my + dy * gap); g.lineTo(b.x, b.y);
    } else {
      g.moveTo(a.x, a.y); g.lineTo(b.x, b.y);
    }
    g.stroke();
    g.setLineDash([]);
    // 눈금 끝을 수평선 쪽으로 꺾어(F-16 관례) 위/아래를 구분
    const tick = p === 0 ? 0 : (p > 0 ? 6 : -6);
    if (tick) {
      const nx = -dy, ny = dx;                       // 바에 수직
      const nl = Math.hypot(nx, ny) || 1;
      for (const e of [a, b]) {
        g.beginPath();
        g.moveTo(e.x, e.y);
        g.lineTo(e.x + (nx / nl) * tick, e.y + (ny / nl) * tick);
        g.stroke();
      }
    }
    if (p !== 0) {
      g.save();
      g.translate(b.x + 6, b.y);
      g.rotate(Math.atan2(dy, dx));
      g.textAlign = "left";
      g.fillText(String(Math.abs(p)), 0, 0);
      g.restore();
    }
    g.restore();
  }
}

// ── FPM (비행경로 마커) ──────────────────────────────────────────────
// 속도 벡터가 찍히는 곳 = 지금 기체가 실제로 가고 있는 방향.
// 건 크로스(중앙)와의 차이가 곧 AOA 다.
function drawFpm(g, cam, s, track, i, w, h) {
  const v = velocityAt(track, i);
  if (!v) return;
  const n = Math.hypot(v.x, v.y, v.z) || 1;
  const p = project(cam, s.x + (v.x / n) * FAR, s.y + (v.y / n) * FAR,
    s.z + (v.z / n) * FAR, w, h);
  if (p.behind || p.x < 0 || p.x > w || p.y < 0 || p.y > h) return;

  const r = 5;
  g.beginPath();
  g.arc(p.x, p.y, r, 0, Math.PI * 2);
  g.moveTo(p.x - r, p.y); g.lineTo(p.x - r - 7, p.y);   // 좌익
  g.moveTo(p.x + r, p.y); g.lineTo(p.x + r + 7, p.y);   // 우익
  g.moveTo(p.x, p.y - r); g.lineTo(p.x, p.y - r - 5);   // 수직미익
  g.stroke();
}

// ── 건 크로스 + 피퍼 ────────────────────────────────────────────────
// 카메라가 기수축을 보므로 보어사이트 = 화면 정중앙 = ATA 0.
// 피퍼 원 = 2°(최대 피해). 사격 중이면 굵게·경고색.
function drawGunReticle(g, cam, s, w, h) {
  const cx = w / 2, cy = h / 2;
  g.save();
  if (s.inWez) { g.strokeStyle = WARN; g.lineWidth = 2; }

  g.beginPath();                                   // 건 크로스
  g.moveTo(cx - 11, cy); g.lineTo(cx - 4, cy);
  g.moveTo(cx + 4, cy); g.lineTo(cx + 11, cy);
  g.moveTo(cx, cy - 11); g.lineTo(cx, cy - 4);
  g.moveTo(cx, cy + 4); g.lineTo(cx, cy + 11);
  g.stroke();

  g.beginPath();                                   // 2° 피퍼
  g.arc(cx, cy, Math.max(angleRadius(cam, PIPPER_DEG, h), 3), 0, Math.PI * 2);
  g.stroke();
  g.restore();
}

// ── TD 박스 (목표 지시기) ────────────────────────────────────────────
// 적기를 상자로 감싸고 거리[ft]를 붙인다. 사격창 안이면 경고색 + GUN 표시.
// 상자가 화면 밖이면 가장자리에 방향 화살표로 대신한다(놓친 방향을 알려준다).
function drawTd(g, cam, s, foe, track, i, w, h) {
  if (!foe) return;
  const p = project(cam, foe.x, foe.y, foe.z, w, h);
  const dist = attrAt(track, "Distance", i);
  const ata = attrAt(track, "ATA", i);
  const onScreen = !p.behind && p.x > 6 && p.x < w - 6 && p.y > 6 && p.y < h - 6;

  g.save();
  if (s.inWez) g.strokeStyle = g.fillStyle = WARN;

  if (onScreen) {
    // 거리에 따라 상자 크기를 바꿔 원근감을 준다 (가까울수록 크게)
    const box = Math.max(7, Math.min(26, 12000 / Math.max(dist ?? 3000, 300)));
    g.strokeRect(p.x - box, p.y - box, box * 2, box * 2);
    g.textAlign = "center";
    if (typeof dist === "number") {
      g.fillText(`${Math.round(dist)}`, p.x, p.y + box + 9);
    }
  } else {
    // 화면 밖 — 중심에서 목표 방향으로 가장자리에 화살표
    const dx = p.behind ? -(p.x - w / 2) : p.x - w / 2;
    const dy = p.behind ? -(p.y - h / 2) : p.y - h / 2;
    const ang = Math.atan2(dy, dx);
    const rx = w / 2 - 16, ry = h / 2 - 16;
    const t = Math.min(rx / Math.abs(Math.cos(ang) || 1e-6),
      ry / Math.abs(Math.sin(ang) || 1e-6));
    const ax = w / 2 + Math.cos(ang) * t;
    const ay = h / 2 + Math.sin(ang) * t;
    g.save();
    g.translate(ax, ay);
    g.rotate(ang);
    g.beginPath();
    g.moveTo(7, 0); g.lineTo(-5, -5); g.lineTo(-5, 5); g.closePath();
    g.fill();
    g.restore();
  }

  if (s.inWez) {
    g.textAlign = "center";
    g.font = "700 13px Consolas, monospace";
    g.fillText("GUN", w / 2, h / 2 - 26);
  }
  g.restore();

  // ATA 는 사격 판정의 핵심 각도 — 숫자로도 남긴다 (맨 아래 한 줄에 모아 둔다)
  g.textAlign = "center";
  g.fillText(`ATA ${typeof ata === "number" ? ata.toFixed(0) : "–"}°`,
    w / 2, h - 10);
}

// ── 속도/고도/방위 테이프 ────────────────────────────────────────────
function drawTapes(g, track, i, s, w, h) {
  const casMs = attrAt(track, "CAS", i);
  const cas = typeof casMs === "number" ? casMs * MPS_TO_KT : null;
  const altFt = track.position[i * 3 + 2] * M_TO_FT;
  const hdg = attrAt(track, "HDG", i);

  tape(g, { x: 34, y0: h * 0.28, y1: h * 0.72, value: cas,
    step: 10, labelEvery: 50, pxPerUnit: 0.55, side: "left" });
  // 고도 눈금은 실기 관례대로 **100ft 단위**로 찍는다(21,000ft → 210).
  // 전체 자릿수로 찍으면 폭이 넘쳐 PIP 가장자리에서 잘린다.
  tape(g, { x: w - 34, y0: h * 0.28, y1: h * 0.72, value: altFt,
    step: 250, labelEvery: 1000, pxPerUnit: 0.022, side: "right",
    tickLabel: (v) => String(Math.round(v / 100)) });

  // 방위 테이프는 실기와 같이 **아래쪽**. 위에 두면 호출부호 줄과 겹친다.
  // 캐럿(위 6px)·눈금·숫자(아래 13px)를 합쳐 h-46 ~ h-27 을 쓴다 → 맨 아래 수치 줄과 분리.
  if (typeof hdg === "number") headingTape(g, hdg, w, h - 40);
}

// 세로 테이프 한 개. value 를 중앙에 두고 위아래로 눈금이 흐른다.
function tape(g, { x, y0, y1, value, step, labelEvery, pxPerUnit, side, tickLabel }) {
  const mid = (y0 + y1) / 2;
  g.save();
  g.beginPath();
  g.moveTo(x, y0); g.lineTo(x, y1);
  g.stroke();
  if (value === null || !Number.isFinite(value)) { g.restore(); return; }

  const span = (y1 - y0) / 2 / pxPerUnit;
  const first = Math.ceil((value - span) / step) * step;
  g.textAlign = side === "left" ? "right" : "left";
  for (let v = first; v <= value + span; v += step) {
    const y = mid - (v - value) * pxPerUnit;
    const major = Math.abs(v % labelEvery) < 1e-6;
    const len = major ? 7 : 4;
    g.beginPath();
    g.moveTo(x, y);
    g.lineTo(side === "left" ? x - len : x + len, y);
    g.stroke();
    if (major) {
      g.fillText(tickLabel ? tickLabel(v) : String(Math.round(v)),
        side === "left" ? x - 10 : x + 10, y);
    }
  }
  // 현재값 박스
  const label = String(Math.round(value));
  const tw = g.measureText(label).width + 8;
  const bx = side === "left" ? x + 2 : x - 2 - tw;
  g.clearRect(bx, mid - 8, tw, 16);
  g.strokeRect(bx, mid - 8, tw, 16);
  g.textAlign = "center";
  g.fillText(label, bx + tw / 2, mid);
  g.restore();
}

// 방위 테이프 — 5° 눈금, 10° 마다 두 자리 숫자(F-16 관례: 270° → 27).
// 눈금은 기준선 아래로, 숫자는 위로, 현재 방위 캐럿은 기준선 위에서 아래를 가리킨다.
function headingTape(g, hdg, w, y) {
  const cx = w / 2;
  const pxPerDeg = 2.2;
  const span = (w / 2 - 40) / pxPerDeg;
  g.save();
  g.textAlign = "center";
  const first = Math.ceil((hdg - span) / 5) * 5;
  for (let d = first; d <= hdg + span; d += 5) {
    const x = cx + (d - hdg) * pxPerDeg;
    const major = ((d % 10) + 10) % 10 === 0;
    g.beginPath();
    g.moveTo(x, y); g.lineTo(x, y + (major ? 6 : 3));
    g.stroke();
    if (major) {
      const t = ((Math.round(d) % 360) + 360) % 360;
      // 숫자는 눈금 **아래** — 위는 캐럿 자리다(겹치면 중앙 숫자가 뭉갠다)
      g.fillText(String(t / 10).padStart(2, "0"), x, y + 13);
    }
  }
  g.beginPath();                                   // 현재 방위 캐럿(눈금 위)
  g.moveTo(cx, y); g.lineTo(cx - 4, y - 6); g.lineTo(cx + 4, y - 6);
  g.closePath();
  g.fill();
  g.restore();
}

// ── 피격 비네트 ─────────────────────────────────────────────────────
// **실제 HP 감소**로 판정한다 — 상대의 InWEZ 로 대신하면 사격창에 들었지만 아직
// 안 깎인 순간에도 붉어져서 "맞고 있다" 는 신호가 헐거워진다.
// 깜빡임 위상은 경기 시계로만 만든다(벽시계·난수 금지 — 같은 판은 항상 같은 화면).
const DMG_WIN_S = 0.35;   // 이 안에 HP 가 줄었으면 피격 중
const DMG_PERIOD_S = 0.4; // 깜빡임 주기

function drawDamageVignette(g, track, i, w, h) {
  const now = attrAt(track, "Health", i);
  const prev = attrAt(track, "Health", indexAt(track, track.times[i] - DMG_WIN_S));
  if (typeof now !== "number" || typeof prev !== "number") return;
  const lost = prev - now;
  if (lost <= 1e-6) return;

  // 초당 50HP 가 최대 피해율(RULEBOOK §4) — 그 비율로 세기를 잡는다
  const rate = Math.min(lost / DMG_WIN_S / 50, 1);
  const pulse = 0.55 + 0.45 * Math.sin((track.times[i] / DMG_PERIOD_S) * Math.PI * 2);
  const alpha = 0.20 + 0.42 * rate * pulse;

  const grad = g.createRadialGradient(
    w / 2, h / 2, Math.min(w, h) * 0.22,
    w / 2, h / 2, Math.hypot(w, h) / 2);
  grad.addColorStop(0, "rgba(255,32,24,0)");
  grad.addColorStop(1, `rgba(255,32,24,${alpha.toFixed(3)})`);
  g.save();
  g.fillStyle = grad;
  g.fillRect(0, 0, w, h);
  g.restore();
}

// ── 모서리 수치 ─────────────────────────────────────────────────────
function drawReadouts(g, track, i, s, { callsign, team, mine }, w, h, dead) {
  const nz = attrAt(track, "Nz", i);
  const aoa = attrAt(track, "AOA", i);
  const hp = s.health ?? 0;

  g.save();
  g.textAlign = "left";
  // 진영 표시 — 같은 로스터를 양 진영으로 다 돌리기 때문에 우리 기체가 어느 날은
  // BLUE, 어느 날은 RED 다. 좌/우 자리만으로는 알 수 없으므로 여기서 못 박는다.
  let x = 8;
  if (team) {
    g.fillStyle = TEAM_TEXT[team] ?? GREEN;
    const tag = team.toUpperCase();
    g.font = "700 11px Consolas, monospace";
    g.fillText(tag, x, 12);
    x += g.measureText(tag).width + 6;
    g.font = "500 11px Consolas, monospace";
  }
  g.fillStyle = dead ? "#9aa4b0" : GREEN;
  g.fillText(callsign ?? "", x, 12);
  if (mine) {
    x += g.measureText(callsign ?? "").width + 6;
    g.fillStyle = "#ffd23c";
    g.fillText("★MINE", x, 12);
    g.fillStyle = dead ? "#9aa4b0" : GREEN;
  }

  // HP — 격추 임박이 한눈에 보여야 한다
  g.fillStyle = hp > 50 ? g.fillStyle : hp > 20 ? "#e8b93e" : WARN;
  g.fillText(`HP ${hp.toFixed(0)}`, 8, 26);
  g.fillStyle = dead ? "#9aa4b0" : GREEN;

  // 맨 아래 한 줄에 좌=AOA·G, 가운데=ATA(drawTd), 우=접근율. 방위 테이프와 층이 다르다.
  const bits = [];
  if (typeof aoa === "number") bits.push(`AOA ${aoa.toFixed(1)}`);
  if (typeof nz === "number") bits.push(`${nz.toFixed(1)}G`);
  if (bits.length) g.fillText(bits.join("  "), 8, h - 10);

  g.textAlign = "right";
  const closure = attrAt(track, "ClosureRate", i);
  if (typeof closure === "number") {
    g.fillText(`Vc ${Math.round(closure)}`, w - 8, h - 10);
  }
  // 전술 노드는 위쪽 — 아래는 비행 상태, 위는 정체·판단으로 층을 나눈다
  const l1 = parsePacked(attrAt(track, "L1", i));
  if (l1.node) g.fillText(l1.node, w - 8, 12);

  if (dead) {
    g.textAlign = "center";
    g.font = "700 16px Consolas, monospace";
    g.fillStyle = "#9aa4b0";
    g.fillText("DESTROYED", w / 2, h / 2 + 40);
  }
  g.restore();
}

export { WEZ_DEG, PIPPER_DEG, angleRadius, FAR, ladderPoint };

/**
 * 피치 사다리 바의 한 끝점 방향 (drawPitchLadder 와 같은 식 — 테스트가 이걸 쓴다).
 * 기수 방위 psi 를 담은 수직면에서 pitch 만큼 올린 뒤 방위로 dAz 만큼 벌린 점.
 */
function ladderPoint(s, pitchDeg, dAzDeg) {
  const th = pitchDeg * DEG;
  const az = s.yaw * DEG + dAzDeg * DEG;
  return {
    x: s.x + Math.sin(az) * Math.cos(th) * FAR,
    y: s.y + Math.cos(az) * Math.cos(th) * FAR,
    z: s.z + Math.sin(th) * FAR,
  };
}
