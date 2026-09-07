// 지면 지도 배치 + 1인칭 카메라 기하 검증.
// 실행: node tools/acmi_viewer/tests/test_map_geo.mjs
//
// 왜 필요한가: 이 두 곳은 브라우저에서만 눈에 보이는데 부호 하나(동/서, 남/북,
// 텍스처 상하, 기수축)만 틀려도 "그럴듯하게" 잘못 그려진다. 헤드리스 크롬은 이
// 뷰어를 렌더하지 못하므로(WebGL+GLTF 적재 정지), 수학만 떼어 여기서 못 박는다.
import { readFileSync, writeFileSync, unlinkSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const HERE = dirname(fileURLToPath(import.meta.url));
const STATIC = join(HERE, "..", "static");
const ROOT = join(HERE, "..", "..", "..");

// 브라우저는 importmap 으로 "three" 를 벤더 파일에 붙이지만 노드에는 그 장치가
// 없다. 실제 배포 소스를 그대로 검증하려고, 임포트 지정자만 바꾼 사본을 같은
// 폴더에 잠깐 두고 불러온다(상대 임포트가 살아 있어야 하므로 static/ 안에).
async function importWithThree(name) {
  const shim = join(STATIC, `.__test_${name}`);
  const src = readFileSync(join(STATIC, name), "utf-8")
    .replace(/from "three"/g, 'from "./vendor/three.module.min.js"');
  writeFileSync(shim, src);
  try {
    return await import(`file://${shim.replaceAll("\\", "/")}`);
  } finally {
    if (existsSync(shim)) unlinkSync(shim);
  }
}

const THREE = await import(
  `file://${join(STATIC, "vendor", "three.module.min.js").replaceAll("\\", "/")}`);
const { buildMapPlane, buildGraticule } = await importWithThree("map.js");
const { placeEye, PIP_FOV_DEG, EYE_OFFSET } = await importWithThree("firstperson.js");

const DEG = Math.PI / 180;
const EARTH_RADIUS_M = 6378137.0; // acmi.js buildTracks 와 같은 값이어야 한다

// ── 1. 지도 평면 배치 ────────────────────────────────────────────────
// 지도가 없으면(각자 굽는 산출물) 이 절은 건너뛴다.
const metaPath = join(STATIC, "maps", "index.json");
if (!existsSync(metaPath)) {
  console.log("skip: static/maps/index.json 없음 (make_map.py 로 생성)");
} else {
  const meta = JSON.parse(readFileSync(metaPath, "utf-8"));
  // 씬 원점은 두 기체 첫 샘플의 중점 — 지도 중심과 일부러 다르게 잡아 본다.
  const refLat = 37.0, refLon = 127.0;
  const plane = buildMapPlane(meta, null, refLat, refLon);

  // 평면 중심은 지도 중심 위경도를 acmi.js 와 같은 식으로 투영한 자리여야 한다.
  const wantEast =
    (meta.center_lon - refLon) * DEG * EARTH_RADIUS_M * Math.cos(refLat * DEG);
  const wantNorth = (meta.center_lat - refLat) * DEG * EARTH_RADIUS_M;
  assert.ok(Math.abs(plane.position.x - wantEast) < 1e-6, "지도 중심 동서 배치");
  assert.ok(Math.abs(plane.position.y - wantNorth) < 1e-6, "지도 중심 남북 배치");
  assert.equal(plane.position.z, 0, "지도는 고도 0 평면 (평지 물리와 일치)");

  // 축척: 픽셀 크기 × m/px 가 평면 크기와 같아야 한다(엉뚱한 배율이면 여기서 깨진다)
  const p = plane.geometry.parameters;
  assert.ok(Math.abs(p.width - meta.width_px * meta.meters_per_pixel) < 1,
    `지도 가로 축척 ${p.width} vs ${meta.width_px * meta.meters_per_pixel}`);
  assert.ok(Math.abs(p.height - meta.height_px * meta.meters_per_pixel) < 1,
    "지도 세로 축척");

  // 그래티큘은 평면 밖으로 새지 않아야 한다 (경계 계산 부호 검증)
  const g = buildGraticule(meta, refLat, refLon).geometry.attributes.position;
  let maxX = 0, maxY = 0;
  for (let i = 0; i < g.count; i++) {
    maxX = Math.max(maxX, Math.abs(g.getX(i) - plane.position.x));
    maxY = Math.max(maxY, Math.abs(g.getY(i) - plane.position.y));
  }
  assert.ok(maxX <= p.width / 2 + 1, `그래티큘 가로 범위 ${maxX} ≤ ${p.width / 2}`);
  assert.ok(maxY <= p.height / 2 + 1, `그래티큘 세로 범위 ${maxY} ≤ ${p.height / 2}`);

  // 교전 원점(37N/127E)이 지도 안에 들어야 한다 — 아니면 빈 바탕만 보인다
  assert.ok(Math.abs(wantEast) < p.width / 2 && Math.abs(wantNorth) < p.height / 2,
    "교전 원점이 지도 범위 안");
  console.log(`OK: 지도 배치 ${(p.width / 1000).toFixed(1)}×${(p.height / 1000).toFixed(1)}km ` +
    `@ ${meta.center_lat}N ${meta.center_lon}E`);
}

// ── 2. 1인칭 카메라 정렬 ─────────────────────────────────────────────
// scene.js 와 같은 방식으로 자세 쿼터니언을 만든다 (기수 +Y, ZXY 오일러).
function attitude(rollDeg, pitchDeg, yawDeg) {
  return new THREE.Quaternion().setFromEuler(new THREE.Euler(
    pitchDeg * DEG, rollDeg * DEG, -yawDeg * DEG, "ZXY"));
}

const cam = new THREE.PerspectiveCamera(PIP_FOV_DEG, 1.5, 5, 500_000);
cam.up.set(0, 0, 1);

for (const [roll, pitch, yaw, label] of [
  [0, 0, 0, "북향 수평"],
  [0, 0, 90, "동향 수평"],
  [0, 30, 0, "기수 30° 상승"],
  [45, 10, 210, "뱅크 45°"],
  [180, 0, 0, "배면비행"],
]) {
  const q = attitude(roll, pitch, yaw);
  const pos = { x: 1000, y: -2000, z: 5000 };
  placeEye(cam, q, pos);
  cam.updateMatrixWorld(true);

  // (a) 시선 = 기체 기수(로컬 +Y). 이게 틀리면 옆이나 뒤를 보게 된다.
  const nose = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
  const look = cam.getWorldDirection(new THREE.Vector3());
  assert.ok(look.distanceTo(nose) < 1e-6, `${label}: 시선=기수 (${look.toArray()})`);

  // (b) 화면 위쪽 = 기체 상방(로컬 +Z). 배면비행이 화면에서도 뒤집혀야 한다.
  const up = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
  const camUp = new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion);
  assert.ok(camUp.distanceTo(up) < 1e-6, `${label}: 화면상방=기체상방`);

  // (c) 눈은 CG 보다 기수쪽으로 나가 있다 (동체 내부 시점 방지)
  const ahead = new THREE.Vector3(cam.position.x - pos.x,
    cam.position.y - pos.y, cam.position.z - pos.z).dot(nose);
  assert.ok(Math.abs(ahead - EYE_OFFSET.y) < 1e-6,
    `${label}: 눈 전방 오프셋 ${ahead}`);
}
// 배면비행에서 화면 상방이 실제로 뒤집히는지 하나만 못 박아 둔다
placeEye(cam, attitude(180, 0, 0), { x: 0, y: 0, z: 0 });
assert.ok(new THREE.Vector3(0, 1, 0).applyQuaternion(cam.quaternion).z < -0.99,
  "배면비행 시 화면 상방이 지면을 향해야 한다");
console.log(`OK: 1인칭 카메라 정렬 5자세 (FOV ${PIP_FOV_DEG}°)`);

// ── 3. HUD 각도 심볼이 FOV 와 맞물리는지 ─────────────────────────────
// 피퍼 반경은 화면 픽셀로 찍히므로 FOV 를 바꾸면 같이 변해야 한다. 안 그러면
// "2° 피퍼" 가 거짓말이 된다.
const { angleRadius, PIPPER_DEG, WEZ_DEG } = await importWithThree("pip_hud.js");
const H = 300;
const fakeCam = { fov: PIP_FOV_DEG };
for (const deg of [PIPPER_DEG, 10, WEZ_DEG]) {
  const want = (H / 2) * Math.tan(deg * DEG) / Math.tan((PIP_FOV_DEG / 2) * DEG);
  assert.ok(Math.abs(angleRadius(fakeCam, deg, H) - want) < 1e-9,
    `${deg}° 반경`);
}
// 사격창(30°)이 세로 시야 안에 들어와야 조준 상태를 놓치지 않는다
assert.ok(WEZ_DEG < PIP_FOV_DEG / 2,
  `사격창 ${WEZ_DEG}° 가 세로 시야 ±${PIP_FOV_DEG / 2}° 밖 — 1인칭에서 잘린다`);
assert.ok(angleRadius(fakeCam, WEZ_DEG, H) < H / 2, "30° 가 화면 세로 안");
console.log(`OK: HUD 각도 심볼 ↔ FOV ${PIP_FOV_DEG}° 정합 (사격창 ${WEZ_DEG}° 포함)`);

// ── 3b. 피치 사다리·수평선 투영 ──────────────────────────────────────
// 부호가 하나만 뒤집혀도 "그럴듯하게" 틀린다: 상승인데 사다리가 내려간다든지,
// 롤이 반대로 실린다든지. 실제 카메라로 투영해 픽셀 위치를 못 박는다.
const { project, ladderPoint } = await importWithThree("pip_hud.js");
const W = 440, HH = 300;
const pipCam = new THREE.PerspectiveCamera(PIP_FOV_DEG, W / HH, 5, 500_000);
pipCam.up.set(0, 0, 1);

function screenLadder(rollDeg, pitchDeg, yawDeg, barPitch, dAz) {
  const s = { x: 0, y: 0, z: 5000, yaw: yawDeg };
  placeEye(pipCam, attitude(rollDeg, pitchDeg, yawDeg), s);
  pipCam.updateMatrixWorld(true);
  pipCam.updateProjectionMatrix();
  const p = ladderPoint(s, barPitch, dAz);
  return project(pipCam, p.x, p.y, p.z, W, HH);
}

// 수평비행: 수평선(0° 바)이 화면 정중앙
let h0 = screenLadder(0, 0, 0, 0, 0);
assert.ok(Math.abs(h0.y - HH / 2) < 0.5, `수평선이 중앙: y=${h0.y}`);
assert.ok(Math.abs(h0.x - W / 2) < 0.5, `수평선이 중앙: x=${h0.x}`);

// 기수 10° 올리면 수평선은 **아래로** 내려간다 (화면 y 증가)
h0 = screenLadder(0, 10, 0, 0, 0);
const want10 = angleRadius(pipCam, 10, HH);
assert.ok(h0.y > HH / 2, `상승 시 수평선이 아래로: y=${h0.y}`);
assert.ok(Math.abs(h0.y - (HH / 2 + want10)) < 1.0,
  `상승 10° 수평선 위치 ${h0.y} vs ${HH / 2 + want10}`);

// 수평비행 중 +10° 바는 화면 위쪽 (y < 중앙)
const up10 = screenLadder(0, 0, 0, 10, 0);
assert.ok(up10.y < HH / 2 - 5, `+10° 바가 위쪽: y=${up10.y}`);
const dn10 = screenLadder(0, 0, 0, -10, 0);
assert.ok(dn10.y > HH / 2 + 5, `−10° 바가 아래쪽: y=${dn10.y}`);

// 롤 45°: 수평선 바가 화면에서 45° 기울어야 한다 (좌우 끝점 기울기로 확인)
const la = screenLadder(45, 0, 0, 0, -14);
const lb = screenLadder(45, 0, 0, 0, 14);
const tilt = Math.atan2(lb.y - la.y, lb.x - la.x) / DEG;
assert.ok(Math.abs(Math.abs(tilt) - 45) < 3, `롤 45° 수평선 기울기 ${tilt.toFixed(1)}°`);
// 오른쪽 뱅크면 수평선 오른쪽 끝이 올라간다(화면 y 감소)
assert.ok(lb.y < la.y, `우뱅크에서 수평선 우측이 위로 (la=${la.y}, lb=${lb.y})`);

// 동쪽(090)을 향해도 수평선은 중앙 — 방위와 무관해야 한다
const east = screenLadder(0, 0, 90, 0, 0);
assert.ok(Math.abs(east.y - HH / 2) < 0.5 && Math.abs(east.x - W / 2) < 0.5,
  "동향에서도 수평선 중앙");
console.log("OK: 피치 사다리 투영 (수평선·±10°·롤 45°·방위 무관)");

// ── 4. 실제 녹화가 지도 범위 안에 들어오는지 ─────────────────────────
if (existsSync(metaPath)) {
  const { parseACMI, buildTracks } = await import(
    `file://${join(STATIC, "acmi.js").replaceAll("\\", "/")}`);
  const meta = JSON.parse(readFileSync(metaPath, "utf-8"));
  const sample = join(ROOT, "replays", "canon", "roster_t3full_150",
    "vs_anchor_ace_blue.acmi");
  if (!existsSync(sample)) {
    console.log("skip: 표본 녹화 없음");
  } else {
    const { blue, red, refLat, refLon } = buildTracks(
      parseACMI(readFileSync(sample, "utf-8")));
    const plane = buildMapPlane(meta, null, refLat, refLon);
    const p = plane.geometry.parameters;
    for (const [name, tr] of [["blue", blue], ["red", red]]) {
      for (let i = 0; i < tr.position.length; i += 3) {
        const dx = Math.abs(tr.position[i] - plane.position.x);
        const dy = Math.abs(tr.position[i + 1] - plane.position.y);
        assert.ok(dx < p.width / 2 && dy < p.height / 2,
          `${name} 트랙이 지도 밖 (${(dx / 1000).toFixed(1)}, ${(dy / 1000).toFixed(1)}) km`);
      }
    }
    console.log("OK: 표본 녹화 전 구간이 지도 범위 안");
  }
}
