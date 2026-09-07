// ACMI(Tacview 2.x text) 파서 — ai-combat-core2 출력 전용.
// 범용 Tacview 호환 아님: core2 acmi.py가 쓰는 부분집합(전 프레임 T= 갱신,
// 단일 청/적 객체, 0,Event=Bookmark)만 다룬다.

const EARTH_RADIUS_M = 6378137.0;
const DEG = Math.PI / 180.0;

const META_KEYS = new Set(["Name", "Type", "Color", "Coalition", "CallSign"]);

/**
 * ACMI 텍스트를 파싱해 객체별 트랙과 이벤트를 돌려준다.
 * @param {string} text - .acmi 파일 전체 문자열
 * @returns {{
 *   header: Object,
 *   objects: Map<string, Object>,
 *   bookmarks: {time: number, text: string}[],
 *   startTime: number, endTime: number
 * }}
 */
export function parseACMI(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);

  const header = {};
  const objects = new Map();
  const bookmarks = [];
  let time = 0.0;

  for (let start = 0; start < text.length; ) {
    let end = text.indexOf("\n", start);
    if (end < 0) end = text.length;
    let line = text.slice(start, end);
    start = end + 1;
    if (line.endsWith("\r")) line = line.slice(0, -1);
    if (!line) continue;

    if (line.charCodeAt(0) === 0x23 /* '#' */) {
      time = parseFloat(line.slice(1));
      continue;
    }

    const comma = line.indexOf(",");
    if (comma < 0) {
      const eq = line.indexOf("=");
      if (eq > 0) header[line.slice(0, eq)] = line.slice(eq + 1);
      continue;
    }

    const id = line.slice(0, comma);
    const rest = line.slice(comma + 1);

    if (id === "0") {
      const eq = rest.indexOf("=");
      if (eq < 0) continue;
      const key = rest.slice(0, eq);
      const value = rest.slice(eq + 1);
      if (key === "Event") {
        const bar = value.indexOf("|");
        bookmarks.push({
          time,
          text: bar >= 0 ? value.slice(bar + 1).trim() : value.trim(),
        });
      } else {
        header[key] = value;
      }
      continue;
    }

    let obj = objects.get(id);
    if (!obj) {
      obj = {
        id,
        meta: {},
        times: [],
        lon: [], lat: [], alt: [],
        roll: [], pitch: [], yaw: [],
        attrs: {},
      };
      objects.set(id, obj);
    }
    parseObjectLine(obj, rest, time);
  }

  let startTime = Infinity;
  let endTime = -Infinity;
  for (const obj of objects.values()) {
    if (!obj.times.length) continue;
    startTime = Math.min(startTime, obj.times[0]);
    endTime = Math.max(endTime, obj.times[obj.times.length - 1]);
  }
  if (!isFinite(startTime)) { startTime = 0; endTime = 0; }

  return { header, objects, bookmarks, startTime, endTime };
}

// "T=...|...,Key=Value,Key=Value" 한 줄을 객체 레코드에 반영한다.
// core2 값에는 콤마가 없으므로 콤마 분리로 충분하다 (Tacview '\,' 이스케이프 미지원).
function parseObjectLine(obj, rest, time) {
  for (const segment of rest.split(",")) {
    const eq = segment.indexOf("=");
    if (eq < 0) continue;
    const key = segment.slice(0, eq);
    const value = segment.slice(eq + 1);

    if (key === "T") {
      pushTransform(obj, value, time);
    } else if (META_KEYS.has(key)) {
      // 최초 선언 우선 — 격추 시 Color=Grey 재선언 등 후속 변경은 무시
      if (!(key in obj.meta)) obj.meta[key] = value;
    } else {
      setAttr(obj, key, value);
    }
  }
}

// T=lon|lat|alt|roll|pitch|yaw — 빈 필드는 직전 샘플 값 유지.
function pushTransform(obj, value, time) {
  const parts = value.split("|");
  const last = obj.times.length - 1;
  const prev = (arr, fallback) => (last >= 0 ? arr[last] : fallback);
  const field = (i, arr) => {
    const s = parts[i];
    return s === undefined || s === "" ? prev(arr, 0) : parseFloat(s);
  };
  obj.lon.push(field(0, obj.lon));
  obj.lat.push(field(1, obj.lat));
  obj.alt.push(field(2, obj.alt));
  obj.roll.push(field(3, obj.roll));
  obj.pitch.push(field(4, obj.pitch));
  obj.yaw.push(field(5, obj.yaw));
  obj.times.push(time);
}

// 속성은 현재(마지막) 샘플에 정렬해 저장. 숫자는 number, True/False는
// boolean, 그 외(L1/L2/L3 등)는 문자열 그대로.
function setAttr(obj, key, value) {
  const index = obj.times.length - 1;
  if (index < 0) return;
  let arr = obj.attrs[key];
  if (!arr) arr = obj.attrs[key] = [];
  while (arr.length < index) arr.push(null);
  arr[index] = coerce(value);
}

function coerce(value) {
  if (value === "True") return true;
  if (value === "False") return false;
  const n = Number(value);
  return Number.isFinite(n) && value.trim() !== "" ? n : value;
}

/**
 * 파싱 결과를 뷰어용 트랙으로 변환: 측지 좌표를 로컬 ENU(m)로 투영하고
 * 청/적 역할을 식별한다. 기준점은 두 트랙 첫 샘플의 중점.
 * @returns {{ blue: Object, red: Object, refLat: number, refLon: number }}
 */
export function buildTracks(parsed) {
  const refLon0 = parseFloat(parsed.header.ReferenceLongitude || "0");
  const refLat0 = parseFloat(parsed.header.ReferenceLatitude || "0");

  const tracks = [];
  for (const obj of parsed.objects.values()) {
    if (obj.times.length) tracks.push(obj);
  }
  if (tracks.length < 2) throw new Error("ACMI에 항공기 트랙이 2개 미만입니다.");

  const blue = tracks.find((o) => o.meta.Color === "Blue") || tracks[0];
  const red = tracks.find((o) => o !== blue && o.meta.Color === "Red") ||
    tracks.find((o) => o !== blue);

  const refLat = refLat0 + (blue.lat[0] + red.lat[0]) / 2;
  const refLon = refLon0 + (blue.lon[0] + red.lon[0]) / 2;
  const cosRefLat = Math.cos(refLat * DEG);

  for (const obj of [blue, red]) {
    const n = obj.times.length;
    const pos = new Float64Array(n * 3); // [east, north, up] m
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (refLon0 + obj.lon[i] - refLon) * DEG * EARTH_RADIUS_M * cosRefLat;
      pos[i * 3 + 1] = (refLat0 + obj.lat[i] - refLat) * DEG * EARTH_RADIUS_M;
      pos[i * 3 + 2] = obj.alt[i];
    }
    obj.position = pos;
  }
  return { blue, red, refLat, refLon };
}

/** 시각 t 이전(포함) 가장 가까운 샘플 인덱스 (이진 탐색). */
export function indexAt(track, t) {
  const times = track.times;
  let lo = 0;
  let hi = times.length - 1;
  if (t <= times[0]) return 0;
  if (t >= times[hi]) return hi;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

/** "k1=v1 k2=v2" packed 결정 문자열(L1/L2/L3) → 객체. 문자열 아니면 빈 객체. */
export function parsePacked(str) {
  const out = {};
  if (typeof str !== "string") return out;
  for (const m of str.matchAll(/(\w+)=(\S+)/g)) out[m[1]] = m[2];
  return out;
}

/** 트랙의 i번째 속성값 (없으면 null). */
export function attrAt(track, key, i) {
  const arr = track.attrs[key];
  if (!arr || i >= arr.length) return null;
  const v = arr[i];
  return v === undefined ? null : v;
}
