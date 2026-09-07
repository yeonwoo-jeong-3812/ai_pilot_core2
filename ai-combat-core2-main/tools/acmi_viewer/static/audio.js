/**
 * 교전 사운드 — **실제 녹음**을 Web Audio 로 가공해 낸다.
 *   · 엔진/비행음: `audio/jet.*` (루프)
 *   · 기총:        `audio/gun.*` (사격 중 루프)
 * 음원을 못 읽으면 **합성으로 폴백**한다(아래 클래스가 그대로 남아 있다) — 파일이
 * 없는 배포에서도 소리가 나야 하고, 합성 경로가 있어야 음원 라이선스가 곤란해질 때
 * 폴더만 지우면 되기 때문이다(F-16 모델과 같은 대응).
 *
 * 합성 폴백을 남겨 두는 이유
 * --------------------------
 * ① 라이선스 — 이 저장소는 외부 자산을 들일 때마다 조건을 따져 왔다(F-16 모델이
 *    CC BY-NC-SA 라 공개 전환 시 문제라고 기록해 둔 것과 같은 이유). 합성이면 그
 *    문제가 아예 없다.
 * ② 연속 변화 — 엔진음은 스로틀·거리·상대속도로 매 프레임 변해야 한다. 파라미터를
 *    직접 미는 편이 녹음 크로스페이드보다 정확하고 가볍다.
 * ③ 배속·스크럽 — 0.25~8배속과 임의 시각 점프에 재생 위치를 맞출 필요가 없다.
 *
 * 소음 구조 — 왜 이렇게 쌓는가
 * ---------------------------
 * 초판은 대역통과 잡음 하나 + 톱니 하나였는데 바람소리처럼 들렸다. 실제 제트 소음은
 * 성격이 다른 성분들의 합이다:
 *
 * · **제트 혼합 소음(jet mixing)** — 광대역이고 **저주파가 몸통**이다. 노즐 근처의
 *   작은 와류가 고주파를, 하류의 큰 와류(제트 지름 규모)가 저주파를 낸다. 그래서
 *   저역 럼블 · 중역 로어 · 고역 히스를 따로 쌓아야 두께가 생긴다.
 * · **버즈소** — 팬/압축기는 축 회전수의 배음 다발을 낸다(50~2400Hz 대역에 50~60Hz
 *   간격의 톤 계열). 톱니파가 정확히 그 구조(기본파 f₀ 의 정수배 배음)라 톱니를
 *   공진 대역통과로 훑으면 그 금속성 소리가 난다. **가속하면 f₀ 가 올라간다** —
 *   이것이 "가속음"의 정체다.
 * · **AB** — 후기연소는 저주파 연소 불안정 럼블에, 초음속 제트의 충격-연계 소음
 *   (스크리치)이 얹힌다. 좁은 공진 하나로 그 날카로움을 흉내낸다.
 * · **대기 흡수** — 거리가 멀수록 고역이 먼저 죽는다. 그래서 보이스마다 거리에 따라
 *   저역통과를 건다. 멀리 있는 제트가 "우웅" 하고만 들리는 이유가 이것이라, 이걸
 *   빼면 아무리 쌓아도 가까이 있는 소리처럼 들린다.
 *
 * · **기총** — M61A1 은 분당 6,000발 = **초당 100발**이라 개별 발사음이 아니라 100Hz
 *   펄스열로 들린다("BRRRT"). 낱발을 100개/초 예약하는 대신 100Hz 톱니 LFO 로 진폭을
 *   깎아 연속 버스로 낸다(노드 수가 일정하고 소리도 끊기지 않는다).
 *
 * 공간감은 합성 임펄스 응답(잡음 감쇠)으로 만든 컨볼루션 잔향을 옅게 섞어 낸다 —
 * 이것도 파일이 아니다.
 */

import { attrAt } from "./acmi.js";

const SPEED_OF_SOUND = 340.0;   // m/s
const REF_DIST = 80.0;          // 이 거리에서 기준 음량 [m]
const MAX_DIST = 8000.0;        // 이보다 멀면 사실상 안 들린다 [m]

/** 결정론 잡음 — 같은 판이면 같은 소리(Math.random 미사용). */
function noiseBuffer(ctx, seconds = 3.0) {
  const n = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(1, n, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let seed = 12345;
  // 갈색잡음 쪽으로 살짝 기울인다(적분) — 백색잡음만 쓰면 쉭쉭거리기만 하고
  // 제트 소음의 저역 몸통이 안 생긴다.
  let last = 0;
  for (let i = 0; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    const w = (seed / 0x3fffffff) - 1.0;
    last = (last + 0.035 * w) / 1.035;
    d[i] = w * 0.5 + last * 6.0;
  }
  return buf;
}

/** 합성 임펄스 응답 — 개활지 반사. 잡음을 지수 감쇠시킨 것. */
function reverbIR(ctx, seconds = 1.6, decay = 3.2) {
  const n = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(2, n, ctx.sampleRate);
  let seed = 999;
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < n; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      const w = (seed / 0x3fffffff) - 1.0;
      d[i] = w * Math.pow(1 - i / n, decay);
    }
  }
  return buf;
}

function src(ctx, buf) {
  const s = ctx.createBufferSource();
  s.buffer = buf; s.loop = true; s.start();
  return s;
}

/** 브라우저가 재생 가능한 첫 포맷을 고른다(AAC 는 Firefox 에서 OS 의존). */
async function loadSample(ctx, base) {
  for (const ext of ["ogg", "m4a"]) {
    try {
      const r = await fetch(`./audio/${base}.${ext}`);
      if (!r.ok) continue;
      return await ctx.decodeAudioData(await r.arrayBuffer());
    } catch { /* 다음 포맷 */ }
  }
  return null;
}

/**
 * 녹음 기반 보이스. 엔진은 루프 재생하고 **재생속도로 RPM 을, 저역통과로 거리를**
 * 만든다(재생속도를 올리면 음정이 올라가는 것이 실제 회전수 변화와 같은 방향이다).
 * 기총은 사격 중에만 루프한다.
 */
class SampleVoice {
  constructor(ctx, jetBuf, gunBuf, dest) {
    this.ctx = ctx;
    this.out = ctx.createGain(); this.out.gain.value = 0;
    // 대기 흡수 — 거리로 고역을 깎는다. 이게 없으면 먼 제트가 코앞처럼 들린다.
    this.air = ctx.createBiquadFilter();
    this.air.type = "lowpass"; this.air.frequency.value = 18000; this.air.Q.value = 0.4;
    this.out.connect(this.air).connect(dest);

    this.jet = ctx.createBufferSource();
    this.jet.buffer = jetBuf; this.jet.loop = true;
    this.jetG = ctx.createGain(); this.jetG.gain.value = 1.0;
    this.jet.connect(this.jetG).connect(this.out);
    this.jet.start();                       // 오프셋 0 — 같은 판이면 같은 소리

    this.gunBuf = gunBuf;
    this.gunG = ctx.createGain(); this.gunG.gain.value = 0;
    this.gunG.connect(this.out);
    this.gunSrc = null;
  }

  /** silent = 격추됐거나 **재생이 멈춘** 상태 — 둘 다 소리를 끈다. */
  update(thr, dist, closing, firing, silent, rate) {
    const ctx = this.ctx, now = ctx.currentTime, S = 0.09;
    if (silent) {
      this.out.gain.setTargetAtTime(0, now, 0.3);
      this._gun(false, now); return;
    }
    const atten = dist >= MAX_DIST ? 0
      : Math.min(1, REF_DIST / Math.max(dist, 1)) * (1 - dist / MAX_DIST);
    this.out.gain.setTargetAtTime(atten, now, S);
    if (atten <= 0.0004) { this._gun(false, now); return; }

    this.air.frequency.setTargetAtTime(
      Math.max(320, 18000 * Math.exp(-dist / 900)), now, S);

    const dop = SPEED_OF_SOUND / Math.max(SPEED_OF_SOUND - closing, 50);
    const t = Math.min(Math.max(thr, 0), 1);
    // 재생속도 = RPM(스로틀) × 도플러 × 배속. 0.82(아이들) ~ 1.28(full AB).
    this.jet.playbackRate.setTargetAtTime(
      (0.82 + 0.46 * t) * dop * rate, now, S);
    this.jetG.gain.setTargetAtTime(0.55 + 0.65 * t, now, S);

    this._gun(firing, now, dop * rate);
  }

  _gun(on, now, rate = 1) {
    if (on && !this.gunSrc && this.gunBuf) {
      const s = this.ctx.createBufferSource();
      s.buffer = this.gunBuf; s.loop = true;
      s.playbackRate.value = rate;
      s.connect(this.gunG); s.start();
      this.gunSrc = s;
    }
    // ⚠ 거리 감쇠를 여기서 또 곱하면 안 된다 — 이 노드는 이미 감쇠가 걸린 out 을
    // 지난다. 예전엔 이중으로 곱해 800m 에서 0.0875² ≈ 0.8% 가 되어 **사격음이
    // 사실상 안 들렸다**. 엔진은 고정 게인이라 이 문제가 없어 눈치채기 어려웠다.
    this.gunG.gain.setTargetAtTime(on ? 2.2 : 0, now, on ? 0.008 : 0.05);
    if (!on && this.gunSrc) {
      const s = this.gunSrc; this.gunSrc = null;
      try { s.stop(now + 0.2); } catch { /* 이미 정지 */ }
    }
  }
}

/** 기체 한 대의 소리 묶음 (합성 폴백). */
class AircraftVoice {
  constructor(ctx, noise, dest) {
    this.ctx = ctx;
    this.out = ctx.createGain();
    this.out.gain.value = 0;

    // 대기 흡수 — 거리로 고역을 깎는다. 보이스 전체가 여기를 지난다.
    this.air = ctx.createBiquadFilter();
    this.air.type = "lowpass";
    this.air.frequency.value = 18000;
    this.air.Q.value = 0.4;
    this.out.connect(this.air).connect(dest);

    const bus = (node, g0) => {
      const g = ctx.createGain(); g.gain.value = g0;
      node.connect(g).connect(this.out); return g;
    };

    // ① 저역 럼블 — 제트 혼합 소음의 몸통(하류 큰 와류)
    this.rumbleF = ctx.createBiquadFilter();
    this.rumbleF.type = "lowpass"; this.rumbleF.frequency.value = 130;
    this.rumbleF.Q.value = 3.0;
    src(ctx, noise).connect(this.rumbleF);
    this.rumbleG = bus(this.rumbleF, 0);

    // ② 중역 로어
    this.roarF = ctx.createBiquadFilter();
    this.roarF.type = "bandpass"; this.roarF.frequency.value = 420;
    this.roarF.Q.value = 0.7;
    src(ctx, noise).connect(this.roarF);
    this.roarG = bus(this.roarF, 0);

    // ③ 고역 히스 — 노즐 근처 작은 와류. 가까울 때만 들린다.
    this.hissF = ctx.createBiquadFilter();
    this.hissF.type = "highpass"; this.hissF.frequency.value = 2600;
    src(ctx, noise).connect(this.hissF);
    this.hissG = bus(this.hissF, 0);

    // ④ 버즈소 — 축 회전수 f₀ 의 배음 다발. 톱니가 곧 그 구조다.
    this.saw = ctx.createOscillator();
    this.saw.type = "sawtooth"; this.saw.frequency.value = 90;
    this.sawF = ctx.createBiquadFilter();
    this.sawF.type = "bandpass"; this.sawF.frequency.value = 1200; this.sawF.Q.value = 2.2;
    this.saw.connect(this.sawF); this.saw.start();
    this.sawG = bus(this.sawF, 0);

    // ⑤ AB 스크리치 — 초음속 제트의 충격-연계 소음. 좁은 공진.
    this.screechF = ctx.createBiquadFilter();
    this.screechF.type = "bandpass"; this.screechF.frequency.value = 1500;
    this.screechF.Q.value = 9.0;
    src(ctx, noise).connect(this.screechF);
    this.screechG = bus(this.screechF, 0);

    // ⑥ 기총 — 100Hz 톱니 LFO 로 진폭을 깎아 펄스열을 만든다(연속 버스).
    this.gunBus = ctx.createGain(); this.gunBus.gain.value = 0;
    this.gunBus.connect(this.out);
    this.gunLevel = ctx.createGain(); this.gunLevel.gain.value = 0;  // LFO 가 흔드는 부분
    this.gunLevel.connect(this.gunBus);
    this.gunLfo = ctx.createOscillator();
    this.gunLfo.type = "sawtooth"; this.gunLfo.frequency.value = 100;
    this.gunLfoAmp = ctx.createGain(); this.gunLfoAmp.gain.value = -0.5;  // 1→0 감쇠형
    this.gunLfo.connect(this.gunLfoAmp).connect(this.gunLevel.gain);
    this.gunLfo.start();
    // 발사음 재료: 파열음(광대역) + 저역 텅
    const crack = ctx.createBiquadFilter();
    crack.type = "bandpass"; crack.frequency.value = 1800; crack.Q.value = 0.9;
    src(ctx, noise).connect(crack).connect(this.gunLevel);
    const thump = ctx.createBiquadFilter();
    thump.type = "lowpass"; thump.frequency.value = 160; thump.Q.value = 4.0;
    src(ctx, noise).connect(thump).connect(this.gunLevel);
    this.gunCrack = crack;
  }

  /** silent = 격추됐거나 **재생이 멈춘** 상태 — 둘 다 소리를 끈다. */
  update(thr, dist, closing, firing, silent, rate) {
    const ctx = this.ctx;
    const now = ctx.currentTime;
    const S = 0.09;

    if (silent) {
      this.out.gain.setTargetAtTime(0, now, 0.3);
      this.gunBus.gain.setTargetAtTime(0, now, 0.05);
      return;
    }
    const atten = dist >= MAX_DIST ? 0
      : Math.min(1, REF_DIST / Math.max(dist, 1)) * (1 - dist / MAX_DIST);
    this.out.gain.setTargetAtTime(atten, now, S);
    if (atten <= 0.0004) return;

    // 대기 흡수 — 멀수록 고역이 죽는다. 이게 없으면 먼 제트도 코앞처럼 들린다.
    const cutoff = Math.max(320, 18000 * Math.exp(-dist / 900));
    this.air.frequency.setTargetAtTime(cutoff, now, S);

    // 도플러 — f' = f·c/(c − v). 배속도 같이 곱한다.
    const dop = SPEED_OF_SOUND / Math.max(SPEED_OF_SOUND - closing, 50) * rate;
    const t = Math.min(Math.max(thr, 0), 1);

    this.rumbleG.gain.setTargetAtTime(0.55 + 0.35 * t, now, S);
    this.rumbleF.frequency.setTargetAtTime((95 + 70 * t) * dop, now, S);

    this.roarG.gain.setTargetAtTime(0.16 + 0.22 * t, now, S);
    this.roarF.frequency.setTargetAtTime((300 + 420 * t) * dop, now, S);

    this.hissG.gain.setTargetAtTime(0.010 + 0.030 * t, now, S);
    this.hissF.frequency.setTargetAtTime(2400 * dop, now, S);

    // 버즈소: f₀ 가 스로틀을 따라 오른다 = 가속음
    this.saw.frequency.setTargetAtTime((48 + 105 * t) * dop, now, S);
    this.sawF.frequency.setTargetAtTime((700 + 2200 * t) * dop, now, S);
    this.sawG.gain.setTargetAtTime(0.030 + 0.075 * t, now, S);

    const ab = t > 0.5 ? (t - 0.5) / 0.5 : 0;
    this.screechG.gain.setTargetAtTime(0.05 * ab, now, S);
    this.screechF.frequency.setTargetAtTime((1300 + 700 * ab) * dop, now, S);

    // 기총
    this.gunBus.gain.setTargetAtTime(firing ? 0.85 : 0.0, now, 0.012);
    if (firing) {
      this.gunLfo.frequency.setTargetAtTime(100 * dop, now, 0.02);
      this.gunCrack.frequency.setTargetAtTime(1700 * dop, now, 0.02);
    }
  }
}

export class CombatAudio {
  constructor() {
    this.ctx = null; this.voices = null; this.enabled = false;
  }

  async enable() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      this.ctx = new AC();
      const ctx = this.ctx;
      this.master = ctx.createGain(); this.master.gain.value = 0.85;
      // 잔향(합성 IR) 을 옅게 — 개활지 공간감. 파일이 아니다.
      this.wet = ctx.createGain(); this.wet.gain.value = 0.14;
      this.conv = ctx.createConvolver(); this.conv.buffer = reverbIR(ctx);
      this.comp = ctx.createDynamicsCompressor();
      this.comp.threshold.value = -16; this.comp.ratio.value = 6;
      this.master.connect(this.comp).connect(ctx.destination);
      this.master.connect(this.conv).connect(this.wet).connect(this.comp);
      const [jetBuf, gunBuf] = await Promise.all([
        loadSample(ctx, "jet"), loadSample(ctx, "gun"),
      ]);
      if (jetBuf) {
        this.source = "녹음";
        this.voices = {
          blue: new SampleVoice(ctx, jetBuf, gunBuf, this.master),
          red: new SampleVoice(ctx, jetBuf, gunBuf, this.master),
        };
      } else {
        this.source = "합성";        // 음원이 없으면 합성으로 — 소리는 난다
        const noise = noiseBuffer(ctx);
        this.voices = {
          blue: new AircraftVoice(ctx, noise, this.master),
          red: new AircraftVoice(ctx, noise, this.master),
        };
      }
    }
    this.ctx.resume();
    this.enabled = true;
    return true;
  }

  disable() {
    this.enabled = false;
    if (this.ctx) this.ctx.suspend();
  }

  update(states, tracks, cam, rate, playing) {
    if (!this.enabled || !this.ctx || !states.blue) return;
    for (const key of ["blue", "red"]) {
      const s = states[key];
      const track = tracks?.[key];
      const v = this.voices[key];
      if (!s || !track) continue;
      const dx = s.x - cam.x, dy = s.y - cam.y, dz = s.z - cam.z;
      const dist = Math.hypot(dx, dy, dz);
      // 속도는 상태에 없다 — 트랙 위치를 차분해 얻는다.
      const i = s.index;
      const j = Math.min(i + 1, track.times.length - 1);
      const dt = Math.max(track.times[j] - track.times[i], 1e-3);
      const P = track.position;
      const vx = (P[j * 3] - P[i * 3]) / dt;
      const vy = (P[j * 3 + 1] - P[i * 3 + 1]) / dt;
      const vz = (P[j * 3 + 2] - P[i * 3 + 2]) / dt;
      const closing = dist > 1 ? -(vx * dx + vy * dy + vz * dz) / dist : 0;
      const thr = attrAt(track, "Throttle", i) ?? 0;
      // **정지하면 소리도 멈춘다.** 예전에는 엔진을 40% 로 남겨 뒀는데, 화면이 멈춘
      // 채 소리만 계속 나는 것은 재생기의 기대와 어긋난다(스크럽 중에도 마찬가지).
      v.update(thr, dist, closing, playing && s.inWez,
               (s.health !== null && s.health <= 0) || !playing, rate);
    }
  }
}
