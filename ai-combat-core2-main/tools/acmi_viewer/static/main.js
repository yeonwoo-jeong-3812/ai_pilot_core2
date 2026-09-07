// 글루: 리플레이 목록 → 로드/파싱 → 씬·HUD 구동 (requestAnimationFrame 루프).
import { parseACMI, buildTracks } from "./acmi.js";
import { ReplayScene } from "./scene.js";
import { HUD } from "./hud.js";
import { CombatAudio } from "./audio.js";

// Gun WEZ 표시 상수 — RULEBOOK §4 / aircombat/geometry/units.py 와 동일.
// 강조 판정은 ACMI의 InWEZ 플래그를 그대로 쓰고, 원뿔은 시각 참고용.
const WEZ = { maxRangeM: 3000 * 0.3048, halfAngleDeg: 30.0 };

let scene;
try {
  scene = new ReplayScene(document.getElementById("scene"));
} catch (err) {
  // WebGL 불가 (그래픽 가속 꺼짐 등) — 죽은 화면 대신 안내
  document.getElementById("status").innerHTML =
    "WebGL을 사용할 수 없습니다.<br>" +
    "브라우저 설정에서 <b>그래픽(하드웨어) 가속</b>을 켜고 재시작하세요:<br>" +
    "Chrome: chrome://settings/system · Edge: edge://settings/system<br>" +
    "상태 확인: chrome://gpu";
  throw err;
}

// 배속 사다리. « / » 버튼이 이 위를 한 칸씩 오르내린다(항상 양수 = 정재생).
const SPEEDS = [0.25, 0.5, 1, 2, 4, 8];

const state = {
  parsed: null,
  tracks: null, // {blue, red}
  time: 0,
  playing: true,
  speed: 1,
  lastFrame: null,
};

// 소리는 합성이다(음원 파일 없음). 브라우저 자동재생 정책 때문에 **버튼을 누른
// 시점에만** AudioContext 를 만든다 — 그 전에는 오디오 객체가 아무것도 하지 않는다.
const audio = new CombatAudio();
const soundBtn = document.getElementById("sound-toggle");
soundBtn?.addEventListener("click", async () => {
  if (audio.enabled) {
    audio.disable();
    soundBtn.textContent = "🔇 소리";
    return;
  }
  soundBtn.textContent = "소리 …";
  if (await audio.enable()) {
    soundBtn.textContent = `🔊 소리`;
    soundBtn.title = `음원: ${audio.source}`;
  } else {
    soundBtn.textContent = "소리 불가";
    soundBtn.disabled = true;
  }
});

const hud = new HUD({
  onSeek: (t) => { state.time = t; },
  onPlayToggle: () => { state.playing = !state.playing; hud.setPlaying(state.playing); },
  // 배속 한 단계 증감. dir=+1 빠르게, −1 느리게. 사다리 양끝에서 멈춘다.
  // (역재생은 없앴다 — "8×에서 뒤로가기 = 4×,2×,1× 로 감속" 이 요청 동작.)
  onSpeedStep: (dir) => {
    const i = SPEEDS.indexOf(state.speed);
    state.speed = SPEEDS[Math.min(Math.max((i < 0 ? 2 : i) + dir, 0), SPEEDS.length - 1)];
    if (!state.playing) { state.playing = true; hud.setPlaying(true); }
    hud.setSpeed(state.speed);
  },
  // 방향키 = 시점 이동(스크럽). 재생 중이든 아니든 그 자리에서 초 단위로 민다.
  onNudge: (sec) => {
    state.time = Math.min(Math.max(state.time + sec, state.parsed.startTime),
                          state.parsed.endTime);
  },
  onCamera: (mode) => scene.setCameraMode(mode),
  onGround: (mode) => scene.setGroundMode(mode),
  onReplay: (name) => loadReplay(`/replays/${encodeURIComponent(name)}`, name),
});

/**
 * 이 녹화에서 "우리 기체"가 앉은 진영. 모르면 null (표시하지 않는다 — 틀리게
 * 단정하느니 비워 두는 편이 낫다).
 *
 * 로스터 배치는 상대 64종을 **양 진영으로 다 돌리므로** 우리 기체가 BLUE 인 판과
 * RED 인 판이 섞여 있다. run_match.py 의 `run_roster` 가 파일명을
 * `vs_<상대>_<내진영>.acmi` 로 찍으므로(scripts/run_match.py) 거기서 읽어 낸다.
 * 단판 녹화(`{일시}_{blue}_vs_{red}.acmi`)는 규약이 다르므로 추정하지 않는다.
 * `?me=blue|red` 로 언제든 덮어쓸 수 있다.
 */
function resolveMineSide(name) {
  const forced = new URLSearchParams(location.search).get("me");
  if (forced === "blue" || forced === "red") return forced;
  const base = name.split("/").pop() ?? "";
  const m = /^vs_.*_(blue|red)\.acmi$/i.exec(base);
  return m ? m[1].toLowerCase() : null;
}

/** URL에서 ACMI를 받아 파싱·장착. 웹 이식 시 이 함수만 다른 URL로 호출하면 된다. */
async function loadReplay(url, name) {
  hud.setStatus(`로딩: ${name} …`);
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const parsed = parseACMI(text);
    const { blue, red, refLat, refLon } = buildTracks(parsed);

    state.parsed = parsed;
    state.tracks = { blue, red };
    state.time = parsed.startTime;
    state.playing = true;
    hud.setPlaying(true);

    scene.setTracks(blue, red, WEZ, { refLat, refLon });
    hud.setReplay(parsed, blue, red);
    hud.setSpeed(state.speed);
    hud.setPipLabels(blue, red, resolveMineSide(name));
    hud.setStatus("");
  } catch (err) {
    hud.setStatus(`로드 실패: ${err.message}`);
  }
}

async function init() {
  try {
    hud.setGroundMode(scene.groundMode);
    // 기체 모델은 첫 리플레이를 그리기 전에 확보한다(실패해도 절차적 형상으로 진행).
    await scene.loadAssets();
    const res = await fetch("/api/replays");
    const { replays } = await res.json();
    if (!replays.length) {
      hud.setStatus("replays/ 에 .acmi 파일이 없습니다.");
      return;
    }
    const params = new URLSearchParams(location.search);
    const requested = params.get("replay");
    const name = replays.includes(requested) ? requested : replays[0];
    hud.setReplayList(replays, name);
    await loadReplay(`/replays/${encodeURIComponent(name)}`, name);
    const t0 = parseFloat(params.get("t"));
    if (Number.isFinite(t0)) state.time = t0; // ?t=초 로 특정 시각 바로 열기
  } catch (err) {
    hud.setStatus(`목록 로드 실패: ${err.message}`);
  }
}

function frame(now) {
  requestAnimationFrame(frame);
  // 탭 백그라운드 복귀·파싱 블로킹 시 dt 폭주 → 끝으로 점프 방지
  const dt = state.lastFrame === null ? 0
    : Math.min((now - state.lastFrame) / 1000, 0.1);
  state.lastFrame = now;

  if (!state.parsed) return;
  if (state.playing) {
    state.time += dt * state.speed;
    if (state.time >= state.parsed.endTime) {
      state.time = state.parsed.endTime;
      state.playing = false; hud.setPlaying(false);
    }
  }
  const states = scene.update(state.time);
  hud.update(state.time, states, state.tracks, scene.pipCams);
  // 관측자는 카메라다 — 거리 감쇠·도플러의 기준점.
  audio.update(states, state.tracks, scene.camera.position,
               state.speed, state.playing);
}

init();
requestAnimationFrame(frame);
