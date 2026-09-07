// F-16 3D 모델 로더 — glTF 지오메트리에 뷰어의 팀색 식별 규약을 입힌다.
//
// 실루엣은 실제 기체를 쓰되, 판독에 필요한 두 단서는 절차적 형상 시절 그대로 유지한다:
//   · 상면 = 팀색 / 하면 = 연한 톤  → 배면비행 육안 식별
//   · 격추 시 회색 전환             → setUnitColor 트래버스가 계속 먹는다
// 원본 도장(위장·마킹)을 보고 싶으면 URL 에 `?skin=real` — 대신 청/적 구분은 사라진다.
import * as THREE from "three";
import { GLTFLoader } from "./vendor/GLTFLoader.js";

const MODEL_URL = "./models/f16/F16.gltf";

// 모델 로컬축(기수 +X, 상방 +Y, 우익 +Z) → 뷰어 규약(기수 +Y, 상방 +Z, 우익 +X).
// 축의 순환 치환이라 행렬식 +1 — 거울 반전이 아니다(반전되면 롤 방향이 뒤집혀 보인다).
const AXIS_REMAP = new THREE.Matrix4().set(
  0, 0, 1, 0,
  1, 0, 0, 0,
  0, 1, 0, 0,
  0, 0, 0, 1,
);

// 원본(Sketchfab)의 부품 이름은 실제 부위와 어긋나 있다 — 예컨대 `instrGlass` 는
// 계기 유리가 아니라 익단·미익의 항법등 유리다. 아래 분류는 이름이 아니라 부품별
// 점군을 측면·평면으로 찍어 눈으로 확인한 결과다.
const HIDDEN = [
  "landingOn",       // 전개된 착륙장치 + 착륙등 — 공중전 중에는 접혀 있다
  "instrGlass",      // 항법등 유리(정점 306개) — 표시 축척에서 보이지 않음
  "hud",             // HUD 유리(정점 21개) — 동상
];
const GLASS = ["canopy"];

let pending = null;

/** 모델을 1회만 로드해 정규화한 부품 배열을 돌려준다. 실패 시 null(호출부가 폴백). */
export function loadF16() {
  if (!pending) {
    pending = new GLTFLoader().loadAsync(MODEL_URL).then(normalize).catch((err) => {
      console.warn("F-16 모델 로드 실패 — 절차적 형상으로 폴백합니다:", err);
      return null;
    });
  }
  return pending;
}

/** 노드 변환·축 규약·축척을 지오메트리에 구워 넣어 부품 목록으로 만든다. */
function normalize(gltf) {
  const parts = [];
  gltf.scene.updateWorldMatrix(true, true);
  gltf.scene.traverse((obj) => {
    if (!obj.isMesh) return;
    // 부위 이름은 메시가 아니라 그 부모 노드에 붙어 있다(Object_4 ← F-16-airframe_0).
    const name = obj.parent ? obj.parent.name : obj.name;
    if (HIDDEN.some((key) => name.includes(key))) return;
    const geom = obj.geometry.clone();
    geom.applyMatrix4(obj.matrixWorld); // 노드 회전 체인을 굽는다
    geom.applyMatrix4(AXIS_REMAP);      // 모델 축 → 뷰어 축
    parts.push({ geom, name, texturedMaterial: obj.material });
  });
  if (!parts.length) return null;

  // 전장(뷰어 +Y)을 1로, 중심을 원점으로 — 호출부는 displayLen 만 곱하면 된다.
  // 절차적 형상도 같은 규약이라 두 경로가 같은 크기로 그려진다.
  const box = new THREE.Box3();
  for (const part of parts) {
    part.geom.computeBoundingBox();
    box.union(part.geom.boundingBox);
  }
  const center = box.getCenter(new THREE.Vector3());
  const scale = 1 / (box.max.y - box.min.y);
  const fit = new THREE.Matrix4()
    .makeTranslation(-center.x, -center.y, -center.z)
    .premultiply(new THREE.Matrix4().makeScale(scale, scale, scale));
  for (const part of parts) part.geom.applyMatrix4(fit);
  return parts;
}

/** 부품 목록 → 한 기체의 Group. 지오메트리는 청/적이 공유하고 재질만 분리한다. */
export function buildF16(parts, { color, bellyColor, displayLen, realSkin }) {
  const group = new THREE.Group();
  for (const part of parts) {
    let material;
    if (realSkin) {
      material = part.texturedMaterial;
    } else if (GLASS.some((key) => part.name.includes(key))) {
      material = new THREE.MeshLambertMaterial({
        color: 0x233250, transparent: true, opacity: 0.85,
      });
    } else {
      material = teamMaterial(color, bellyColor);
    }
    const mesh = new THREE.Mesh(part.geom, material);
    // 팀색 재칠(setUnitColor) 대상은 기체 재질뿐 — 캐노피·원본 도장은 제외.
    mesh.userData.belly = material.userData.uBelly === undefined;
    group.add(mesh);
  }
  group.scale.setScalar(displayLen);
  return group;
}

/**
 * 상/하면 투톤 팀색 재질.
 *
 * 절차적 형상에서는 평면 삼각형의 FrontSide/BackSide 로 상·하면을 갈랐지만, 실제
 * 기체는 닫힌 입체라 그 수법이 통하지 않는다. 대신 기체 로컬 좌표의 법선 z 성분
 * (= 기체 기준 위쪽)으로 섞는다 — 자세와 무관하게 "동체 아랫면"이라는 고정된 면
 * 집합이 연한 톤이 되므로, 배면비행 때 그 면이 위로 보이는 효과는 그대로다.
 */
function teamMaterial(color, bellyColor) {
  const material = new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide });
  const uBelly = { value: new THREE.Color(bellyColor) };
  material.userData.uBelly = uBelly; // setUnitColor 가 격추 시 함께 회색으로
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uBelly = uBelly;
    shader.vertexShader = "varying float vUpN;\n" + shader.vertexShader.replace(
      "#include <beginnormal_vertex>",
      "#include <beginnormal_vertex>\n\tvUpN = objectNormal.z;",
    );
    shader.fragmentShader = "varying float vUpN;\nuniform vec3 uBelly;\n"
      + shader.fragmentShader.replace(
        "#include <color_fragment>",
        "#include <color_fragment>\n\tdiffuseColor.rgb = "
        + "mix(diffuseColor.rgb, uBelly, smoothstep(0.05, -0.35, vUpN));",
      );
  };
  return material;
}
