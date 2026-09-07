// acmi.js 파서 자가 검증: 실제 리플레이를 파싱해 .txt 결과와 대조.
// 실행: node tools/acmi_viewer/tests/test_acmi_parse.mjs  (repo 루트 기준 자동 탐색)
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

import { parseACMI, buildTracks, indexAt, attrAt } from "../static/acmi.js";

// 표본 상한 — 녹화가 세대별 폴더로 쌓여 500판을 넘고 판당 10MB급이라 전수 파싱은
// 몇 분이 걸린다. 정렬 후 등간격으로 뽑아 결정론을 유지하면서 상한만 건다.
const SAMPLE_CAP = 12;

const REPLAYS = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "replays");

function load(name) {
  const parsed = parseACMI(readFileSync(join(REPLAYS, name), "utf-8"));
  return { parsed, tracks: buildTracks(parsed) };
}

// --- 공통 불변식: replays/ 이하(하위 폴더 포함)의 .acmi 표본 ---
// 녹화는 canon/·archive/·legacy/ 하위에 있으므로 재귀로 훑는다. 최상위만 보면
// 목록이 비어 통과해 버려, 검증이 조용히 죽는다.
function listReplays(dir, prefix = "") {
  const out = [];
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${ent.name}` : ent.name;
    if (ent.isDirectory()) out.push(...listReplays(join(dir, ent.name), rel));
    else if (ent.name.endsWith(".acmi")) out.push(rel);
  }
  return out;
}

const all = listReplays(REPLAYS).sort();
assert.ok(all.length > 0, "replays/에 .acmi가 없음");
const step = Math.max(1, Math.ceil(all.length / SAMPLE_CAP));
const files = all.filter((_, i) => i % step === 0);
for (const name of files) {
  const { parsed, tracks } = load(name);
  const { blue, red } = tracks;
  // 매치 리플레이는 Blue/Red, 유도 트랙 등 단독 실행물은 Grey일 수 있음
  assert.ok(blue !== red && blue && red, `${name}: 트랙 2개 식별`);
  for (const t of [blue, red]) {
    assert.ok(t.times.length > 10, `${name}: 샘플 수`);
    for (let i = 1; i < t.times.length; i++) {
      assert.ok(t.times[i] >= t.times[i - 1], `${name}: 시간 단조증가`);
    }
    const health = t.attrs.Health;
    assert.ok(health && health.length > 0, `${name}: Health 존재`);
    assert.equal(health[0], 100.0, `${name}: 초기 HP 100`);
  }
  assert.ok(parsed.endTime > parsed.startTime, `${name}: 시간 범위`);
  // ENU 변환 퇴화 여부만 확인 (근접 CZ 시나리오는 3,000ft=914m에서 시작)
  const d0 = Math.hypot(
    blue.position[0] - red.position[0],
    blue.position[1] - red.position[1],
  );
  assert.ok(d0 > 100, `${name}: 초기 수평거리 ${d0.toFixed(0)}m`);
}

// --- 수치 앵커: 결과 로그(.txt)가 딸린 녹화는 최종 HP를 대조 ---
// 예전에는 특정 파일 하나에 고정돼 있었는데, 그 녹화가 폴더 정리 때 사라지면서
// 대조가 조용히 꺼져 있었다. 이제는 짝이 되는 .txt 가 있는 녹화면 무엇이든 잡는다.
let anchored = 0;
for (const name of all) {
  const txt = join(REPLAYS, name.replace(/\.acmi$/, ".txt"));
  if (!existsSync(txt)) continue;
  const m = readFileSync(txt, "utf-8")
    .match(/HP\s+:\s+blue=([\d.]+)\s+red=([\d.]+)/);
  if (!m) continue;
  const { blue, red } = load(name).tracks;
  const last = blue.times.length - 1;
  assert.ok(Math.abs(attrAt(blue, "Health", last) - parseFloat(m[1])) < 0.5,
    `${name}: blue 최종 HP (로그 ${m[1]})`);
  assert.ok(Math.abs(attrAt(red, "Health", last) - parseFloat(m[2])) < 0.5,
    `${name}: red 최종 HP (로그 ${m[2]})`);
  anchored += 1;
}
assert.ok(anchored > 0, "결과 로그와 대조할 녹화가 하나도 없음 — 수치 앵커가 꺼져 있다");
console.log(`anchor OK: 결과 로그 대조 ${anchored}판`);

console.log(`OK: ${files.length}/${all.length}개 리플레이 파싱 검증 통과(등간격 표본)`);
