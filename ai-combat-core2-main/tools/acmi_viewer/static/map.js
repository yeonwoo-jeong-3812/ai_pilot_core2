// 지면 — 고도 0 평면에 무엇을 깔지. 두 가지를 제공한다:
//   map  : make_map.py 가 구운 위성 타일 (실제 좌표 위)
//   grid : 계측용 격자 (아래 buildGridGround)
//
// 왜 둘 다 필요한가 — 위성 영상은 고주파 무늬라 항적·기체와 주목을 다툰다.
// 복기에서 읽어야 하는 건 지형이 아니라 상대 기하(거리·각도·에너지)이므로,
// 집중해서 볼 때는 격자가 낫다는 현장 의견이 있었다. 지도는 "어디서 싸웠나" 를
// 보여주는 맥락용, 격자는 "어떻게 싸웠나" 를 읽는 계측용이다.
//
// 엔진의 ned_to_lonlat(lon0=127.0, lat0=37.0) 이 교전을 한반도 중부 상공에 찍으므로,
// 같은 좌표계로 지도를 배치하면 트랙이 실제 지형 위에 정확히 얹힌다.
//
// ★ 평면인 이유: 엔진 물리가 평지다(평면근사 투영 + 해수면 기준 하드덱 1,000ft).
//   실지형 고도를 넣으면 산을 통과해 나는 화면이 되어 판정과 모순된다.
import * as THREE from "three";

const DEG = Math.PI / 180.0;
const EARTH_RADIUS_M = 6378137.0; // acmi.js buildTracks 와 동일 상수

/** static/maps/index.json 로드. 지도가 없으면 null (뷰어는 격자 폴백). */
export async function loadMapMeta() {
  try {
    const res = await fetch("/maps/index.json");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 지도 텍스처 로드. 실패 시 null. */
export function loadMapTexture(meta) {
  return new Promise((resolve) => {
    new THREE.TextureLoader().load(
      `/maps/${meta.image}`,
      (tex) => {
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = 8;
        resolve(tex);
      },
      undefined,
      () => resolve(null),
    );
  });
}

/**
 * 지도 평면 메시. 씬 원점은 (refLat, refLon) 이므로 지도 중심을 그만큼 옮겨 놓는다.
 * UV 는 three 기본(flipY) 이라 이미지 첫 행(북쪽)이 +Y(북)로 간다 — 뒤집기 불필요.
 */
export function buildMapPlane(meta, texture, refLat, refLon) {
  // 무조명 — 위성 영상에 씬 조명이 겹치면 색이 뜬다.
  const material = new THREE.MeshBasicMaterial({
    map: texture, transparent: true, depthWrite: true,
  });
  // 지도는 실제 지리 크기(≈78km)로 고정이라 멀리서 보면 잘린 판때기처럼 직선
  // 경계가 드러난다. 가장자리 알파를 죽여 배경 지면으로 녹인다(fog 가 나머지를 한다).
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = "varying vec2 vMapUv2;\n" + shader.vertexShader.replace(
      "#include <uv_vertex>", "#include <uv_vertex>\n\tvMapUv2 = uv;");
    shader.fragmentShader = "varying vec2 vMapUv2;\n" + shader.fragmentShader.replace(
      "#include <opaque_fragment>",
      "\tvec2 e = min(vMapUv2, 1.0 - vMapUv2);\n"
      + "\tdiffuseColor.a *= smoothstep(0.0, 0.06, min(e.x, e.y));\n"
      + "#include <opaque_fragment>");
  };
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(meta.width_m, meta.height_m), material);
  mesh.position.set(
    (meta.center_lon - refLon) * DEG * EARTH_RADIUS_M * Math.cos(refLat * DEG),
    (meta.center_lat - refLat) * DEG * EARTH_RADIUS_M,
    0,
  );
  mesh.renderOrder = -1; // 항적·드롭라인의 z-fighting 방지
  return mesh;
}

// ── 계측용 격자 지면 ────────────────────────────────────────────────
// 눈금은 **피트**다 — 사격창(500~3,000ft)·거리 readout·하드덱(1,000ft)이 전부
// 피트라, 화면에서 잰 칸 수가 그대로 판정 단위로 읽혀야 한다.
export const GRID_MINOR_FT = 1000;
export const GRID_MAJOR_FT = 5000;
const FT_TO_M = 0.3048;

/**
 * 격자 지면. 선을 지오메트리로 깔면(GridHelper) 원경에서 모아레가 생기고 정점도
 * 수만 개가 된다 — 대신 프래그먼트에서 그리고 `fwidth` 로 **화면상 굵기를 고정**한다.
 * 줌과 무관하게 같은 굵기라 멀리서도 가까이서도 깨끗하다.
 */
export function buildGridGround(size, horizonColor) {
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uMinor: { value: GRID_MINOR_FT * FT_TO_M },
      uMajor: { value: GRID_MAJOR_FT * FT_TO_M },
      uBase: { value: new THREE.Color(0xe8edf3) },
      uLine: { value: new THREE.Color(0x93a7bd) },
      uLineMajor: { value: new THREE.Color(0x5d7189) },
      uHorizon: { value: new THREE.Color(horizonColor) },
      uFade: { value: 90_000 },
    },
    vertexShader: `
      varying vec3 vWorld;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vWorld = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: `
      varying vec3 vWorld;
      uniform float uMinor, uMajor, uFade;
      uniform vec3 uBase, uLine, uLineMajor, uHorizon;

      // 격자선 세기 — 셀 좌표의 화면 미분으로 나눠 굵기를 픽셀로 고정한다.
      // 한 픽셀에 한 칸 이상이 들어오면(스치는 각도·원경) 선이 뭉쳐 검은 해칭이
      // 되므로, 그 전에 녹여 없앤다 — 모아레의 원인이 바로 이 구간이다.
      float gridLine(vec2 p, float step, float width) {
        vec2 c = p / step;
        vec2 fw = fwidth(c);
        vec2 d = fw * width;
        vec2 g = abs(fract(c - 0.5) - 0.5) / max(d, vec2(1e-6));
        float line = 1.0 - min(min(g.x, g.y), 1.0);
        float dissolve = 1.0 - smoothstep(0.12, 0.5, max(fw.x, fw.y));
        return line * dissolve;
      }

      void main() {
        float dist = length(vWorld - cameraPosition);
        // 원경은 격자를 지운다 — 안 그러면 지평 근처가 잡티로 뭉친다
        float fade = 1.0 - smoothstep(uFade * 0.2, uFade, dist);
        vec3 base = mix(uBase, uHorizon, smoothstep(uFade * 0.25, uFade * 1.4, dist));
        float minor = gridLine(vWorld.xy, uMinor, 1.0) * 0.45;
        float major = gridLine(vWorld.xy, uMajor, 1.3);
        vec3 c = mix(base, uLine, minor * fade);
        c = mix(c, uLineMajor, major * fade);
        gl_FragColor = vec4(c, 1.0);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
  mesh.renderOrder = -2;
  return mesh;
}

/**
 * 위경도 그래티큘 — 0.1° 간격 선 + 지도 경계.
 * 지도가 실제 좌표계 위에 있음을 눈으로 확인하는 용도.
 */
export function buildGraticule(meta, refLat, refLon, stepDeg = 0.1) {
  const cosRef = Math.cos(refLat * DEG);
  const toEast = (lon) => (lon - refLon) * DEG * EARTH_RADIUS_M * cosRef;
  const toNorth = (lat) => (lat - refLat) * DEG * EARTH_RADIUS_M;

  const halfLat = meta.height_m / 2 / (DEG * EARTH_RADIUS_M);
  const halfLon = meta.width_m / 2 / (DEG * EARTH_RADIUS_M * cosRef);
  const latMin = meta.center_lat - halfLat;
  const latMax = meta.center_lat + halfLat;
  const lonMin = meta.center_lon - halfLon;
  const lonMax = meta.center_lon + halfLon;

  const pts = [];
  const snap = (v) => Math.ceil(v / stepDeg) * stepDeg;
  for (let lat = snap(latMin); lat <= latMax; lat += stepDeg) {
    pts.push(toEast(lonMin), toNorth(lat), 0, toEast(lonMax), toNorth(lat), 0);
  }
  for (let lon = snap(lonMin); lon <= lonMax; lon += stepDeg) {
    pts.push(toEast(lon), toNorth(latMin), 0, toEast(lon), toNorth(latMax), 0);
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
  const lines = new THREE.LineSegments(geom, new THREE.LineBasicMaterial({
    color: 0xffffff, transparent: true, opacity: 0.22, depthWrite: false,
  }));
  lines.position.z = 2; // 지도 위로 살짝 띄워 z-fighting 회피
  lines.frustumCulled = false;
  return lines;
}

// ── 실사 바다 ────────────────────────────────────────────────────────────
// 왜 바다인가 — 엔진 물리가 평지다(평면근사 투영, 하드덱은 **해수면** 1,000ft 고정).
// 실지형 고도를 넣으면 산을 통과해 나는 화면이 되어 승패 판정과 모순된다. 평평해야
// 하는 지면 중 "실사"가 되는 것은 바다이고, 하드덱이 해수면 기준이라 의미도 맞는다.
//
// three.js 공식 Water(webgl_shaders_ocean)는 반사 카메라로 한 번 더 렌더한다. 이 뷰어는
// 본 화면 + 1인칭 2개를 한 프레임에 그리므로 반사 패스가 **프레임당 3번** 붙는다.
// 게다가 교전 고도는 12,000~25,000ft — 그 높이에서 수면에 비치는 기체는 보이지 않고,
// 눈에 들어오는 것은 ①시야각에 따른 색 변화(프레넬) ②태양 반짝임 길(글리터)
// ③잔물결 질감뿐이다. 그래서 그 셋만 셰이더로 직접 낸다 — 추가 패스 0.
export function buildSeaGround(size, sunDir, horizonColor) {
  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uSun: { value: sunDir.clone().normalize() },
      uHorizon: { value: new THREE.Color(horizonColor) },
      uDeep: { value: new THREE.Color(0x0b2a45) },     // 깊은 바다(수직으로 볼 때)
      uShallow: { value: new THREE.Color(0x2f6d95) },  // 비스듬히 볼 때 밝아진다
    },
    fog: false,
    vertexShader: `
      varying vec3 vWorld;
      void main() {
        vec4 w = modelMatrix * vec4(position, 1.0);
        vWorld = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: `
      precision highp float;
      uniform float uTime;
      uniform vec3 uSun, uDeep, uShallow, uHorizon;
      varying vec3 vWorld;

      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float noise(vec2 p){
        vec2 i = floor(p), f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash(i), hash(i+vec2(1,0)), u.x),
                   mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
      }

      void main() {
        vec3 V = normalize(cameraPosition - vWorld);
        float dist = length(cameraPosition - vWorld);

        // 잔물결 법선 — 두 방향으로 흐르는 노이즈를 겹쳐 규칙적인 줄무늬를 피한다.
        // 진폭을 거리로 죽인다: 멀리서 픽셀보다 잔 물결을 그리면 지글거림(에일리어싱)만 는다.
        float fade = 1.0 / (1.0 + dist * 0.0009);
        vec2 p = vWorld.xy * 0.010;
        float t = uTime * 0.35;
        float h = noise(p + vec2(t, t * 0.6)) + 0.5 * noise(p * 2.3 - vec2(t * 0.8, t));
        float e = 0.35;
        vec2 dp = vec2(
          noise(p + vec2(e, 0.0) + vec2(t, t*0.6)) - noise(p - vec2(e, 0.0) + vec2(t, t*0.6)),
          noise(p + vec2(0.0, e) + vec2(t, t*0.6)) - noise(p - vec2(0.0, e) + vec2(t, t*0.6)));
        vec3 N = normalize(vec3(-dp * 2.2 * fade, 1.0));

        // ① 프레넬 — 수직으로 내려다보면 짙고, 비스듬히 보면 하늘을 반사해 밝아진다.
        float f = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 4.0);
        vec3 col = mix(uDeep, uShallow, 0.35 + 0.25 * h);
        col = mix(col, uHorizon, clamp(f, 0.0, 0.92));

        // ② 태양 반짝임 길 — 수면 법선이 흔들려 정반사 방향이 흩어진 것. 좁고 밝다.
        vec3 H = normalize(uSun + V);
        float spec = pow(max(dot(N, H), 0.0), 220.0);
        col += vec3(1.0, 0.95, 0.85) * spec * 1.4 * fade;
        // 넓게 퍼지는 글리터(잔물결 다발의 합)
        col += vec3(1.0, 0.93, 0.80) * pow(max(dot(N, H), 0.0), 24.0) * 0.10 * fade;

        // ③ 원경은 지평 색으로 — 수평선이 자연스럽게 이어진다.
        col = mix(col, uHorizon, clamp(dist * 0.0000085, 0.0, 0.85));
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
  // z-up 씬에서 PlaneGeometry 의 법선(+Z)은 이미 위를 향한다 — 회전 불필요.
  mesh.renderOrder = -2;
  return mesh;
}

// ── 구름층 ───────────────────────────────────────────────────────────────
// 교전 고도가 12,000~25,000ft 라, 그 **아래**에 적운 갑판(약 6,000ft)과 **위**에
// 권운(약 32,000ft)을 두면 교전을 가리지 않으면서 고도감·속도감이 생긴다.
// 볼류메트릭 레이마칭은 1인칭 2개 포함 프레임당 3번 돌아 너무 비싸므로, 각 층을
// 평면 한 장 + fbm 노이즈 알파로 낸다(위·아래 양면에서 보이도록 DoubleSide).
const FT_TO_M_C = 0.3048;

export function buildCloudLayer(size, altFt, opts = {}) {
  const {
    scale = 1 / 9000,      // 노이즈 셀 크기[1/m] — 작을수록 구름 덩이가 크다
    cover = 0.48,          // 피복률 문턱 — 낮을수록 구름이 많다
    softness = 0.30,       // 가장자리 부드러움
    tint = 0xffffff,
    opacity = 0.85,
    drift = 0.004,         // 흐르는 속도[셀/초]
  } = opts;
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, fog: false,
    uniforms: {
      uTime: { value: 0 }, uScale: { value: scale }, uCover: { value: cover },
      uSoft: { value: softness }, uTint: { value: new THREE.Color(tint) },
      uOpacity: { value: opacity }, uDrift: { value: drift },
    },
    vertexShader: `
      varying vec3 vWorld;
      void main() {
        vec4 w = modelMatrix * vec4(position, 1.0);
        vWorld = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: `
      precision highp float;
      uniform float uTime, uScale, uCover, uSoft, uOpacity, uDrift;
      uniform vec3 uTint;
      varying vec3 vWorld;
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float noise(vec2 p){
        vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(hash(i), hash(i+vec2(1,0)), u.x),
                   mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
      }
      float fbm(vec2 p){
        float v = 0.0, a = 0.5;
        for (int k = 0; k < 5; k++) { v += a * noise(p); p = p * 2.03 + 11.7; a *= 0.5; }
        return v;
      }
      void main() {
        vec2 p = vWorld.xy * uScale + vec2(uTime * uDrift, uTime * uDrift * 0.4);
        float d = fbm(p);
        // 피복 문턱 위만 구름 — 아래는 맑은 하늘(구멍)이라 갑판이 끊겨 보인다.
        float a = smoothstep(uCover, uCover + uSoft, d);
        // 시선이 스칠수록 층이 두껍게 보인다(광학 두께) — 지평 근처가 짙어진다.
        vec3 V = normalize(cameraPosition - vWorld);
        float graze = 1.0 - abs(V.z);
        a *= (0.75 + 0.6 * graze);
        // 멀리서는 지평 haze 에 녹는다
        a *= 1.0 / (1.0 + length(cameraPosition.xy - vWorld.xy) * 0.000006);
        if (a < 0.01) discard;
        gl_FragColor = vec4(uTint, clamp(a, 0.0, 1.0) * uOpacity);
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), material);
  mesh.position.z = altFt * FT_TO_M_C;
  mesh.renderOrder = -1;
  return mesh;
}
