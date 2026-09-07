// 1인칭(콕핏) 뷰 카메라 배치 — scene.js 의 PIP 렌더가 쓴다.
// 씬/DOM 에 의존하지 않는 순수 기하만 두어 노드에서 그대로 검증한다
// (tests/test_map_geo.mjs).
import * as THREE from "three";

// 시야각. index.html 조준 링 반경(tan(각)/tan(FOV/2))과 짝이므로 함께 고쳐야 한다.
export const PIP_FOV_DEG = 65;

// 눈 위치: 기체 로컬 기준 기수쪽 +Y, 위쪽 +Z [m].
// CG(0,0,0)에 두면 동체 내부에서 보게 되므로 앞으로 빼 둔다.
export const EYE_OFFSET = new THREE.Vector3(0, 4.0, 1.2);

// 기체 메시는 기수 +Y / 상방 +Z 인데 카메라는 로컬 −Z 를 본다.
// Rx(+90°)가 −Z→+Y 로 보내고, 그때 카메라 상방(+Y)은 +Z(기체 상방)로 간다
// → 롤이 그대로 실려 배면비행이 화면에서도 뒤집힌다.
export const NOSE_ALIGN = new THREE.Quaternion()
  .setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);

const _eye = new THREE.Vector3();

/**
 * 콕핏 시점으로 카메라를 옮긴다.
 * @param {THREE.Camera} cam
 * @param {THREE.Quaternion} attitude - 기체 자세 (group.quaternion)
 * @param {{x:number,y:number,z:number}} pos - 기체 월드 위치 [m]
 */
export function placeEye(cam, attitude, pos) {
  cam.quaternion.copy(attitude).multiply(NOSE_ALIGN);
  // group 은 displayLen 으로 스케일돼 있으므로 회전만 적용해 월드 m 로 더한다
  _eye.copy(EYE_OFFSET).applyQuaternion(attitude);
  cam.position.set(pos.x + _eye.x, pos.y + _eye.y, pos.z + _eye.z);
}
