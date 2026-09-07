// three.js 3D 씬 — ENU(z-up) 좌표계에서 청/적 항공기·항적·WEZ 원뿔을 렌더.
import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { indexAt, attrAt, parsePacked } from "./acmi.js";
import { loadF16, buildF16 } from "./f16.js";
import {
  loadMapMeta, loadMapTexture, buildMapPlane, buildGraticule, buildGridGround,
  buildSeaGround, buildCloudLayer,
} from "./map.js";
import { PIP_FOV_DEG, placeEye } from "./firstperson.js";

const DEG = Math.PI / 180.0;
// 밝은 배경용 팔레트 — 상면=팀색, 하면(belly)=팀색 밝은 톤 (배면비행 식별 + 팀 유지).
// 하면 톤은 채도를 남겨 둔다: 너무 옅으면 음영에서 회색으로 읽혀 격추색과 헷갈린다.
const COLORS = {
  blue: 0x1d5fd6, red: 0xd63a3a, dead: 0x9aa4b0,
  belly: { blue: 0x5b9bff, red: 0xff7a7a },
};
// 리프트 벡터 색 = L2 gmode (tacview addon 팔레트를 밝은 배경용으로 명도 조정)
const GMODE_COLORS = {
  regulate: 0x2fae5b, initial_pull: 0xd98d00, max_g: 0xd63a3a,
  track_lock: 0x0e9ab8, energy_backoff: 0xc8a000,
};
const GMODE_FALLBACK = 0x8a94a3;
const SKY_COLOR = 0x5b8fd0;       // 천정
const HORIZON_COLOR = 0xcfe0ee;   // 지평 헤이즈 (SKY_HAZE 와 같은 값 — 경계 은폐)
const GUN_COLOR = 0xffd23c;       // 기총 예광 (ACMI Beam 과 같은 의미)
const GUN_RANGE_M = 1000.0;       // acmi.py GunVisualizer Length=1000 과 동일
const LOS_COLOR = 0x47566b;       // 평시 (addon 흰색은 밝은 배경에서 안 보임)
const LOS_WEZ_COLOR = 0xd63a3a;   // 어느 쪽이든 InWEZ
const VELVEC_LEN = 300;           // 속도 벡터 길이 [m] (addon과 동일)
const LIFTVEC_LEN = 260;          // 리프트 벡터 길이 [m]
const PARAMS = new URLSearchParams(location.search);
// 기본은 원본 F-16 도장(위장·마킹). 기체 자체로는 청/적이 구분되지 않으므로
// **항적선 색이 유일한 팀 식별 단서**다 — 그래서 항적을 진한 팀색 실선으로 둔다.
// 기체까지 팀색으로 칠하고 싶으면 ?skin=team.
const REAL_SKIN = (PARAMS.get("skin") ?? "real") !== "team";
// 조준점 마커(와이어프레임 구)는 기본 끔 — 기체 앞에 늘 떠 있어 시야를 어지럽힌다.
// L1 pursuit·L2 aim 을 눈으로 확인해야 할 때만 ?aim=1.
const SHOW_AIM = PARAMS.get("aim") === "1";

export class ReplayScene {
  constructor(container) {
    this.container = container;
    // 로그 깊이 버퍼 — 씬이 수백 km 인데 콕핏 뷰는 수 m 앞을 본다. 선형 깊이로는
    // 원거리 정밀도가 바닥나 지면과 배경 평면이 서로 뚫고 나온다(줄무늬 아티팩트).
    this.renderer = new THREE.WebGLRenderer({
      antialias: true, logarithmicDepthBuffer: true,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(HORIZON_COLOR);
    // 원경을 지평 색으로 흐려 지면 평면이 끊기는 경계를 감춘다(수평선이 생긴다)
    this.scene.fog = new THREE.FogExp2(HORIZON_COLOR, 1.1e-5);
    this.scene.add(buildSky());

    this.camera = new THREE.PerspectiveCamera(55, 1, 10, 500_000);
    this.camera.up.set(0, 0, 1); // ENU z-up
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;

    this.scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    // 태양광은 하늘의 태양과 **같은 방향**에서 와야 한다 — 어긋나면 밝은 쪽과
    // 그림자 지는 쪽이 따로 놀아 입체감이 거짓말이 된다.
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.05);
    sun.position.copy(sunDirection()).multiplyScalar(1000);
    this.scene.add(sun);
    // 아래쪽 보조광 — 없으면 기체 하면이 그늘로 떨어져 회색(=격추 색)처럼 보인다.
    // 하면의 연한 팀톤이 배면비행 식별 단서이므로 그 톤이 살아 있어야 한다.
    const fill = new THREE.DirectionalLight(0xffffff, 0.45);
    fill.position.set(-1, -1, -2);
    this.scene.add(fill);

    this.cameraMode = "both";
    // 지면 종류 — 위성 지도는 고주파 무늬라 항적·기체와 주목을 다툰다. 집중해서
    // 기하를 읽을 때는 격자가 낫다는 현장 의견이 있어 고를 수 있게 했다.
    // 기본은 바다 — 엔진 물리가 평지이고 하드덱이 해수면 기준이라, 평평하면서
    // 실사인 유일한 지면이다. 계측이 목적이면 상단 셀렉트로 격자를 고른다.
    // sandbox 된 iframe(웹 임베드)은 불투명 출처라 localStorage 접근이 SecurityError 다.
    // 취향 기억은 있으면 좋은 것일 뿐이므로 못 읽으면 조용히 기본값으로 간다.
    let savedGround = null;
    try { savedGround = localStorage.getItem("acmiGround"); } catch { /* sandbox */ }
    this.groundMode = PARAMS.get("ground") || savedGround || "sea";
    this.f16 = null; // loadAssets() 성공 시 부품 목록, 실패 시 null(절차적 형상 폴백)
    this.units = new Map(); // key: "blue"|"red" → {track, group, cone, trail, dropLine}
    this.mapMeta = null;    // loadAssets() 에서 채움, 없으면 격자 폴백
    this.mapTexture = null;

    // 1인칭 뷰 카메라 — 본 화면과 같은 씬을 scissor 뷰포트로 나눠 그린다.
    // (씬을 공유하므로 지오메트리·텍스처 업로드가 한 벌로 끝난다)
    this.pipCams = new Map();
    for (const key of ["blue", "red"]) {
      const cam = new THREE.PerspectiveCamera(PIP_FOV_DEG, 1.5, 5, 500_000);
      cam.up.set(0, 0, 1);
      this.pipCams.set(key, cam);
    }

    this._resize = () => {
      const w = container.clientWidth || window.innerWidth;
      const h = container.clientHeight || window.innerHeight;
      this.renderer.setSize(w, h);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    };
    window.addEventListener("resize", this._resize);
    this._resize();
  }

  /** 기체 모델·지면 지도 선적재 — setTracks 전에 한 번 부른다(둘 다 실패해도 진행).
   *
   * 적재는 **반드시 끝난다**. 예전에는 로더가 영영 정착하지 않으면(디코더가 멎는
   * 환경이 실제로 있다) 화면이 "로딩…" 에서 굳어 아무것도 볼 수 없었다. 이제
   * 시한을 두고 폴백한다 — 기체는 절차적 형상, 지면은 격자로 떨어질 뿐 재생은 된다. */
  async loadAssets() {
    const [f16, meta] = await Promise.all([
      withTimeout(loadF16(), "F-16 모델"),
      withTimeout(loadMapMeta(), "지도 메타"),
    ]);
    this.f16 = f16;
    if (meta) {
      const tex = await withTimeout(loadMapTexture(meta), "지도 텍스처");
      if (tex) { this.mapMeta = meta; this.mapTexture = tex; }
    }
  }

  /** 지면 종류 교체 — "map"(위성) / "grid"(계측 격자) / "plain"(무지). */
  setGroundMode(mode) {
    this.groundMode = mode;
    if (this.geo) this._buildGround();
  }

  /** 지면 레이어 재구성. setTracks·setGroundMode 양쪽에서 부른다. */
  _buildGround() {
    for (const o of this.groundLayers ?? []) this.scene.remove(o);
    this.groundLayers = [];
    this.sea = null;
    this.clouds = [];
    const { refLat, refLon } = this.geo;
    // 지도를 요청했는데 아직(또는 끝내) 없으면 격자로 떨어진다
    // 지도를 요청했는데 타일이 아직(또는 끝내) 없으면 바다로 떨어진다
    const mode = this.groundMode === "map" && !this.mapMeta ? "sea" : this.groundMode;

    // 배경 평면은 시계 밖까지 깔아 둔다 — 5,000m 상공의 진짜 수평선은 250km 밖이라
    // 지면이 그보다 먼저 끝나면 허공에 걸린 판때기로 보인다. 먼 쪽은 fog 가 지평
    // 색으로 녹여 수평선을 만든다. depthTest 를 꺼서 지도와의 z-fighting 을 원천 차단
    // (renderOrder 로 지도보다 먼저 그려지고, 깊이를 쓰지 않으니 지도가 항상 덮는다).
    const groundSize = Math.max(600_000, this.extent * 4);
    const backdrop = new THREE.Mesh(
      new THREE.PlaneGeometry(groundSize, groundSize),
      new THREE.MeshBasicMaterial({
        color: mode === "map" ? 0x7d8b76 : 0xe8edf3, // 지면 가장자리와 이어지는 톤
        depthTest: false, depthWrite: false,
      }),
    );
    backdrop.renderOrder = -3;
    this.groundLayers.push(backdrop);

    if (mode === "map") {
      this.groundLayers.push(
        buildMapPlane(this.mapMeta, this.mapTexture, refLat, refLon),
        buildGraticule(this.mapMeta, refLat, refLon),
      );
    } else if (mode === "grid") {
      this.groundLayers.push(buildGridGround(groundSize, HORIZON_COLOR));
    } else if (mode === "sea") {
      this.sea = buildSeaGround(groundSize, sunDirection(), HORIZON_COLOR);
      this.groundLayers.push(this.sea);
    }
    // 구름 — 교전 고도(12~25kft) **아래** 적운 갑판과 **위** 권운. 그 사이를 비우면
    // 교전을 가리지 않으면서 고도감·속도감이 난다.
    if (mode !== "plain") {
      const sky = Math.max(400_000, this.extent * 4);
      this.clouds = [
        buildCloudLayer(sky, 6000, {                       // 적운 갑판(아래)
          scale: 1 / 7000, cover: 0.50, softness: 0.26, opacity: 0.9,
          tint: 0xf7fbff, drift: 0.5,
        }),
        buildCloudLayer(sky, 32000, {                      // 권운(위) — 얇고 넓다
          scale: 1 / 26000, cover: 0.56, softness: 0.34, opacity: 0.42,
          tint: 0xffffff, drift: 1.2,
        }),
      ];
      this.groundLayers.push(...this.clouds);
    }
    this.scene.add(...this.groundLayers);
  }

  /** 트랙 2개 장착. wez: {maxRangeM, halfAngleDeg}, geo: {refLat, refLon} */
  setTracks(blue, red, wez, geo) {
    for (const unit of this.units.values()) {
      this.scene.remove(unit.group, unit.trail, unit.cone,
        unit.aim.marker, unit.aim.line, unit.velVec, unit.liftVec, unit.gun);
    }
    for (const o of this.groundLayers ?? []) this.scene.remove(o);
    this.groundLayers = [];
    if (this.los) this.scene.remove(this.los);
    this.units.clear();

    this.los = buildSegment(LOS_COLOR, 0.8);
    this.scene.add(this.los);

    const extent = trackExtent(blue, red);
    const displayLen = Math.min(Math.max(extent * 0.015, 60), 250);

    this.geo = geo;
    this.extent = extent;
    this._buildGround();

    for (const [key, track] of [["blue", blue], ["red", red]]) {
      const color = COLORS[key];
      const group = this.f16
        ? buildF16(this.f16, {
          color, bellyColor: COLORS.belly[key], displayLen, realSkin: REAL_SKIN,
        })
        : buildAircraft(color, COLORS.belly[key], displayLen);
      // WEZ 원뿔은 **기수(자세) 정렬** — 룰의 ATA 가 BEM 종축(boresight) 기준
      // (combat_geometry.ata_deg, 2026-07-17 교범 정합 전환)이므로.
      const cone = buildWezCone(color, wez);
      this.scene.add(cone);
      const trail = buildTrail(track, color);
      const dropLine = buildDropLine(color);
      group.add(dropLine);
      const aim = buildAimpoint(color);
      aim.marker.visible = aim.line.visible = SHOW_AIM;
      const velVec = buildSegment(color, 0.9);
      const liftVec = buildSegment(GMODE_FALLBACK, 0.9);
      const gun = buildGunBeam(GUN_COLOR);
      // 화염·베이퍼는 기체 자식 — 자세·축척을 그대로 따라간다(전장 1 정규화 기준).
      const flame = buildEngineFlame();
      // 노즐 출구는 기체 뒤 끝(-0.5)이 아니다 — 수평미익이 더 뒤로 나온다.
      // 모델 정점에서 실측한 배기 출구 위치(전장 정규화 좌표).
      flame.position.set(0, NOZZLE_Y, NOZZLE_Z);
      const vapor = buildVapor();
      group.add(flame, vapor);
      this.scene.add(group, trail, aim.marker, aim.line, velVec, liftVec, gun);
      this.units.set(key, { track, group, cone, trail, dropLine, aim,
        velVec, liftVec, gun, flame, vapor, displayLen });
    }

    // 초기 카메라: 두 기체 중점 상공 비스듬히.
    // ?dist=<m> 로 거리를 지정할 수 있다 — 화염·베이퍼 같은 근접 표현을 확인하거나
    // 근접 복기 화면을 캡처할 때 쓴다(기본은 전장이 다 들어오는 거리).
    const mid = midpoint(blue, red, 0);
    const want = parseFloat(PARAMS.get("dist"));
    const d = Number.isFinite(want) ? want : extent;
    this.controls.target.copy(mid);
    this.camera.position.set(
      mid.x + d * 0.7, mid.y - d * 0.7, mid.z + d * 0.5,
    );
    const cam = PARAMS.get("camera");
    if (["blue", "red", "both", "free"].includes(cam)) this.cameraMode = cam;
    this.controls.update();
  }

  setCameraMode(mode) {
    this.cameraMode = mode;
  }

  /** 시각 t의 상태를 씬에 반영. HUD용 보간 상태를 돌려준다. */
  update(t) {
    const states = {};
    for (const [key, unit] of this.units) {
      const s = sampleState(unit.track, t);
      states[key] = s;
      unit.group.position.set(s.x, s.y, s.z);
      // 기체 메시는 기수 +Y 기준: ZXY 순서로 heading→pitch→roll 적용
      unit.group.rotation.set(s.pitch * DEG, s.roll * DEG, -s.yaw * DEG, "ZXY");

      const dead = s.health !== null && s.health <= 0;
      setUnitColor(unit.group, dead ? COLORS.dead : COLORS[key],
        dead ? COLORS.dead : COLORS.belly[key]);
      unit.cone.material.opacity = s.inWez ? 0.18 : 0.04;
      unit.cone.visible = !dead;
      unit.cone.position.set(s.x, s.y, s.z);
      unit.cone.quaternion.copy(unit.group.quaternion);

      const abFrac = updateFlame(unit, s, dead, t);
      updateVapor(unit, s, dead, t);

      // 기총 예광 — 사격 중(InWEZ)에만. 축은 기수 = ACMI Beam 과 동일.
      unit.gun.visible = s.inWez && !dead;
      if (unit.gun.visible) {
        unit.gun.position.set(s.x, s.y, s.z);
        unit.gun.quaternion.copy(unit.group.quaternion);
      }

      // 항적 리본: 세그먼트당 인덱스 6개. 끝은 **노즐 뒤 + 화염 뒤**에서 시작하도록
      // 잘라 낸다 — 기체 위나 화염 속에서 리본이 솟으면 형상도 화염도 뭉갠다.
      const head = Math.max(s.index - trailHeadTrim(unit.track, s.index,
        unit.displayLen * (0.5 + FLAME_LEN_BASE + FLAME_LEN_AB * abFrac)), 0);
      unit.trail.geometry.setDrawRange(0, head * 6);
      updateTrailRibbon(unit.trail, unit.track, head, this.camera,
        this.renderer.domElement.clientHeight, t);
      // 고도 인지선: 기체 → 해수면 (group 로컬 좌표, 자세 회전 상쇄)
      updateDropLine(unit.dropLine, unit.group, s.z);
      updateVectors(unit, s, dead);
    }

    // 조준점 (tacview addon 정합): pursuit별 목표점 + aim_above 수직 오프셋
    if (this.units.size === 2) {
      for (const [key, foeKey] of [["blue", "red"], ["red", "blue"]]) {
        updateAimpoint(this.units.get(key), this.units.get(foeKey).track,
          states[key], states[foeKey], this.camera);
      }
      // LOS: 평시 회청색, 어느 쪽이든 사격 solution(InWEZ)이면 적색
      const b = states.blue, r = states.red;
      setSegment(this.los, b.x, b.y, b.z, r.x, r.y, r.z);
      this.los.material.color.setHex(
        b.inWez || r.inWez ? LOS_WEZ_COLOR : LOS_COLOR);
    }

    // 카메라 추적: 대상점만 갱신 (사용자 오빗 오프셋 유지)
    if (this.cameraMode !== "free" && this.units.size === 2) {
      const b = states.blue, r = states.red;
      const target =
        this.cameraMode === "blue" ? new THREE.Vector3(b.x, b.y, b.z)
        : this.cameraMode === "red" ? new THREE.Vector3(r.x, r.y, r.z)
        : new THREE.Vector3((b.x + r.x) / 2, (b.y + r.y) / 2, (b.z + r.z) / 2);
      const delta = target.clone().sub(this.controls.target);
      this.controls.target.copy(target);
      this.camera.position.add(delta);
    }
    this.controls.update();
    this.renderScene(states);
    return states;
  }

  /** 본 화면 + 1인칭 PIP 2개를 같은 캔버스에 scissor 로 나눠 그린다. */
  renderScene(states) {
    const canvas = this.renderer.domElement;
    const W = canvas.clientWidth;
    const H = canvas.clientHeight;

    this.renderer.setScissorTest(false);
    this.renderer.setViewport(0, 0, W, H);
    this.renderer.render(this.scene, this.camera);

    // scissor 를 켜면 clear 도 해당 사각형 안으로 제한된다 → 본 화면이 지워지지 않는다
    this.renderer.setScissorTest(true);
    for (const [key, cam] of this.pipCams) {
      const unit = this.units.get(key);
      const rect = pipRect(key);
      if (!unit || !rect) continue;

      placeEye(cam, unit.group.quaternion, states[key]);
      cam.aspect = rect.w / rect.h;
      cam.updateProjectionMatrix();

      // 이 뷰에서만 숨길 것 —
      //  · 자기 기체·WEZ 원뿔·속도/리프트 벡터·기총 예광: 눈에 붙어 있어 화면을 덮는다
      //  · **상대의** 조준점 마커·연결선: 상대가 나를 겨누면 그 마커가 내 콕핏에
      //    얹혀 커다란 와이어프레임 공으로 보인다. 내 조준점은 앞의 적기에 찍히므로 유지.
      const foe = this.units.get(key === "blue" ? "red" : "blue");
      const hidden = [unit.group, unit.cone, unit.velVec, unit.liftVec, unit.gun,
        foe?.aim.marker, foe?.aim.line]
        .filter(Boolean).map((o) => [o, o.visible]);
      for (const [o] of hidden) o.visible = false;

      this.renderer.setViewport(rect.x, rect.y, rect.w, rect.h);
      this.renderer.setScissor(rect.x, rect.y, rect.w, rect.h);
      this.renderer.render(this.scene, cam);

      for (const [o, was] of hidden) o.visible = was;
    }
    this.renderer.setScissorTest(false);
  }
}

/** PIP 자리 = DOM 요소 위치 (레이아웃은 CSS 가 정한다). WebGL y 는 아래가 0. */
function pipRect(key) {
  const el = document.getElementById(`pip-${key}`);
  if (!el || el.hidden) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 8 || r.height < 8) return null;
  return {
    x: r.left,
    y: (document.documentElement.clientHeight || window.innerHeight) - r.bottom,
    w: r.width,
    h: r.height,
  };
}

/** 샘플 사이 선형 보간 상태 (yaw는 최단호 보간). */
export function sampleState(track, t) {
  const i = indexAt(track, t);
  const j = Math.min(i + 1, track.times.length - 1);
  const t0 = track.times[i];
  const t1 = track.times[j];
  const a = t1 > t0 ? Math.min(Math.max((t - t0) / (t1 - t0), 0), 1) : 0;
  const p = track.position;
  const lerp = (u, v) => u + (v - u) * a;
  return {
    index: i,
    x: lerp(p[i * 3], p[j * 3]),
    y: lerp(p[i * 3 + 1], p[j * 3 + 1]),
    z: lerp(p[i * 3 + 2], p[j * 3 + 2]),
    roll: lerpAngle(track.roll[i], track.roll[j], a),
    pitch: lerpAngle(track.pitch[i], track.pitch[j], a),
    yaw: lerpAngle(track.yaw[i], track.yaw[j], a),
    health: attrAt(track, "Health", i),
    inWez: attrAt(track, "InWEZ", i) === true,
  };
}

function lerpAngle(u, v, a) {
  let d = ((v - u + 540) % 360) - 180;
  return u + d * a;
}

function trackExtent(blue, red) {
  let min = [Infinity, Infinity, Infinity];
  let max = [-Infinity, -Infinity, -Infinity];
  for (const track of [blue, red]) {
    const p = track.position;
    for (let i = 0; i < p.length; i += 3) {
      for (let k = 0; k < 3; k++) {
        min[k] = Math.min(min[k], p[i + k]);
        max[k] = Math.max(max[k], p[i + k]);
      }
    }
  }
  return Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1000);
}

function midpoint(blue, red, i) {
  return new THREE.Vector3(
    (blue.position[i * 3] + red.position[i * 3]) / 2,
    (blue.position[i * 3 + 1] + red.position[i * 3 + 1]) / 2,
    (blue.position[i * 3 + 2] + red.position[i * 3 + 2]) / 2,
  );
}

// 선택 자산 적재의 시한. 로컬 파일이라 넉넉하며, 넘기면 폴백으로 간다.
const ASSET_TIMEOUT_MS = 15_000;

function withTimeout(promise, what, ms = ASSET_TIMEOUT_MS) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => {
      console.warn(`${what} 적재가 ${ms}ms 안에 끝나지 않아 폴백합니다.`);
      resolve(null);
    }, ms)),
  ]);
}

// 하늘 돔 — 천정→지평 그라데이션. 지평색을 fog·background 와 공유해서
// 멀리서 지면 평면이 끊기는 자리가 수평선처럼 보이게 만든다.
// ── 하늘 — 파란 그라데이션 돔 ───────────────────────────────────────
// three.js 공식 Sky(Preetham)를 썼다가 되돌렸다: ① 밝은 HDR 이라 톤매핑을 요구하는데
// 그 노출이 기체·바다·화염 전체를 흔든다 ② 태양 미 산란 후광이 화면에 세로 밴드로
// 번져 "우중충" 하게 보였다 ③ 헤드리스(swiftshader)에서 실 GPU 와 다르게 렌더돼
// 검증이 안 됐다. 이 뷰어에 필요한 건 사실적 대기 모델이 아니라 **깨끗한 파란 하늘**
// 이므로, 천정→지평 3색 그라데이션 돔으로 간다. 태양 후광 없음, 톤매핑 불필요.
const SKY_ZENITH = new THREE.Color(0x2a6fd6);   // 천정 — 짙은 파랑
const SKY_MID = new THREE.Color(0x6ea6e8);      // 중공 — 하늘 파랑
const SKY_HAZE = new THREE.Color(0xcfe0ee);     // 지평 — 옅은 헤이즈

// 방향광용 태양 위치(하늘엔 안 그린다 — 후광 제거가 요청). 음영 방향만 담당.
const SUN_ELEV_DEG = 55.0;
const SUN_AZIM_DEG = 225.0;

function sunDirection() {
  const phi = THREE.MathUtils.degToRad(90 - SUN_ELEV_DEG);
  const theta = THREE.MathUtils.degToRad(SUN_AZIM_DEG);
  const v = new THREE.Vector3().setFromSphericalCoords(1, phi, theta);
  return new THREE.Vector3(v.x, v.z, v.y);
}

function buildSky() {
  const geom = new THREE.SphereGeometry(450_000, 32, 16);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, depthTest: false, fog: false,
    uniforms: {
      uZenith: { value: SKY_ZENITH }, uMid: { value: SKY_MID },
      uHaze: { value: SKY_HAZE },
    },
    vertexShader: `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      precision highp float;
      uniform vec3 uZenith, uMid, uHaze;
      varying vec3 vDir;
      void main() {
        // ENU z-up: vDir.z = 위(+1 천정) ~ 0(지평) ~ −1(발밑).
        float h = clamp(vDir.z, 0.0, 1.0);
        // 지평(옅음) → 중공 → 천정(짙음). pow 로 천정을 넓게, 지평 헤이즈를 얇게.
        vec3 col = mix(uHaze, uMid, smoothstep(0.0, 0.30, h));
        col = mix(col, uZenith, smoothstep(0.25, 1.0, pow(h, 0.8)));
        // 지평 아래(발밑)는 헤이즈를 유지해 지면 평면과 경계가 안 보이게.
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  const sky = new THREE.Mesh(geom, mat);
  sky.renderOrder = -10;
  return sky;
}
// 기총 예광 — acmi.py GunVisualizer 가 쓰는 Beam 과 같은 의미·같은 기하:
// 기수 방향(+Y) 1,000m. 사격 판정이 InWEZ 이고 Beam 도 InWEZ 로 켜지므로,
// ACMI 의 Beam 객체를 따로 읽지 않고 같은 조건·같은 축으로 재현한다.
function buildGunBeam(color) {
  const geom = new THREE.CylinderGeometry(10, 2, GUN_RANGE_M, 10, 1, true);
  geom.translate(0, GUN_RANGE_M / 2, 0); // 원점을 기수에, +Y 전방으로 전개
  const beam = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.3, side: THREE.DoubleSide,
    depthWrite: false, blending: THREE.AdditiveBlending, fog: false,
  }));
  beam.userData.wez = true; // 팀색 트래버스 제외
  beam.frustumCulled = false;
  beam.visible = false;
  return beam;
}

// ── 엔진 후기연소(AB) 화염 ──────────────────────────────────────────
// 근거: 이 F-16 은 F100-PW-229(`jsbsim_data/engine/F100-PW-229.xml`) — `augmented=1`,
// `augmethod=2`(연속 가변), milthrust 17,800 / maxthrust 29,000 lbf.
// JSBSim 에 throttle 을 직접 넣어 재어 보면(15,000ft·350kt 정상상태):
//     throttle 0.50 → 추력 14,842 lbf, 연료 10,349 pph, TSFC 0.70  = 건추력
//     throttle 0.60 → 추력 21,474 lbf, 연료 44,022 pph, TSFC 2.05  = AB
// TSFC 가 엔진 파일의 tsfc 0.74 → atsfc 2.05 로 **throttle 0.5 에서** 갈아탄다.
// 즉 0~0.5 = idle→military(화염 없음), 0.5~1.0 = AB 0~100%.
// 그래서 화염은 throttle>0.5 에서만 나오고 길이·밝기는 (thr-0.5)/0.5 에 비례한다.
const AB_THRESHOLD = 0.5;

// 굵기는 노즐 실치수 기준: F100 배기 노즐 출구 지름 ≈ 1.25m, F-16 전장 ≈ 15m
// → 전장 1 로 정규화하면 반지름 ≈ 0.042. 확산부는 그보다 약간 넓게 잡는다.
// ★ 가산 혼합은 쓰지 않는다 — 이 뷰어는 배경이 밝아서 가산으로 그리면 무조건
//   흰색으로 떠버린다(불꽃이 아니라 흰 원뿔이 된다). 일반 알파로 색을 지킨다.
// 모델 정점 실측값(전장 1 정규화): 배기 출구 축위치와 반지름.
// 기체 뒤 끝은 -0.5 지만 그건 수평미익이고, 노즐은 그보다 앞이다.
// 축·수직·반지름 모두 glTF 정점에 원을 최소자승 적합해 얻었다. 수직미익 뿌리가
// 같은 후방 슬라이스에 걸려 있어 그걸 빼야(y<22) 잔차가 2.28 → 1.07 로 떨어진다.
// **수직 오프셋이 0 이 아니다** — 배기구는 기체 bbox 중심보다 아래다(미익이 위로
// 커서 bbox 중심이 올라간다). 0 으로 두면 화염이 노즐 위로 떠 붙는다.
const NOZZLE_Y = -0.4687;   // 축(기수 +) — 기체 뒤 끝은 수평미익이라 -0.5 가 아니다
const NOZZLE_Z = -0.0656;   // 수직 — 실측
const NOZZLE_R = 0.052;     // 적합 반지름 0.0343 보다 약간 넓게(플룸이 노즐을 살짝 덮는다)

// 플룸 길이(전장 대비). F-16(PW-229) 의 가시 플룸은 25~30ft, 전장이 49.4ft 이므로
// **전장의 0.5~0.6** 이다. full AB 에서 0.10+0.45 = 0.55.
const FLAME_LEN_BASE = 0.10;
const FLAME_LEN_AB = 0.45;

/** 플룸 단면 반지름 프로필 r(x) — x: 0 노즐 → 1 끝.
 *
 * 실제 AB 플룸은 노즐 직후 살짝 부풀었다가 **뾰족하게 수렴**한다. 뒤로 갈수록
 * 벌어지는 원뿔(나팔통)로 그리면 배기가 아니라 통을 매단 것처럼 보인다 — 첫 판이
 * 그랬다. 그래서 초반 약한 팽창 + 후반 강한 수렴을 곱으로 만든다.
 */
function plumeRadius(x) {
  return Math.pow(1 - x, 0.45) * (1 + 0.35 * Math.sin(Math.PI * x));
}

function buildEngineFlame() {
  const group = new THREE.Group();
  // 원기둥을 세로로 잘게 나눠 정점 반지름을 프로필로 다시 찍는다(LatheGeometry 대신
  // 원기둥을 쓰면 uv 가 축·둘레로 깔끔히 나뉜다 — 셰이더가 그 uv 에 의존한다).
  const geom = new THREE.CylinderGeometry(1, 1, 1, 28, 48, true);
  geom.translate(0, -0.5, 0);              // −Y(후방)로 전개, 노즐이 원점
  const pos = geom.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = Math.min(Math.max(-pos.getY(i), 0), 1);   // 0(노즐) → 1(끝)
    const k = plumeRadius(x);
    pos.setX(i, pos.getX(i) * k);
    pos.setZ(i, pos.getZ(i) * k);
  }
  pos.needsUpdate = true;
  geom.computeVertexNormals();

  const mesh = new THREE.Mesh(geom, flameMaterial());
  mesh.userData.wez = true;                // 팀색 트래버스 제외
  group.add(mesh);

  // 노즐 글로우 — 카메라를 향하는 판 한 장. 후처리 블룸(UnrealBloomPass)이 정석이지만
  // 이 뷰어는 본 화면과 1인칭 2개를 **scissor 뷰포트로 나눠** 한 프레임에 그린다.
  // EffectComposer 는 전체화면 쿼드로 도는 구조라 뷰포트마다 컴포저를 따로 두어야 해
  // 비용이 커진다. 그래서 글로우는 재질 안에서 낸다.
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), glowMaterial());
  glow.userData.wez = true;
  group.add(glow);

  group.visible = false;
  return group;
}

// 플룸 셰이더. 시간은 **경기 시계**로만 흐른다(uTime) — 벽시계·난수를 쓰면 같은 판을
// 다시 열 때 화면이 달라져 이 저장소의 결정론 규약을 깬다.
function flameMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
    blending: THREE.NormalBlending,   // 가산은 밝은 하늘에서 흰 원뿔이 된다
    uniforms: {
      uTime: { value: 0 },
      uAB: { value: 0 },          // AB 분율 0~1 — 길이·밝기·심 온도를 함께 민다
      uRadius: { value: NOZZLE_R },  // 노즐 출구 반지름 — 모델 실측
    },
    vertexShader: `
      varying vec2 vUv;
      varying float vFacing;   // |n·v| — 시선이 플룸을 얼마나 깊게 관통하는가
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        // 껍질 하나로 부피를 흉내내는 정석: 시선이 껍질 정면을 뚫으면 가스를 길게
        // 지나가고(밝고 짙다), 실루엣을 스치면 짧게 지난다(옅다).
        vec3 n = normalize(normalMatrix * normal);
        vFacing = abs(dot(n, normalize(-mv.xyz)));
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      precision highp float;
      uniform float uTime, uAB, uRadius;
      varying vec2 vUv;
      varying float vFacing;

      // 값 노이즈 + fbm — 난류를 낸다. 텍스처를 안 쓰므로 외부 자산이 필요 없다.
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float noise(vec2 p){
        vec2 i = floor(p), f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash(i), hash(i + vec2(1,0)), u.x),
                   mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
      }
      float fbm(vec2 p){
        float v = 0.0, a = 0.5;
        for (int k = 0; k < 4; k++) { v += a * noise(p); p *= 2.02; a *= 0.5; }
        return v;
      }

      void main() {
        // 원기둥 껍질의 uv: **x 는 둘레 각도, y 는 축 방향**이다.
        // (이걸 가로 폭으로 착각해 쓰면 둘레 대부분이 잘려 플룸이 사라진다 — 실측 교정)
        // ⚠ CylinderGeometry 의 uv.y 는 **아래(−height/2)가 0** 이다. 우리는 translate 로
        // 위쪽 끝을 노즐에 뒀으므로 노즐이 uv.y=1 이다 — 그대로 쓰면 온도·알파가
        // 앞뒤로 뒤집혀 **꼬리 끝이 가장 뜨겁고 노즐이 투명**해진다(실측 교정).
        float x = 1.0 - vUv.y;        // 0 = 노즐, 1 = 플룸 끝
        float ang = vUv.x;            // 둘레 — 난류 변화에만 쓴다

        // ① 난류 — 하류로 갈수록 커지고, 배기와 함께 뒤로 흐른다.
        float flow = uTime * 2.6;
        float turb = fbm(vec2(ang * 7.0, x * 5.0 - flow)) - 0.5;
        turb *= 0.25 + 0.75 * x;

        // ② 충격 다이아몬드(Mach disk) — AB 플룸의 서명. 과팽창 제트가 팽창·압축을
        //    반복하며 축을 따라 밝은 마디가 규칙적으로 선다. 간격은 하류로 갈수록
        //    벌어지고(pow), 대기압에 가까워지며 사라진다(exp 감쇠).
        // 마디는 노즐 직후 **앞쪽 1/3 에만** 선다 — 하류로 가면 압력이 평형에
        // 가까워져 사라진다. 전 구간에 깔면 배기가 아니라 줄무늬 통이 된다.
        float node = sin(6.28318 * (pow(x, 0.7) * 6.0) - flow * 0.5);
        float diamonds = (pow(max(node, 0.0), 4.0) - 0.3 * pow(max(-node, 0.0), 3.0))
                         * exp(-5.0 * x) * uAB;

        // ③ 심 온도 — 시선이 플룸 한가운데를 관통할수록 뜨거운 축을 통과한다.
        float core = pow(clamp(vFacing, 0.0, 1.0), 2.0);  // 실루엣을 더 부드럽게
        // 노즐 직후가 가장 뜨겁다(청백) — 지수 감쇠로 급히 식는다. 선형이면 플룸
        // 전체가 미지근한 주황 하나로 보인다.
        // 노즐 직후가 3,200°F 급으로 가장 뜨겁고(창백한 청색) 급히 식는다.
        float axial = exp(-2.4 * x);
        float heat = axial * core * 1.35 + diamonds * 0.42 + turb * 0.22;
        heat = clamp(heat * (0.55 + 0.45 * uAB), 0.0, 1.0);

        // ④ 색 스펙트럼 — 검은연기 → 적 → 주황 → 노랑 → 청백(최고온).
        // 관측 기준: 노즐 직후는 **창백한 청색**(고온·완전연소), 하류로 갈수록
        // 노랑→주황(저온·불완전연소), 끝은 흐릿하게 사라진다.
        vec3 col = mix(vec3(0.30, 0.09, 0.03), vec3(0.90, 0.30, 0.05), smoothstep(0.04, 0.26, heat));
        col = mix(col, vec3(1.00, 0.58, 0.12), smoothstep(0.26, 0.48, heat));
        col = mix(col, vec3(1.00, 0.88, 0.52), smoothstep(0.48, 0.68, heat));
        // 청백은 흰색에 가깝게 — 시안으로 빠지면 불이 아니라 플라스마처럼 보인다.
        col = mix(col, vec3(0.96, 0.95, 0.92), smoothstep(0.70, 0.88, heat));
        col = mix(col, vec3(0.84, 0.88, 1.00), smoothstep(0.88, 1.00, heat));

        // ⑤ 알파 — 관통 길이(core)에 비례하고 하류로 갈수록 확산해 옅어진다.
        float a = core * (1.0 - smoothstep(0.05, 0.85, x));
        a *= 0.30 + 0.40 * uAB;        // 전체 농도 — 진하면 형상을 덮는 판때기가 된다
        a *= 0.45 + 0.85 * heat;       // 뜨거운 곳만 진하게 → 마디가 드러난다
        if (a < 0.004) discard;
        gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));
      }`,
  });
}

// 노즐 글로우 — 카메라 지향 판. 중심이 밝고 가장자리로 부드럽게 죽는 원.
function glowMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, fog: false,
    blending: THREE.AdditiveBlending,   // 글로우는 빛이므로 여기서만 가산
    uniforms: { uAB: { value: 0 } },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        // 빌보드: 모델 원점을 뷰 공간으로 옮기고, 판을 화면에 평행하게 세운다.
        vec4 mv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
        vec2 sc = vec2(length(modelMatrix[0].xyz), length(modelMatrix[1].xyz));
        mv.xy += position.xy * sc;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      precision highp float;
      uniform float uAB;
      varying vec2 vUv;
      void main() {
        float d = length(vUv - 0.5) * 2.0;
        float g = pow(1.0 - clamp(d, 0.0, 1.0), 3.0);
        // 가산이라 강하게 넣으면 하늘이 하얗게 뜬다 — AB 분율에 비례해 약하게만.
        gl_FragColor = vec4(vec3(1.0, 0.72, 0.42) * g, g * 0.26 * uAB);
      }`,
  });
}

// ── 고G 베이퍼 (익단·LEX 와류 응결) ─────────────────────────────────
// 근거: 큰 받음각·하중배수에서 LEX/익단 와류 중심의 정압이 급락하고, 단열팽창으로
// 국소 온도가 이슬점 아래로 내려가면 수증기가 응결해 흰 띠로 보인다. 그래서
// **하중배수(Nz)와 받음각(AOA)** — 둘 다 ACMI 에 기록돼 있다 — 로만 켠다.
//
// 일부러 넣지 않은 것:
//   · 콘트레일 — 배기 응결은 대략 -40°C 이하(보통 26,000ft 이상)에서 지속한다.
//     이 대회 교전은 12,000~25,000ft 라 근거가 없다.
//   · 천음속 충격 원뿔(Prandtl–Glauert) — 여기 속도는 마하 0.5~0.85 수준이라
//     충격파가 서지 않는다.
// 습도는 시뮬레이션에 없으므로 "습한 날" 을 가정한 표현임을 문서에 밝힌다.
const VAPOR_NZ_ON = 4.0;    // 이 하중배수부터 보이기 시작
const VAPOR_NZ_FULL = 7.5;  // 여기서 최대

function buildVapor() {
  const group = new THREE.Group();
  // 고G 응결운은 두 곳에서 난다(조사: 날개 윗면 저압 + 동체 볼록부 위):
  //   ① 익단 실오라기 — 가늘고 길게 뒤로 끌린다(익단 와류 중심의 응결).
  //   ② 날개·동체 상면 시트 — 기체를 **감싸는** 얇은 구름. 천음속 고G 의 그 장면.
  // 원뿔 메시로 그리면 흰 삼각형 판이 꽂힌 것처럼 보이므로(실측 교정) 전부 얇은
  // 면 + 셰이더 밀도로 낸다.

  // ① 익단 실오라기 (기존)
  for (const side of [-1, 1]) {
    const geom = new THREE.PlaneGeometry(0.03, 0.30, 1, 12);
    geom.translate(0, -0.15, 0);
    const mesh = new THREE.Mesh(geom, vaporMaterial("tip"));
    mesh.position.set(side * 0.30, -0.10, -0.02);
    mesh.userData.wez = true;
    group.add(mesh);
  }

  // ② 상면 시트 — 날개 상면(넓게)과 동체 상면(길게)을 덮는 수평 면. 기체를 감싸도록
  //    기체 바로 위(+z)에 눕힌다. 셰이더가 앞전에서 옅고 중앙이 짙게, 뒤로 흩어지게.
  for (const [w, l, y, z] of [
    [0.52, 0.26, -0.06, 0.015],   // 날개 상면: 익폭 넓게, 짧게
    [0.10, 0.55, 0.02, 0.03],     // 동체 상면: 좁게, 기수~꼬리 길게
  ]) {
    const geom = new THREE.PlaneGeometry(w, l, 8, 10);
    geom.rotateX(-Math.PI / 2);   // XY(수평)면으로 눕힌다 — 위에서 덮는다
    const mesh = new THREE.Mesh(geom, vaporMaterial("sheet"));
    mesh.position.set(0, y, z);
    mesh.userData.wez = true;
    mesh.userData.sheet = true;
    group.add(mesh);
  }
  group.visible = false;
  return group;
}

/** 응결 재질. kind="tip" 익단 실오라기(빌보드) / "sheet" 날개·동체 상면 시트(고정). */
function vaporMaterial(kind) {
  const isSheet = kind === "sheet";
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
    uniforms: { uAmt: { value: 0 }, uTime: { value: 0 },
                uSheet: { value: isSheet ? 1 : 0 } },
    vertexShader: `
      varying vec2 vUv;
      uniform float uSheet;
      void main() {
        vUv = uv;
        if (uSheet > 0.5) {
          // 시트는 기체에 붙어 함께 도는 고정 면 — 자세를 그대로 따른다(빌보드 아님).
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        } else {
          // 실오라기는 카메라를 향해 눕는 빌보드.
          vec4 mv = modelViewMatrix * vec4(0.0, position.y, 0.0, 1.0);
          mv.x += position.x * length(modelMatrix[0].xyz);
          gl_Position = projectionMatrix * mv;
        }
      }`,
    fragmentShader: `
      precision highp float;
      uniform float uAmt, uTime, uSheet;
      varying vec2 vUv;
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float noise(vec2 p){
        vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(hash(i), hash(i+vec2(1,0)), u.x),
                   mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
      }
      float fbm(vec2 p){ float v=0.,a=.5; for(int k=0;k<3;k++){v+=a*noise(p);p*=2.1;a*=.5;} return v; }
      void main() {
        if (uSheet > 0.5) {
          // 상면 시트: 앞전(uv.y=0)에서 피어 중앙이 짙고 뒷전으로 흩어진다. 표면을
          // 덮는 얇은 구름이라 가장자리를 둥글게 죽여 판때기로 안 보이게 한다.
          vec2 c = vUv - 0.5;
          float body = smoothstep(0.5, 0.15, length(c));         // 중앙 집중
          float chord = smoothstep(0.0, 0.25, vUv.y) * (1.0 - smoothstep(0.6, 1.0, vUv.y));
          float puff = fbm(vec2(vUv.x * 5.0, vUv.y * 4.0 - uTime * 1.2));
          float a = body * chord * (0.4 + 0.6 * puff) * uAmt;
          // 고G 에서 급히 피고(임계 근처 비선형) 약하게. 판이 아니라 안개로.
          a *= a * 1.8;
          if (a < 0.006) discard;
          gl_FragColor = vec4(1.0, 1.0, 1.0, clamp(a, 0.0, 0.5) * 0.7);
        } else {
          float x = 1.0 - vUv.y;
          float edge = 1.0 - smoothstep(0.15, 0.5, abs(vUv.x - 0.5));
          float wisp = noise(vec2(vUv.x * 3.0, x * 6.0 - uTime * 2.0));
          float a = edge * (1.0 - smoothstep(0.1, 1.0, x)) * (0.35 + 0.65 * wisp) * uAmt;
          if (a < 0.004) discard;
          gl_FragColor = vec4(1.0, 1.0, 1.0, a * 0.55);
        }
      }`,
  });
}

// 절차적 저폴리 제트 실루엣 — 기수 +Y, 상방 +Z, 전체 길이 1 → displayLen 스케일.
// F-16 모델(f16.js)이 없거나 로드에 실패했을 때의 폴백. 외부 자산 없이도 뷰어가 돈다.
function buildAircraft(color, bellyColor, displayLen) {
  const group = new THREE.Group();
  const mat = new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide });

  const fuselage = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.02, 0.8, 8), mat);
  fuselage.position.y = -0.05;
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.028, 0.2, 8), mat);
  nose.position.y = 0.45;
  const fin = new THREE.Mesh(triangle(
    [0, -0.26, 0.02], [0, -0.48, 0.2], [0, -0.48, 0.02]), mat);
  group.add(fuselage, nose, fin);

  // 날개·수평미익은 상면=팀색 / 하면=밝은 회색 투톤 — 배면비행 육안 식별.
  // 정점 winding이 법선 +Z(상면)이므로 FrontSide=위, BackSide=아래에서 보임.
  const topMat = new THREE.MeshLambertMaterial({ color, side: THREE.FrontSide });
  const bellyMat = new THREE.MeshLambertMaterial({
    color: bellyColor, side: THREE.BackSide,
  });
  const wingGeom = triangle([0, 0.15, 0], [-0.3, -0.25, 0], [0.3, -0.25, 0]);
  const stabGeom = triangle([0, -0.28, 0], [-0.15, -0.48, 0], [0.15, -0.48, 0]);
  for (const geom of [wingGeom, stabGeom]) {
    group.add(new THREE.Mesh(geom, topMat));
    const belly = new THREE.Mesh(geom, bellyMat);
    belly.userData.belly = true;
    group.add(belly);
  }

  // 짙은 캐노피 — 등쪽에만 있는 형상 비대칭 단서. 색과 무관하게 상/하면 식별.
  const canopy = new THREE.Mesh(
    new THREE.SphereGeometry(0.035, 12, 8),
    new THREE.MeshLambertMaterial({ color: 0x233250 }),
  );
  canopy.scale.set(0.8, 1.8, 0.8);
  canopy.position.set(0, 0.18, 0.03);
  canopy.userData.belly = true; // 팀색 트래버스에서 제외 — 항상 짙은 색 유지
  group.add(canopy);

  group.scale.setScalar(displayLen);
  return group;
}

function triangle(a, b, c) {
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position",
    new THREE.Float32BufferAttribute([...a, ...b, ...c], 3));
  geom.computeVertexNormals();
  return geom;
}

function setUnitColor(group, color, bellyColor) {
  group.traverse((o) => {
    if (o.isMesh && !o.userData.wez && !o.userData.belly) {
      o.material.color.setHex(color);
      // 실기 모델은 하면 톤이 셰이더 유니폼이라 격추 회색 전환 시 같이 바꿔준다.
      const uBelly = o.material.userData.uBelly;
      if (uBelly) uBelly.value.setHex(bellyColor);
    }
  });
}

// Gun WEZ 원뿔 — 꼭짓점이 기수, +Y(전방)으로 열림. group 자식이라 자세를 따라감.
function buildWezCone(color, wez) {
  const h = wez.maxRangeM;
  const r = h * Math.tan(wez.halfAngleDeg * DEG);
  const geom = new THREE.ConeGeometry(r, h, 24, 1, true);
  geom.rotateX(Math.PI);          // 꼭짓점을 원점으로
  geom.translate(0, h / 2, 0);    // +Y 전방으로 전개
  const mat = new THREE.MeshBasicMaterial({
    color, transparent: true, opacity: 0.07, side: THREE.DoubleSide,
    depthWrite: false,
  });
  const cone = new THREE.Mesh(geom, mat);
  cone.userData.wez = true;
  return cone;
}

// 항적 — 지나온 경로를 팀색 굵은 선으로. setDrawRange 로 현재 시각까지만.
//
// WebGL 은 `linewidth` 를 무시한다(항상 1px). 그래서 얇은 THREE.Line 대신
// **카메라를 향하는 리본**을 쓰고 폭을 매 프레임 다시 잡는다 — 각 정점의 카메라
// 거리에 비례시키면 줌과 무관하게 화면 두께가 일정하다.
// (예전 리본은 폭이 displayLen 고정이라 멀리서 보면 화면을 가로지르는 판때기,
//  가까이선 실오라기였다. 이제 두 경우 모두 같은 굵기로 보인다.)
// 원본 도장을 쓰는 지금은 **이 색이 유일한 팀 식별 단서**이므로 진하게 둔다.
const TRAIL_HALF_PX = 3.0;      // 화면상 반폭 [px] → 최근 구간 두께 약 6px
const TRAIL_HALF_M_MAX = 400;   // 극단적 원경에서 리본이 커지는 것만 막는다
// 꼬리 페이드: 최근이 진하고 굵다(혜성 꼬리). 반대로 하면 시선이 과거로 끌리고,
// 144초치가 전부 진해져 궤적이 엉킨다. **고정 시간**으로 페이드하므로 빠를수록
// 밝은 꼬리가 길어진다 — 색이 아니라 길이가 속도를 말해 준다.
const TRAIL_FADE_S = 12;        // 이 시간에 걸쳐 밝은 꼬리 → 흐린 이력
// 바닥값은 넉넉히 — 너무 낮추면 "지금까지 어떻게 싸웠나" 를 못 읽는다. 이력이
// 보이되 최근 구간이 확실히 앞에 서는 정도가 맞다.
const TRAIL_FLOOR = 0.34;       // 오래된 구간의 최소 진하기
const TRAIL_THIN = 0.58;        // 오래된 구간의 두께 배율
const TRAIL_BAND = 0.72;        // 1초 간격 밝기 띠의 어두운 쪽 배율

function buildTrail(track, color) {
  const n = track.times.length;
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 6), 3));
  // RGBA 정점색 — RGB 는 흰색으로 두고 알파만 쓴다(재질 color 가 팀색을 곱한다)
  const rgba = new Float32Array(n * 8).fill(1);
  geom.setAttribute("color", new THREE.BufferAttribute(rgba, 4));
  const idx = new Uint32Array(Math.max(n - 1, 0) * 6);
  for (let i = 0; i < n - 1; i++) {
    const a = i * 2;
    idx.set([a, a + 1, a + 2, a + 1, a + 3, a + 2], i * 6);
  }
  geom.setIndex(new THREE.BufferAttribute(idx, 1));
  const mesh = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({
    color, side: THREE.DoubleSide, transparent: true, opacity: 1,
    depthWrite: false, vertexColors: true,
  }));
  mesh.frustumCulled = false;
  return mesh;
}

// 리본 정점 재계산. 폭 방향 = (경로 접선) × (정점→카메라) — 즉 화면에 정면으로
// 눕는다. count 까지만 계산하면 되지만(그 뒤는 draw range 밖) 카메라가 움직이면
// 이미 그린 구간의 폭도 달라지므로 매 프레임 전 구간을 다시 잡는다.
function updateTrailRibbon(trail, track, count, camera, viewportH, nowT) {
  const p = track.position;
  const n = track.times.length;
  const arr = trail.geometry.attributes.position.array;
  const col = trail.geometry.attributes.color.array;
  // 화면 1px 에 대응하는 거리당 월드 길이
  const perMeter = (2 * Math.tan((camera.fov / 2) * DEG)) / Math.max(viewportH, 1);
  const cx = camera.position.x, cy = camera.position.y, cz = camera.position.z;
  const last = Math.min(count, n - 1);

  for (let i = 0; i <= last; i++) {
    // 나이 → 진하기·두께. 최근(age 0)이 가장 진하고 굵다.
    const fresh = Math.max(0, 1 - (nowT - track.times[i]) / TRAIL_FADE_S);
    // 1초 간격 밝기 띠 — **한 칸이 정확히 1초**다. 빠를수록 칸이 길어지므로
    // 속도가 눈금으로 읽힌다(속도감이 인상이 아니라 계측이 된다).
    const band = Math.floor(track.times[i]) % 2 === 0 ? 1 : TRAIL_BAND;
    const alpha = (TRAIL_FLOOR + (1 - TRAIL_FLOOR) * fresh) * band;
    const c = i * 8;
    col[c + 3] = alpha;
    col[c + 7] = alpha;
    const a = Math.max(i - 1, 0) * 3;
    const b = Math.min(i + 1, n - 1) * 3;
    let tx = p[b] - p[a], ty = p[b + 1] - p[a + 1], tz = p[b + 2] - p[a + 2];
    const x = p[i * 3], y = p[i * 3 + 1], z = p[i * 3 + 2];
    let vx = cx - x, vy = cy - y, vz = cz - z;
    const dist = Math.hypot(vx, vy, vz) || 1;
    vx /= dist; vy /= dist; vz /= dist;

    // right = tangent × toCam (둘 다 정규화 불필요 — 결과만 정규화한다)
    let rx = ty * vz - tz * vy;
    let ry = tz * vx - tx * vz;
    let rz = tx * vy - ty * vx;
    const rl = Math.hypot(rx, ry, rz);
    if (rl < 1e-9) { rx = 1; ry = 0; rz = 0; }     // 카메라 정면 — 임의 축
    else { rx /= rl; ry /= rl; rz /= rl; }

    const taper = TRAIL_THIN + (1 - TRAIL_THIN) * fresh;
    const hw = Math.min(dist * perMeter * TRAIL_HALF_PX * taper, TRAIL_HALF_M_MAX);
    const o = i * 6;
    arr[o] = x - rx * hw; arr[o + 1] = y - ry * hw; arr[o + 2] = z - rz * hw;
    arr[o + 3] = x + rx * hw; arr[o + 4] = y + ry * hw; arr[o + 5] = z + rz * hw;
  }
  trail.geometry.attributes.position.needsUpdate = true;
  trail.geometry.attributes.color.needsUpdate = true;
}

// 항적이 시작되는 지점을 뒤로 밀어 낼 거리(offsetM)를 샘플 수로 환산한다.
// 샘플 간격은 속도에 따라 달라지므로 매 프레임 현재 간격으로 계산한다.
function trailHeadTrim(track, index, offsetM) {
  if (index < 2) return 0;
  const p = track.position;
  const a = (index - 1) * 3, b = index * 3;
  const step = Math.hypot(p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]);
  if (step < 1e-4) return 0;
  return Math.min(Math.round(offsetM / step), 60, index);
}

/** AB 화염 갱신. 반환값 = AB 분율(0~1) — 항적 시작점 계산에 쓴다.
 *
 * 애니메이션 시간은 **경기 시계 t** 다. 벽시계(performance.now)나 난수를 쓰면 같은
 * 판을 다시 열 때마다 다른 화면이 나와, 이 저장소가 지키는 결정론 규약을 깬다
 * (피격 비네트도 같은 이유로 경기 시계만 쓴다).
 */
function updateFlame(unit, s, dead, t) {
  const thr = attrAt(unit.track, "Throttle", s.index);
  const abFrac = typeof thr === "number" && thr > AB_THRESHOLD
    ? Math.min((thr - AB_THRESHOLD) / (1 - AB_THRESHOLD), 1) : 0;
  unit.flame.visible = abFrac > 0 && !dead;
  if (!unit.flame.visible) return 0;

  const len = FLAME_LEN_BASE + FLAME_LEN_AB * abFrac;
  const [plume, glow] = unit.flame.children;
  // 플룸: 길이는 AB 분율, 굵기는 노즐 실치수 고정(하류 확산은 셰이더가 낸다)
  const r = plume.material.uniforms.uRadius.value;
  plume.scale.set(r, len, r);
  plume.material.uniforms.uTime.value = t;
  plume.material.uniforms.uAB.value = abFrac;
  // 글로우: 노즐 바로 뒤에 붙이고 AB 가 셀수록 크게
  // 글로우는 노즐 주변만 — 크게 잡으면 플룸 구조를 덮어 주황색 공이 된다(실측 교정)
  glow.scale.setScalar(r * (1.5 + 1.1 * abFrac));
  glow.position.set(0, -r * 0.5, 0);
  glow.material.uniforms.uAB.value = abFrac;
  return abFrac;
}

/** 고G 와류 응결. Nz(실측 하중배수) 기준, AOA 가 있으면 함께 본다. */
function updateVapor(unit, s, dead, t) {
  const nz = attrAt(unit.track, "Nz", s.index);
  if (typeof nz !== "number" || dead) { unit.vapor.visible = false; return; }
  const g = Math.abs(nz);
  const f = Math.min(Math.max((g - VAPOR_NZ_ON) / (VAPOR_NZ_FULL - VAPOR_NZ_ON), 0), 1);
  unit.vapor.visible = f > 0.01;
  if (!unit.vapor.visible) return;
  // 받음각이 크면 와류가 강해 더 짙다 — 없으면 Nz 만으로 간다
  const aoa = attrAt(unit.track, "AOA", s.index);
  const aoaBoost = typeof aoa === "number"
    ? Math.min(Math.max((aoa - 8) / 14, 0), 1) : 0.5;
  const amt = f * (0.6 + 0.4 * aoaBoost);
  for (const m of unit.vapor.children) {
    m.material.uniforms.uAmt.value = amt;
    m.material.uniforms.uTime.value = t;
    // 실오라기만 세기에 따라 길어진다(빌보드 세로축). 시트는 고정 크기(기체에 붙음).
    if (!m.userData.sheet) m.scale.set(1, 0.7 + 0.6 * f, 1);
  }
}

// 2-정점 라인 (LOS·속도/리프트 벡터 공용). 매 프레임 setSegment 로 갱신.
function buildSegment(color, opacity) {
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(6, 3));
  const line = new THREE.Line(geom,
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
  line.frustumCulled = false;
  return line;
}

function setSegment(line, ax, ay, az, bx, by, bz) {
  const pos = line.geometry.attributes.position;
  pos.setXYZ(0, ax, ay, az);
  pos.setXYZ(1, bx, by, bz);
  pos.needsUpdate = true;
}

// 속도 벡터(팀색, 300m) + 리프트 벡터(gmode 색, 기체 상방 260m) — addon 정합.
function updateVectors(unit, s, dead) {
  const { velVec, liftVec } = unit;
  velVec.visible = liftVec.visible = !dead;
  if (dead) return;

  const v = trackVelocity(unit.track, s.index);
  velVec.visible = !!v;
  if (v) {
    v.normalize().multiplyScalar(VELVEC_LEN);
    setSegment(velVec, s.x, s.y, s.z, s.x + v.x, s.y + v.y, s.z + v.z);
  }

  const up = new THREE.Vector3(0, 0, LIFTVEC_LEN)
    .applyQuaternion(unit.group.quaternion);
  setSegment(liftVec, s.x, s.y, s.z, s.x + up.x, s.y + up.y, s.z + up.z);
  const gmode = parsePacked(attrAt(unit.track, "L2", s.index)).gmode;
  liftVec.material.color.setHex(GMODE_COLORS[gmode] ?? GMODE_FALLBACK);
}

// 조준점 마커(와이어프레임 구, 팀색) + 노즈→조준점 연결선.
// 구는 단위 반지름 — 매 프레임 카메라 거리 비례로 스케일해 화면 고정 크기.
function buildAimpoint(color) {
  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(1, 12, 8),
    new THREE.MeshBasicMaterial({
      color, wireframe: true, transparent: true, opacity: 0.6,
    }),
  );
  marker.frustumCulled = false;
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(6, 3));
  const line = new THREE.Line(geom,
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.45 }));
  line.frustumCulled = false;
  return { marker, line };
}

// L1 pursuit(pure/lead/lag)·L2 aim/lead/lag 파라미터로 조준점 산출
// (tacview-addons AddPilotGeometry 와 동일 로직, ENU z-up):
//   lead = 적 위치 + 적속도×lead[s], lag = 적 뒤 lag[ft], pure = 적 현위치
//   aim_above[ft]는 +z 오프셋 (core2 NED aim[2] -= aim_above_ft 등가)
const FT = 0.3048;
function updateAimpoint(unit, foeTrack, s, foeState, camera) {
  const { marker, line } = unit.aim;
  const dead = s.health !== null && s.health <= 0;
  marker.visible = line.visible = SHOW_AIM && !dead;
  if (dead || !SHOW_AIM) return;

  const l1 = parsePacked(attrAt(unit.track, "L1", s.index));
  const l2 = parsePacked(attrAt(unit.track, "L2", s.index));
  const pursuit = l1.pursuit ?? "pure";
  const num = (key, fallback) => {
    const n = parseFloat(l2[key]);
    return Number.isFinite(n) ? n : fallback;
  };

  const aim = new THREE.Vector3(foeState.x, foeState.y, foeState.z);
  const fvel = trackVelocity(foeTrack, foeState.index);
  if (fvel) {
    if (pursuit === "lead") {
      aim.addScaledVector(fvel, num("lead", 1.0));
    } else if (pursuit === "lag") {
      aim.addScaledVector(fvel.normalize(), -num("lag", 1500) * FT);
    }
  }
  aim.z += num("aim", 0) * FT;

  marker.position.copy(aim);
  marker.scale.setScalar(
    Math.max(3, camera.position.distanceTo(aim) * 0.005));
  const pos = line.geometry.attributes.position;
  pos.setXYZ(0, s.x, s.y, s.z);
  pos.setXYZ(1, aim.x, aim.y, aim.z);
  pos.needsUpdate = true;
}

// 트랙 i번째 샘플의 속도 [m/s]. 인접 샘플 차분은 ACMI 좌표 양자화 잡음이 지배해
// 벡터가 떤다(hud.js loadFactorG 와 같은 사정) — ±VEL_WIN_S 창으로 평활한다.
const VEL_WIN_S = 0.25;
function trackVelocity(track, i) {
  const t = track.times;
  const a = indexAt(track, t[i] - VEL_WIN_S);
  const b = Math.min(indexAt(track, t[i] + VEL_WIN_S) + 1, t.length - 1);
  const dt = t[b] - t[a];
  if (dt <= 0) return null;
  const p = track.position;
  return new THREE.Vector3(
    (p[b * 3] - p[a * 3]) / dt,
    (p[b * 3 + 1] - p[a * 3 + 1]) / dt,
    (p[b * 3 + 2] - p[a * 3 + 2]) / dt,
  );
}

// 고도 인지선 (기체→해수면 수직선). group 로컬에 두되 매 프레임 월드 기준 재계산.
function buildDropLine(color) {
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(6, 3));
  const line = new THREE.Line(geom,
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.25 }));
  line.userData.wez = true; // 색상 트래버스에서 제외
  line.frustumCulled = false;
  return line;
}

function updateDropLine(line, group, altitude) {
  // group 회전·스케일을 상쇄해 로컬 좌표로 수직선 구성
  const inv = group.scale.x;
  const pos = line.geometry.attributes.position;
  pos.setXYZ(0, 0, 0, 0);
  const local = new THREE.Vector3(0, 0, -altitude / inv);
  local.applyQuaternion(group.quaternion.clone().invert());
  pos.setXYZ(1, local.x, local.y, local.z);
  pos.needsUpdate = true;
}
