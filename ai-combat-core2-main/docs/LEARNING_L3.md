# L3 제어기 학습 자료 — INDI · Attitude Shim · Limiter

이 문서는 학부생이 `aircombat/control/` 아래 L3(내부 루프) 제어기 코드 세 개를
**처음부터 읽고, 논문(졸업논문/보고서)에 옮길 수 있는 형태**로 정리한 것입니다.

대상 파일 (이 세 개만 다룹니다):

| 파일 | 역할 |
|---|---|
| `aircombat/control/indi.py` | body-rate INDI(Incremental Nonlinear Dynamic Inversion) 제어기 |
| `aircombat/control/attitude.py` | 쿼터니언 기반 자세→각속도 지령 변환 shim |
| `aircombat/control/limiter.py` | 구조/공력 하중배수 한계를 각속도 setpoint에 씌우는 안전 리미터 |

**표기 규칙**
- 코드 인용 블록은 `파일명, L시작-끝` 헤더를 달고, 각 줄 앞에 실제 줄 번호를 붙입니다.
- 수식은 논문에 바로 옮길 수 있도록 LaTeX 표기(`$...$`, `$$...$$`)로도 다시 씁니다.
- **[코드 근거]**: 코드/주석에 그대로 있는 내용.
- **[해설추가 — 코드에 명시되어 있지 않음]**: 코드에는 없지만 표준 이론(신호처리/강체역학)으로 검증 가능한 배경 설명. 논문에 쓸 때는 별도 출처(교과서/논문)를 인용해야 하는 부분입니다.
- 코드에 근거가 없는 것은 추측하지 않고 "코드에 명시되어 있지 않음"이라고 명시합니다.

---

## 0. L3가 전체 파이프라인에서 어디에 있는가

이 세 파일 자체에는 호출 순서가 나오지 않으므로, 참고로 `aircombat/engine/pilot.py`
(대상 파일 아님, 인용만)의 주석을 봅니다.

```python
# pilot.py, L3-7 (참고, 대상 파일 아님)
3    tactic_step   (L1  20Hz) : BT → (pursuit, g_burst)
4    guidance_step (L2 60Hz): BFMGuidance → GuidanceCommand
5    control_step  (L3  120Hz): shim+limiter+INDI → 조종면, 위치 적분
6    step_physics  (L4  120Hz): JSBSim 1스텝
```

즉 실행 순서는 **L2가 목표 자세(q_des)를 만든다 → `attitude.py`의 shim이 이를
body-rate setpoint ω_sp로 바꾼다 → `limiter.py`가 ω_sp를 기체 한계로 클램프한다 →
`indi.py`의 INDI 제어기가 클램프된 ω_sp를 실제 조종면 명령 u로 바꾼다 → JSBSim이
그 u로 한 스텝 적분한다.** 세 파일은 이 체인에서 각각 3번째~5번째 단계를 맡습니다.

---

## 1. `aircombat/control/indi.py`

### 1.1 모듈 설계 목표 — 제어 법칙 (L1-41)

```python
# indi.py, L22-40
22   THE CONTROL LAW (fixed-wing inner loop)
23   ---------------------------------------
24   Rotational dynamics:  J*omega_dot = M(u, qbar, ...) - omega x J*omega
25   INDI replaces all the hard-to-model terms with a *measured* angular
26   acceleration and only needs the input effectiveness G = d(omega_dot)/d(u):
27   
28       nu      = K_rate * (omega_sp - omega)            # desired angular accel
29       G(qbar) = (qbar / qbar_ref) * G0                 # aero effectiveness scales with q-bar
30       du      = G^+ * (nu - alpha_meas)                # required control increment
31       u_k     = u_filt_{k-1} + du                      # increment the (filtered) actuator state
32   
33   The key fixed-wing twist vs. the multirotor INDI literature: control
34   effectiveness scales (approximately) with dynamic pressure qbar = 0.5*rho*V^2,
35   so G is gain-scheduled on qbar. Because alpha is *measured*, G only has to be
36   roughly correct in direction and scale.
37   
38   A second-order low-pass filter is applied to BOTH the angular-acceleration
39   estimate and the actuator command with identical dynamics, so the two signals
40   are time-aligned (this synchronization is the crux of a working INDI loop).
```

**[코드 근거] 수식으로 다시 쓰면:**

강체 회전 운동방정식(오일러 방정식):
$$
J\dot{\boldsymbol\omega} = \mathbf{M}(\mathbf{u}, \bar q, \dots) - \boldsymbol\omega \times (J\boldsymbol\omega)
$$

INDI 제어 법칙:
$$
\boldsymbol\nu = K_{\text{rate}}\,(\boldsymbol\omega_{sp} - \boldsymbol\omega)
$$
$$
G(\bar q) = \frac{\bar q}{\bar q_{ref}}\, G_0
$$
$$
\Delta \mathbf{u} = G^{+}\,(\boldsymbol\nu - \boldsymbol\alpha_{meas})
$$
$$
\mathbf{u}_k = \mathbf{u}_{filt,\,k-1} + \Delta \mathbf{u}
$$

| 기호 | 의미 | 단위 |
|---|---|---|
| $J$ | 기체 관성 텐서 (3×3) | kg·m² (또는 slug·ft²) |
| $\boldsymbol\omega=[p,q,r]^T$ | 동체축 각속도 | rad/s |
| $\dot{\boldsymbol\omega}=[\dot p,\dot q,\dot r]^T$ | 각가속도 | rad/s² |
| $\mathbf{M}$ | 공력+조종면 모멘트 | N·m |
| $\mathbf{u}$ | 조종면 명령 벡터 [aileron, elevator, rudder] | 정규화 무차원 (−1..1) |
| $\bar q$ | 동압 $=\tfrac12\rho V^2$ | JSBSim 관례상 lbf/ft² |
| $\bar q_{ref}$ | $G_0$를 식별한 기준 동압 | $\bar q$와 동일 단위 |
| $\boldsymbol\nu$ | 목표(원하는) 각가속도 | rad/s² |
| $K_{\text{rate}}$ | 각속도 오차 → 목표 각가속도 비례 이득 (대각) | 1/s |
| $G$ | 제어 효과도 행렬 $=\partial\dot{\boldsymbol\omega}/\partial\mathbf{u}$ | rad/s² per (정규화 명령 단위) |
| $G_0$ | $\bar q_{ref}$에서 식별한 $G$ | $G$와 동일 |
| $\boldsymbol\alpha_{meas}$ | 측정(또는 추정)된 각가속도, 필터링됨 | rad/s² |
| $\Delta\mathbf{u}$ | 조종면 명령 증분 | 무차원 |
| $\mathbf{u}_{filt}$ | 필터링된 이전 조종면 상태 | 무차원 |

**[코드 근거] docstring과 실제 구현의 차이(중요, 논문에 정확히 쓰기 위해 반드시 확인할 것):**
위 pseudo-code(L28)는 $\boldsymbol\nu = K_{\text{rate}}(\boldsymbol\omega_{sp}-\boldsymbol\omega)$ 로
원시(raw) 각속도 $\boldsymbol\omega$를 쓰지만, 실제 `update()` 구현(L154, 아래 1.3.3절)은
**필터링된** $\boldsymbol\omega_f$를 사용합니다. 이는 docstring이 아니라 실행되는 코드가
진실이므로, 논문에는 $\boldsymbol\nu = K_{\text{rate}}(\boldsymbol\omega_{sp}-\boldsymbol\omega_f)$가
맞습니다.

---

### 1.2 `class SecondOrderLPF` (L51-77)

INDI의 "동기화(synchronization)" 필터 — 각가속도 추정치와 조종면 상태 양쪽에 **동일한 동역학**으로 적용되는 2차 저역통과 필터.

#### 1.2.1 `__init__` (L52-65)

```python
# indi.py, L52-65
52       def __init__(self, cutoff_hz: float, sample_rate_hz: float,
53                    n_channels: int, damping: float = 0.7071, x0=0.0):
54           wc = 2.0 * np.pi * cutoff_hz
55           T = 1.0 / sample_rate_hz
56           n = 2.0 / T                      # bilinear (Tustin) transform constant
57           d = n * n + 2.0 * damping * wc * n + wc * wc
58           self.b0 = wc * wc / d
59           self.b1 = 2.0 * wc * wc / d
60           self.b2 = wc * wc / d
61           self.a1 = (2.0 * wc * wc - 2.0 * n * n) / d
62           self.a2 = (n * n - 2.0 * damping * wc * n + wc * wc) / d
63           x0 = np.broadcast_to(np.asarray(x0, float), (n_channels,)).astype(float)
64           self.x1 = x0.copy(); self.x2 = x0.copy()
65           self.y1 = x0.copy(); self.y2 = x0.copy()
```

**[코드 근거] 연속시간 원형(코드 주석에 "Butterworth biquad"라고 명시, L48):**
$$
H(s) = \frac{\omega_c^2}{s^2 + 2\zeta\omega_c s + \omega_c^2}
$$

**[해설추가 — 코드에 명시되어 있지 않음, 표준 쌍선형(Tustin) 변환 이론]**
L56의 `n = 2/T`는 Tustin 치환 $s \leftarrow n\dfrac{1-z^{-1}}{1+z^{-1}}$의 상수입니다.
이를 $H(s)$의 분모/분자에 대입하고 $(1+z^{-1})^2$을 곱해 정리하면:

$$
D(z) = \underbrace{(n^2+2\zeta\omega_c n+\omega_c^2)}_{d,\ \text{L57}} + z^{-1}\underbrace{(2\omega_c^2-2n^2)}_{\propto a_1,\ \text{L61}} + z^{-2}\underbrace{(n^2-2\zeta\omega_c n+\omega_c^2)}_{\propto a_2,\ \text{L62}}
$$
$$
N(z) = \omega_c^2(1+z^{-1})^2 = \omega_c^2 + z^{-1}(2\omega_c^2) + z^{-2}\omega_c^2 \ \Rightarrow\ b_0=b_1/2=b_2,\ \text{L58-60}
$$

즉 코드의 5개 계수 $b_0,b_1,b_2,a_1,a_2$는 이 연속시간 2차 저역통과 필터를 Tustin
변환으로 이산화한 표준 biquad 계수와 정확히 일치합니다. 이 유도 과정 자체는 코드
주석에는 없으며, 표준 디지털 신호처리(쌍선형 변환) 결과로 검증한 것입니다.

| 기호 | 코드 변수 | 의미 | 단위 |
|---|---|---|---|
| $f_c$ | `cutoff_hz` | 차단주파수 | Hz |
| $f_s$ | `sample_rate_hz` | 샘플링 주파수 | Hz |
| $\zeta$ | `damping` | 감쇠비 | 무차원 |
| $\omega_c$ | `wc` | 차단각주파수 $=2\pi f_c$ | rad/s |
| $T$ | `T` | 샘플 주기 $=1/f_s$ | s |
| $n$ | `n` | Tustin 상수 $=2/T$ | 1/s |
| $b_0,b_1,b_2$ | `b0,b1,b2` | 분자(전방) biquad 계수 | 무차원 |
| $a_1,a_2$ | `a1,a2` | 분모(피드백) biquad 계수 | 무차원 |
| $x[k-1],x[k-2]$ | `x1,x2` | 이전 입력 상태 | 채널과 동일 |
| $y[k-1],y[k-2]$ | `y1,y2` | 이전 출력 상태 | 채널과 동일 |

**상수/기본값 (L52-65 내부):**

| 이름 | 기본값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `damping` | 0.7071 (≈$1/\sqrt2$, 표준 Butterworth Q) | L53 | L57, L61, L62 |
| `x0` | 0.0 | L53 | L63 (초기 상태 브로드캐스트) |

#### 1.2.2 `reset` (L67-69)

```python
# indi.py, L67-69
67       def reset(self, x0):
68           x0 = np.broadcast_to(np.asarray(x0, float), self.x1.shape).astype(float)
69           self.x1[:] = x0; self.x2[:] = x0; self.y1[:] = x0; self.y2[:] = x0
```

필터의 내부 상태(과거 입력 2개, 과거 출력 2개)를 모두 상수 `x0`로 덮어씁니다. 이는
필터가 이미 `x0`에서 정상상태(steady state)였다고 가정하는 것과 같습니다 — 그래야
`reset` 직후 첫 호출에서 출력이 튀지(bump) 않습니다.

#### 1.2.3 `__call__` (L71-77)

```python
# indi.py, L71-77
71       def __call__(self, x):
72           x = np.asarray(x, float)
73           y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
74                - self.a1 * self.y1 - self.a2 * self.y2)
75           self.x2[:] = self.x1; self.x1[:] = x
76           self.y2[:] = self.y1; self.y1[:] = y
77           return y
```

**[코드 근거] Direct Form I 이산 biquad 재귀식:**
$$
y[k] = b_0 x[k] + b_1 x[k-1] + b_2 x[k-2] - a_1 y[k-1] - a_2 y[k-2]
$$
L75-76은 상태 이동(shift register): $x[k-2]\leftarrow x[k-1]$, $x[k-1]\leftarrow x[k]$, 마찬가지로 $y$에도 적용.

---

### 1.3 `class INDIRateController` (L83-167)

#### 1.3.1 생성자 docstring과 `__init__` (L84-115)

```python
# indi.py, L84-97 (docstring)
84       """
85       Parameters
86       ----------
87       dt        : controller timestep [s]
88       G0        : (3,3) control effectiveness d(pdot,qdot,rdot)/d(u) identified at
89                   qbar_ref. Columns = [aileron, elevator, rudder]; rows = [p,q,r].
90       qbar_ref  : reference dynamic pressure at which G0 was identified [same units
91                   as the qbar you pass to update(), e.g. lbf/ft^2 for JSBSim].
92       k_rate    : (3,) proportional gains on body-rate error -> desired angular
93                   accel [1/s]. Larger = faster, noisier. Typical 4-12.
94       u_min/max : (3,) actuator command saturation (e.g. -1..1 normalised).
95       filt_hz   : cutoff for the synchronization low-pass [Hz].
96       qbar_min  : floor on qbar to keep G invertible at low airspeed.
97       """
```

```python
# indi.py, L98-115
98       def __init__(self, dt, G0, qbar_ref, k_rate=(8.0, 8.0, 6.0),
99                    u_min=(-1, -1, -1), u_max=(1, 1, 1),
100                   filt_hz=20.0, qbar_min=20.0):
101          self.dt = float(dt)
102          self.G0 = np.asarray(G0, float).reshape(3, 3)
103          self.qbar_ref = float(qbar_ref)
104          self.k_rate = np.asarray(k_rate, float)
105          self.u_min = np.asarray(u_min, float)
106          self.u_max = np.asarray(u_max, float)
107          self.qbar_min = float(qbar_min)
108          fs = 1.0 / self.dt
109          # Two filters with IDENTICAL dynamics so accel and actuator stay aligned.
110          self.f_acc = SecondOrderLPF(filt_hz, fs, 3)
111          self.f_act = SecondOrderLPF(filt_hz, fs, 3)
112          self.f_rate = SecondOrderLPF(filt_hz, fs, 3)   # rate used in the error term
113          self.u_prev = np.zeros(3)
114          self.omega_prev = np.zeros(3)
115          self._primed = False
```

L108-112가 이 파일에서 가장 중요한 설계 결정입니다: `fs = 1/dt` 하나로부터
`f_acc`, `f_act`, `f_rate` **세 개의 `SecondOrderLPF` 인스턴스를 정확히 같은
`filt_hz`, 같은 `fs`, 같은 채널 수(3)로 생성**합니다. 이 이유는 §5.1에서 따로
깊게 다룹니다.

#### 1.3.2 `reset` (L117-121)

```python
# indi.py, L117-121
117      def reset(self, u0=(0, 0, 0), omega0=(0, 0, 0)):
118          u0 = np.asarray(u0, float); omega0 = np.asarray(omega0, float)
119          self.u_prev = u0.copy(); self.omega_prev = omega0.copy()
120          self.f_acc.reset(0.0); self.f_act.reset(u0); self.f_rate.reset(omega0)
121          self._primed = True
```

`f_acc`는 0(각가속도가 0이었다고 가정)으로, `f_act`는 `u0`(현재 조종면 위치)로,
`f_rate`는 `omega0`(현재 측정 각속도)로 각각 다른 정상상태 값으로 리셋됩니다 —
각 필터가 대표하는 물리량이 다르기 때문에 리셋 값도 다릅니다(차단주파수는 같지만
초기 조건은 신호별로 다름).

#### 1.3.3 `update` (L123-167) — 핵심 루프

```python
# indi.py, L123-134 (docstring)
123      def update(self, omega, omega_sp, qbar, ang_accel=None, omega_sp_dot=None):
124          """
125          omega        : (3,) measured body rates [p,q,r] (rad/s)
126          omega_sp     : (3,) commanded body rates (rad/s)
127          qbar         : scalar dynamic pressure (same units as qbar_ref)
128          ang_accel    : (3,) measured angular acceleration [pdot,qdot,rdot]
129                         (rad/s^2). In JSBSim read accelerations/pdot|qdot|rdot.
130                         If None, it is estimated from a filtered finite difference
131                         of omega (what you'd do on real hardware with only a gyro).
132          omega_sp_dot : (3,) optional rate-setpoint feedforward (rad/s^2).
133          returns u    : (3,) actuator command [aileron, elevator, rudder].
134          """
```

```python
# indi.py, L135-138
135          omega = np.asarray(omega, float)
136          omega_sp = np.asarray(omega_sp, float)
137          if not self._primed:
138              self.reset(self.u_prev, omega)
```

첫 호출에서 `_primed`가 `False`이면 `reset(self.u_prev, omega)`를 호출합니다.
이때 `self.omega_prev`가 **현재 프레임의 `omega`와 같은 값**으로 세팅되므로,
바로 아래(L142)에서 계산하는 유한차분 각가속도는 첫 호출에서 정확히 0이 됩니다.

```python
# indi.py, L140-145
140          # --- measured angular acceleration, filtered ---
141          if ang_accel is None:
142              alpha_raw = (omega - self.omega_prev) / self.dt
143          else:
144              alpha_raw = np.asarray(ang_accel, float)
145          alpha_f = self.f_acc(alpha_raw)
```

**[코드 근거] 두 가지 각가속도 획득 경로:**
1. 시뮬레이터(JSBSim)가 직접 각가속도를 주면(`ang_accel`) 그대로 사용.
2. 없으면 유한차분으로 추정(실제 하드웨어에서 자이로만 있을 때 하는 방식, L131):
$$
\boldsymbol\alpha_{raw}[k] = \frac{\boldsymbol\omega[k]-\boldsymbol\omega[k-1]}{\Delta t}
$$
이후 두 경우 모두 `f_acc`로 필터링해 $\boldsymbol\alpha_f$를 얻습니다.

```python
# indi.py, L147-151
147          # --- filtered actuator state (delay-matched to alpha_f) ---
148          u_f = self.f_act(self.u_prev)
149      
150          # --- filtered rate for the feedback term ---
151          omega_f = self.f_rate(omega)
```

주석(L147)이 명시하듯 `u_f`는 "$\alpha_f$와 지연을 맞추기 위한" 필터링된 이전
조종면 상태입니다. `omega_f`는 비례 오차항에 쓸 필터링된 각속도입니다.

```python
# indi.py, L153-156
153          # --- desired angular acceleration (linear outer law on rate error) ---
154          nu = self.k_rate * (omega_sp - omega_f)
155          if omega_sp_dot is not None:
156              nu = nu + np.asarray(omega_sp_dot, float)
```

**[코드 근거] 실제 구현된 목표 각가속도(모듈 docstring L28과 달리 필터링된 $\omega_f$ 사용):**
$$
\boldsymbol\nu = K_{\text{rate}} \odot (\boldsymbol\omega_{sp} - \boldsymbol\omega_f) \; [+\, \dot{\boldsymbol\omega}_{sp}]
$$
($\odot$: 원소별 곱. `k_rate`가 (3,) 벡터이므로 대각행렬 $K_{\text{rate}}=\mathrm{diag}(k_p,k_q,k_r)$과 곱하는 것과 같습니다.)
`omega_sp_dot`은 선택적 피드포워드 항입니다.

```python
# indi.py, L158-163
158          # --- qbar-scheduled effectiveness and increment ---
159          G = (max(qbar, self.qbar_min) / self.qbar_ref) * self.G0
160          du = np.linalg.solve(G, nu - alpha_f) if abs(np.linalg.det(G)) > 1e-9 \
161              else np.linalg.pinv(G) @ (nu - alpha_f)
162      
163          u = np.clip(u_f + du, self.u_min, self.u_max)
```

**[코드 근거] 동압 스케줄된 효과도 행렬과 증분식:**
$$
G(\bar q) = \frac{\max(\bar q,\ \bar q_{min})}{\bar q_{ref}}\, G_0
$$
$$
\Delta\mathbf{u} =
\begin{cases}
G^{-1}(\boldsymbol\nu - \boldsymbol\alpha_f) & |\det G| > 10^{-9}\ \text{(L160)}\\[4pt]
G^{+}(\boldsymbol\nu - \boldsymbol\alpha_f) & \text{그 외 (Moore–Penrose 유사역행렬)}
\end{cases}
$$
$$
\mathbf{u} = \mathrm{clip}(\mathbf{u}_f + \Delta\mathbf{u},\ \mathbf{u}_{min},\ \mathbf{u}_{max})
$$
즉 도입부 수식(L30)의 $G^{+}$는, $G$가 정칙(가역)이면 정확한 역행렬로, 특이(singular)에
가까우면 유사역행렬로 대체되는 두 경로로 구현되어 있습니다. 임계값 $10^{-9}$은
코드에 하드코딩된 매직넘버입니다.

```python
# indi.py, L165-167
165          self.u_prev = u
166          self.omega_prev = omega
167          return u
```

다음 스텝을 위해 `u_prev`(방금 낸 명령)와 `omega_prev`(방금 측정한 각속도)를 저장합니다.

---

### 1.4 `identify_G0` (L179-204)

```python
# indi.py, L179-204
179      def identify_G0(fdm, delta=0.02, settle=3):
180          """Perturb aileron/elevator/rudder by +-delta and measure d(angaccel)/du.
181          Returns (G0 (3,3), qbar_ref). Call right after trimming. Non-destructive:
182          restores the original commands afterwards."""
183          CMD = ['fcs/aileron-cmd-norm', 'fcs/elevator-cmd-norm', 'fcs/rudder-cmd-norm']
184          ACC = ['accelerations/pdot-rad_sec2', 'accelerations/qdot-rad_sec2',
185                 'accelerations/rdot-rad_sec2']
186          u0 = np.array([fdm[c] for c in CMD])
187          qbar_ref = fdm['aero/qbar-psf']
188      
189          def measure(u):
190              for c, v in zip(CMD, u):
191                  fdm[c] = float(v)
192              for _ in range(settle):
193                  fdm.run()
194              return np.array([fdm[a] for a in ACC])
195      
196          G0 = np.zeros((3, 3))
197          for j in range(3):
198              up = u0.copy(); up[j] += delta
199              um = u0.copy(); um[j] -= delta
200              a_plus = measure(up)
201              a_minus = measure(um)
202              G0[:, j] = (a_plus - a_minus) / (2.0 * delta)   # central difference
203          measure(u0)  # restore
204          return G0, qbar_ref
```

**[코드 근거]** 이 함수는 §1.1에서 정의한 $G_0 = \partial\dot{\boldsymbol\omega}/\partial\mathbf{u}$를
**중심차분(central difference)**으로 실측합니다:
$$
(G_0)_{:,j} = \frac{\boldsymbol\alpha(\mathbf{u}_0+\delta\,\hat e_j) - \boldsymbol\alpha(\mathbf{u}_0-\delta\,\hat e_j)}{2\delta}
$$
각 조종면 $j$(aileron/elevator/rudder)를 트림 명령 $\mathbf{u}_0$에서 $\pm\delta$만큼
흔들고, `settle` 스텝만큼 JSBSim을 돌려 과도응답을 지나게 한 뒤 각가속도를 읽습니다.
`qbar_ref`는 트림 상태에서의 실제 동압(`aero/qbar-psf`)입니다. 마지막에 `measure(u0)`로
원래 명령을 복원해 부작용이 없게 합니다(비파괴적).

**상수/기본값:**

| 이름 | 기본값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `delta` | 0.02 (정규화 명령 단위) | L179 | L198, L199, L202 |
| `settle` | 3 (스텝) | L179 | L192 |

---

### 1.5 `indi.py` 상수/기본값 총정리

| 상수/기본값 | 값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `SecondOrderLPF.damping` | 0.7071 | L53 | L57, L61, L62 |
| `SecondOrderLPF.x0` | 0.0 | L53 | L63 |
| `INDIRateController.k_rate` | (8.0, 8.0, 6.0) [1/s] | L98 | L104 → L154 |
| `INDIRateController.u_min` | (−1, −1, −1) | L99 | L105 → L163 |
| `INDIRateController.u_max` | (1, 1, 1) | L99 | L106 → L163 |
| `INDIRateController.filt_hz` | 20.0 [Hz] | L100 | L110, L111, L112 |
| `INDIRateController.qbar_min` | 20.0 (qbar 단위) | L100 | L107 → L159 |
| 행렬식 임계값 | 1e-9 | L160 | L160 |
| `reset.u0` | (0,0,0) | L117 | L118-121 |
| `reset.omega0` | (0,0,0) | L117 | L118-121 |
| `identify_G0.delta` | 0.02 | L179 | L198, L199, L202 |
| `identify_G0.settle` | 3 | L179 | L192 |

---

## 2. `aircombat/control/attitude.py`

### 2.1 모듈 설계 목표 (L1-15)

```python
# attitude.py, L1-15 (모듈 docstring)
1    """쿼터니언 자세→각속도 shim (D3) — Euler `AttitudeToRate` 대체.
2    
3    근거(tmp/f16_bfm_control_architecture.md D3): Euler φ/θ 는 θ≈±90°(루프·수직기동
4    = BFM 이 실제로 벌어지는 곳)에서 특이(gimbal lock). 쿼터니언 오차 → 각속도 명령으로
5    특이점을 제거한다.
6    
7    제어 법칙(표준 쿼터니언 피드백):
8        q_err     = conj(q_cur) ⊗ q_des       # body 프레임 상대회전
9        [p_sp,q_sp] = 2·K·vec(q_err)[roll,pitch]  # (shortest-path: q_err.w<0 이면 부호 반전)
10       r_sp      = -k_yaw_damp · r            # yaw 는 자세 추종이 아님(고정익)
11   q 는 항법(NED)→기체(body) 회전을 나타내는 [w,x,y,z] 규약(항공 3-2-1: yaw-pitch-roll).
12   yaw(r)를 쿼터니언으로 추종하지 않는 이유: BFM 에서 heading 은 L2 의 리프트벡터·뱅크
13   배치로 간접 제어되는 결과다. yaw 축은 협조선회/sideslip(여기선 r→0 감쇠)에 맡긴다.
14   출력 ω_sp 는 body rate [p,q,r] 로 L3 INDI(INDIRateController)로 직접 들어간다.
15   """
```

**[코드 근거] 왜 쿼터니언인가:** 오일러각 $[\phi,\theta,\psi]$(roll,pitch,yaw)는
피치 $\theta \approx \pm90°$에서 짐벌락(gimbal lock)이 발생합니다. 코드 주석(L3-4)은
이 특이점이 바로 **BFM(공중전 기동)이 실제로 일어나는 영역**(루프, 수직 기동)이라고
명시합니다. 쿼터니언 오차 기반 제어는 이 특이점이 없습니다.

**[코드 근거] 왜 yaw를 자세로 추종하지 않는가:** L12-13에 따르면 고정익 BFM에서
heading(방위)은 L2가 정하는 "리프트벡터·뱅크 배치"의 **간접 결과**이지 직접 추종
대상이 아닙니다. 따라서 yaw축은 자세 오차가 아니라 단순 요율 감쇠($r\to 0$)로 처리합니다.

**[코드 근거] 제어 법칙을 수식으로:**
$$
q_{err} = q_{cur}^{*} \otimes q_{des}
$$
$$
\begin{bmatrix}p_{sp}\\ q_{sp}\end{bmatrix} = 2K_{att}\cdot \mathrm{vec}(q_{err})_{x,y}
\qquad(\text{만약 } (q_{err})_w<0 \text{이면 } q_{err}\leftarrow -q_{err})
$$
$$
r_{sp} = -k_{yawdamp}\cdot r
$$

| 기호 | 의미 | 단위 |
|---|---|---|
| $q_{cur}$ | 현재 자세 쿼터니언 [w,x,y,z], NED→body | 무차원(단위 쿼터니언) |
| $q_{des}$ | 목표 자세 쿼터니언 | 무차원 |
| $q_{cur}^{*}$ | $q_{cur}$의 켤레(conjugate) | 무차원 |
| $\otimes$ | 쿼터니언 곱(Hamilton product) | — |
| $q_{err}$ | 상대회전(오차) 쿼터니언, body 프레임 | 무차원 |
| $\mathrm{vec}(q)_{x,y}$ | 쿼터니언 벡터부의 x,y 성분 | 무차원 |
| $K_{att}$ | 자세 오차 → roll/pitch rate 비례 이득 | 1/s (§2.4 근거 참조) |
| $k_{yawdamp}$ | yaw rate 감쇠 이득 | 무차원(1/s로도 해석 가능, r[rad/s]→r_sp[rad/s]이므로 무차원 계수) |
| $r$ | 현재 측정 yaw rate | rad/s |
| $p_{sp},q_{sp},r_{sp}$ | roll/pitch/yaw rate 지령 | rad/s |

**[해설추가 — 코드에 명시되어 있지 않음, 표준 쿼터니언 오차 피드백 이론]**
단위 쿼터니언 $q=[\cos(\theta/2),\ \hat n\sin(\theta/2)]$에서 회전각 $\theta$가 작으면
벡터부는 $\mathrm{vec}(q)\approx (\theta/2)\hat n$로 근사됩니다. 따라서
$$
\boldsymbol\omega_{sp} \approx 2K_{att}\cdot\frac{\theta}{2}\hat n = K_{att}\,\theta\,\hat n
$$
즉 $K_{att}$는 "회전벡터 오차(rad) → 각속도 지령(rad/s)"의 비례 이득이므로 단위는
1/s이며, `k_rate`(indi.py)와 같은 성격(오차에 곱해 각속도류 지령을 만드는 비례
이득)을 갖습니다. 이 소각근사 유도는 코드/주석에는 없고 표준 자세제어 이론(예:
쿼터니언 피드백 제어, Wie & Barba류 결과)에 근거합니다.

### 2.2 쿼터니언 유틸 함수

#### 2.2.1 `euler_to_quat` (L24-34)

```python
# attitude.py, L24-34
24   def euler_to_quat(phi: float, theta: float, psi: float) -> np.ndarray:
25       cr, sr = np.cos(phi / 2), np.sin(phi / 2)
26       cp, sp = np.cos(theta / 2), np.sin(theta / 2)
27       cy, sy = np.cos(psi / 2), np.sin(psi / 2)
28       q = np.array([
29           cr * cp * cy + sr * sp * sy,
30           sr * cp * cy - cr * sp * sy,
31           cr * sp * cy + sr * cp * sy,
32           cr * cp * sy - sr * sp * cy,
33       ])
34       return q / np.linalg.norm(q)
```

**[코드 근거] 3-2-1(yaw-pitch-roll) 항공 시퀀스 오일러각→쿼터니언 표준식:**
$$
\begin{aligned}
w &= \cos\tfrac{\phi}{2}\cos\tfrac{\theta}{2}\cos\tfrac{\psi}{2} + \sin\tfrac{\phi}{2}\sin\tfrac{\theta}{2}\sin\tfrac{\psi}{2}\\
x &= \sin\tfrac{\phi}{2}\cos\tfrac{\theta}{2}\cos\tfrac{\psi}{2} - \cos\tfrac{\phi}{2}\sin\tfrac{\theta}{2}\sin\tfrac{\psi}{2}\\
y &= \cos\tfrac{\phi}{2}\sin\tfrac{\theta}{2}\cos\tfrac{\psi}{2} + \sin\tfrac{\phi}{2}\cos\tfrac{\theta}{2}\sin\tfrac{\psi}{2}\\
z &= \cos\tfrac{\phi}{2}\cos\tfrac{\theta}{2}\sin\tfrac{\psi}{2} - \sin\tfrac{\phi}{2}\sin\tfrac{\theta}{2}\cos\tfrac{\psi}{2}
\end{aligned}
$$
L34에서 수치오차 누적으로 인한 비단위화를 막기 위해 $q \leftarrow q/\lVert q\rVert$로 정규화합니다.

| 기호 | 의미 | 단위 |
|---|---|---|
| $\phi,\theta,\psi$ | roll, pitch, yaw (오일러각) | rad |

#### 2.2.2 `quat_conj` (L37-39)

```python
# attitude.py, L37-39
37   def quat_conj(q: np.ndarray) -> np.ndarray:
38       q = np.asarray(q, float)
39       return np.array([q[0], -q[1], -q[2], -q[3]])
```
$$
q^{*} = [w,\,-x,\,-y,\,-z]
$$
단위 쿼터니언의 켤레는 역회전(inverse rotation)과 같습니다.

#### 2.2.3 `quat_mul` (L42-50)

```python
# attitude.py, L42-50
42   def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
43       w1, x1, y1, z1 = a
44       w2, x2, y2, z2 = b
45       return np.array([
46           w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
47           w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
48           w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
49           w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
50       ])
```

**[코드 근거] Hamilton 곱(쿼터니언 곱셈), [w,x,y,z] 규약:**
$$
\begin{aligned}
(a\otimes b)_w &= w_1w_2 - x_1x_2 - y_1y_2 - z_1z_2\\
(a\otimes b)_x &= w_1x_2 + x_1w_2 + y_1z_2 - z_1y_2\\
(a\otimes b)_y &= w_1y_2 - x_1z_2 + y_1w_2 + z_1x_2\\
(a\otimes b)_z &= w_1z_2 + x_1y_2 - y_1x_2 + z_1w_2
\end{aligned}
$$

#### 2.2.4 `quat_to_euler` (L53-59)

```python
# attitude.py, L53-59
53   def quat_to_euler(q: np.ndarray) -> tuple[float, float, float]:
54       w, x, y, z = np.asarray(q, float)
55       phi = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
56       t = np.clip(2 * (w * y - z * x), -1.0, 1.0)
57       theta = np.arcsin(t)
58       psi = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
59       return float(phi), float(theta), float(psi)
```

$$
\phi = \operatorname{atan2}\big(2(wx+yz),\ 1-2(x^2+y^2)\big)
$$
$$
\theta = \arcsin\big(\mathrm{clip}(2(wy-zx),\,-1,\,1)\big)
$$
$$
\psi = \operatorname{atan2}\big(2(wz+xy),\ 1-2(y^2+z^2)\big)
$$
L56의 `clip(...,-1,1)`은 부동소수점 반올림으로 $2(wy-zx)$가 $[-1,1]$을 아주 살짝
벗어나 `arcsin`이 정의역 오류(NaN)를 내는 것을 막기 위한 수치적 안전장치입니다
(상수 $-1.0, 1.0$은 이 파일에서 정의된 매직넘버, L56).

### 2.3 `class QuaternionAttitudeShim` (L65-89)

#### 2.3.1 `__init__` (L68-72)

```python
# attitude.py, L65-72
65   class QuaternionAttitudeShim:
66       """목표 쿼터니언 → ω_sp. L2 가 준 리프트벡터/뱅크 자세를 L3 rate 지령으로 변환."""
67   
68       def __init__(self, k_att: float = 4.5, k_yaw_damp: float = 1.5,
69                    rate_limit_dps=(120.0, 60.0, 30.0)):
70           self.k_att = float(k_att)
71           self.k_yaw_damp = float(k_yaw_damp)
72           self.rate_limit = np.deg2rad(np.asarray(rate_limit_dps, float))
```

`rate_limit_dps`는 deg/s 단위로 받아 L72에서 rad/s로 변환되어 저장됩니다.

#### 2.3.2 `rate_setpoint` (L74-82)

```python
# attitude.py, L74-82
74       def rate_setpoint(self, q_cur: np.ndarray, q_des: np.ndarray,
75                         r_cur: float = 0.0) -> np.ndarray:
76           """q_cur, q_des ([w,x,y,z]) → ω_sp=[p,q,r] (rad/s)."""
77           q_err = quat_mul(quat_conj(q_cur), q_des)
78           if q_err[0] < 0.0:            # shortest path (q 와 -q 는 같은 자세)
79               q_err = -q_err
80           omega_sp = 2.0 * self.k_att * q_err[1:4]
81           omega_sp[2] = -self.k_yaw_damp * float(r_cur)   # yaw: 추종 아닌 감쇠(q_err_z 무시)
82           return np.clip(omega_sp, -self.rate_limit, self.rate_limit)
```

**[코드 근거] 실제 구현:**
$$
q_{err} = q_{cur}^{*}\otimes q_{des},\qquad
q_{err}\leftarrow -q_{err} \text{ if } (q_{err})_w<0
$$
$$
\boldsymbol\omega_{sp} = 2k_{att}\,\mathrm{vec}(q_{err}) = 2k_{att}\,[(q_{err})_x,(q_{err})_y,(q_{err})_z]
$$
$$
(\boldsymbol\omega_{sp})_z \leftarrow -k_{yawdamp}\, r_{cur} \quad(\text{L81, } (q_{err})_z\text{는 버려짐})
$$
$$
\boldsymbol\omega_{sp} \leftarrow \mathrm{clip}(\boldsymbol\omega_{sp},\ -\boldsymbol\omega_{limit},\ \boldsymbol\omega_{limit})
$$

L80에서는 $x,y,z$ 세 성분 모두 $2k_{att}$를 곱하지만, 바로 다음 줄(L81)에서 $z$성분은
버려지고 요율 감쇠값으로 덮어써집니다. 즉 **쿼터니언 오차의 z성분(대략 yaw 오차에
해당)은 실제로 아무 역할도 하지 않습니다** — 이는 모듈 docstring(L12-13)이 명시한
설계 의도와 일치합니다.

#### 2.3.3 `rate_setpoint_euler` (L84-88)

```python
# attitude.py, L84-88
84       def rate_setpoint_euler(self, phi, theta, psi,
85                               phi_des, theta_des, psi_des, r_cur: float = 0.0) -> np.ndarray:
86           """현재/목표를 Euler 로 받는 편의 래퍼 (내부는 쿼터니언)."""
87           return self.rate_setpoint(euler_to_quat(phi, theta, psi),
88                                     euler_to_quat(phi_des, theta_des, psi_des), r_cur)
```

오일러각 입력을 받아 내부적으로 쿼터니언으로 변환한 뒤 `rate_setpoint`를 호출하는
편의 래퍼입니다. 알고리즘 자체는 항상 쿼터니언으로 동작합니다.

### 2.4 `attitude.py` 상수/기본값 총정리

| 상수/기본값 | 값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `QuaternionAttitudeShim.k_att` | 4.5 [1/s, §2.1 소각근사 참조] | L68 | L70 → L80 |
| `QuaternionAttitudeShim.k_yaw_damp` | 1.5 | L68 | L71 → L81 |
| `QuaternionAttitudeShim.rate_limit_dps` | (120.0, 60.0, 30.0) [deg/s] | L69 | L72 → L82 |
| `rate_setpoint.r_cur` | 0.0 | L74-75 | L81 |
| `quat_to_euler` clip 경계 | −1.0, 1.0 | L56 | L56 |

---

## 3. `aircombat/control/limiter.py`

### 3.1 모듈 설계 목표 — 한계 모델 (L1-27)

```python
# limiter.py, L1-27 (모듈 docstring)
1    """L3 결합 리미터 — 코너 플래토 + (AoA_max→G) ∩ 구조 9G.
2    
3    INDI 앞단 안전 실행기 (tmp/f16_bfm_control_architecture.md 로드맵 §2, §4.3).
4    L2 가이드가 요청한 각속도 setpoint(특히 pitch q)를 기체 한계로 클램프한다.
5    당김은 조절(regulation)이며 상한은 코너 플래토라는 D6 불변식을 여기서 강제한다.
6    
7    검사가능(auditable): limit_omega_sp 는 어떤 한계가 걸렸는지 플래그로 반환한다
8    (제1세부 "신뢰성 평가 기준"의 실행 로그).
9    
10   한계 모델
11   ---------
12   · 구조: **비대칭** — 양의 당김은 g_struct_max(F-16 +9G), 음의 밀기는 g_struct_min
13     (−3G). 실기 한계는 대칭이 아니며, 음의 한계는 조종사 내성이 아니라 **기골 설계
14     하중**이다(극한하중 −4.5G). 실기 FLCS 도 −3G 에서 명령을 자른다.
15   · 공력(AoA_max→G): 최대 양력계수에서 낼 수 있는 G 는 동압 ∝ V² 에 비례.
16       G_aero(V) = g_struct_max · (KCAS / KCAS_corner_lo)²   (코너 하한에서 구조한계 도달)
17     → 저속에선 AoA 한계가, 코너 플래토·고속에선 구조 한계가 지배.
18   · pitch-rate 환산 (중력 포함): 당김면 운동방정식은
19       m·V·q = L − W·(중력의 양력방향 성분) 이고, 양력 방향(동체 −z)에 대한 중력 성분은
20       cosφ·cosθ 다. 따라서  **q = (n − cosφ·cosθ)·g / V**.
21       수평 정립(cosφcosθ=1): q=(n−1)g/V — 1G 는 중력이 이미 상쇄한다.
22       배면 수평(=−1):        q=(n+1)g/V.
23       나이프에지(=0):        q=n·g/V.
24     이전 판은 중력항 없이 q=n·g/V 를 썼는데, 이는 나이프에지에서만 맞고 수평 비행에서는
25     **양수쪽을 1G 관대하게(+9 의도→+10 허용), 음수쪽을 1G 엄격하게(−3 의도→−2 제한)**
26     만들었다.
27   """
```

**[코드 근거] 구조 한계:** 양(당김)/음(밀기)이 비대칭입니다. 음의 한계 $g_{struct,min}$은
"조종사 내성"이 아니라 **기골(airframe) 설계 하중**이며, 극한하중은 −4.5G, 실제
F-16 FLCS(비행제어시스템)도 −3G에서 명령을 자릅니다(L12-14, L48 주석과 동일).

**[코드 근거] 공력 한계 → 코너 스피드 개념:**
$$
G_{aero}(V_{KCAS}) = g_{struct,max}\cdot\left(\frac{V_{KCAS}}{V_{corner,lo}}\right)^{2}
$$
동압 $\bar q \propto V^2$이므로 최대 양력계수에서 낼 수 있는 G는 속도의 제곱에
비례합니다(L15-16). 이 식은 "코너 하한 속도에서 정확히 구조한계에 도달하도록"
보정되어 있습니다 — 이것이 코너 스피드의 정의 그 자체입니다. 저속에서는 이 공력식이,
코너 플래토 이상 고속에서는 구조한계(상수 9G)가 지배합니다.

**[코드 근거] 중력을 포함한 피치레이트 환산 — 수식 유도(뉴턴 제2법칙, 이미 주석에 있는 것을 정리):**
양력 방향(동체 $-z$)에 대한 뉴턴의 제2법칙(원운동):
$$
mV\dot q_{path} = L - W\cos\phi\cos\theta
$$
하중배수 $n = L/W$, $m=W/g$를 대입:
$$
q = \frac{(n-\cos\phi\cos\theta)\,g}{V}
$$

| 기호 | 의미 | 단위 |
|---|---|---|
| $m$ | 기체 질량 | slug |
| $V$ | 대기속도(진대기속도) | ft/s |
| $q$ | body pitch rate | rad/s |
| $L$ | 양력 | lbf |
| $W$ | 중량 | lbf |
| $n$ | 하중배수(load factor) $=L/W$ | g (무차원, g 단위) |
| $\phi,\theta$ | roll, pitch 오일러각 | rad |
| $\cos\phi\cos\theta$ | 중력의 양력방향 성분 = `g_lift` | 무차원 |
| $g$ | 중력가속도 | ft/s² |

특수해(코드 주석 L21-23):
- 수평 정립 비행($\cos\phi\cos\theta=1$): $q=(n-1)g/V$ — 1G는 이미 중력이 상쇄.
- 배면 수평 비행($=-1$): $q=(n+1)g/V$.
- 나이프에지($=0$): $q=ng/V$.

**[코드 근거] 이전 버전과의 차이(설계 이력, 논문의 "선행 연구 대비 개선점"에 쓸 수 있음):**
이전 판은 중력항 없이 $q=ng/V$만 사용했는데, 이는 나이프에지에서만 정확하고
수평비행에서는 양의 한계를 1G 관대하게(의도 +9G → 실제 +10G 허용), 음의 한계를
1G 엄격하게(의도 −3G → 실제 −2G로 제한) 만드는 오차가 있었습니다(L24-26).

### 3.2 모듈 레벨 상수 (L33-39)

```python
# limiter.py, L33-39
33   G_FT_S2 = 32.174  # 중력가속도 [ft/s^2]
34   
35   # 지속 G(Ps=0) 실측표 — scripts/measure_g_envelope.py sustained. 15kft 는 350–400KCAS
36   # 에서 4.8G 피크(실기 F-16 지속 ~5G 와 부합), 25kft 는 추력 감소로 3.9G 피크.
37   SUSTAINED_KCAS = (250.0, 300.0, 350.0, 400.0, 450.0)
38   SUSTAINED_G_15K = (3.59, 4.64, 4.79, 4.81, 3.68)
39   SUSTAINED_G_25K = (3.27, 3.88, 3.86, 3.27, 1.97)
```

**[코드 근거]** `G_FT_S2 = 32.174` ft/s²는 표준 중력가속도(사용: L95, L101에서
`G_FT_S2`로 참조). `SUSTAINED_*` 세 튜플은 시뮬레이션 실측표(주석에 `scripts/
measure_g_envelope.py sustained` 명시, L35)로, "정상상태 추력=항력(Ps=0)에서
**계속 유지 가능한** G"를 속도별로 기록한 것이며, 순간 최대 G 포락선과는 다른
개념입니다(§3.4.3에서 사용).

| 상수 | 값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `G_FT_S2` | 32.174 [ft/s²] | L33 | L95, L101 |
| `SUSTAINED_KCAS` | (250, 300, 350, 400, 450) [KCAS] | L37 | L80, L81 |
| `SUSTAINED_G_15K` | (3.59, 4.64, 4.79, 4.81, 3.68) [g] | L38 | L80 |
| `SUSTAINED_G_25K` | (3.27, 3.88, 3.86, 3.27, 1.97) [g] | L39 | L81 |

### 3.3 `class LimiterConfig` (L42-52)

```python
# limiter.py, L42-52
42   @dataclass
43   class LimiterConfig:
44       g_struct_max: float = 9.0       # 양의 구조 한계 [g] (당김)
45       # 음의 구조 한계 [g] (밀기). F-16 설계 한계 −3.0G / 극한하중 −4.5G.
46       # 이전 판은 이 항이 없어 리미터가 ±9G 대칭으로 동작했고, 유도층은 감사 로그에
47       # −16G 짜리 명령을 남겼다 — 실기에서는 기골이 부러지는 값이다.
48       g_struct_min: float = -3.0
49       kcas_corner_lo: float = 330.0   # 코너 플래토 하한 [KCAS] — 여기서 구조한계 G 도달
50       kcas_corner_hi: float = 440.0   # 코너 플래토 상한 [KCAS] (참고; 상한은 구조로 이미 포화)
51       p_max_dps: float = 220.0        # 롤율 상한 [deg/s]
52       r_max_dps: float = 30.0         # 요율 상한 [deg/s]
```

**[코드 근거]** `g_struct_max`(+9G)와 `g_struct_min`(−3G)은 §3.1에서 설명한 F-16
구조 설계 한계 값입니다. 주석(L46-47)은 이 필드가 없던 이전 버전에서 리미터가
대칭(±9G)으로 동작해 감사 로그에 −16G 명령이 남았다는 실제 회귀(regression)
사례를 기록하고 있습니다.

`kcas_corner_lo`(330 KCAS)는 §3.1의 $G_{aero}$ 식 분모(코너 스피드 하한)로 쓰입니다.
`kcas_corner_hi`(440 KCAS)는 정의는 되어 있지만, **`limiter.py` 파일 내부의 어떤
계산식에서도 참조되지 않습니다** — 주석 자체가 "참고용, 상한은 이미 구조 한계로
포화된다"고 명시합니다(L50). 즉 이 값은 문서화/참고 목적의 상수이며 실제 클램프
연산에는 관여하지 않습니다.

`p_max_dps`, `r_max_dps`는 롤/요 각속도 상한입니다. **주의:** 피치(q)는 §3.1의
물리식으로 매 순간 동적으로 계산되는 반면, 롤·요는 이렇게 **고정 상수**로
주어집니다 — 코드/주석 어디에도 220 deg/s, 30 deg/s이라는 구체적 숫자가 어떤
공력/구조 계산에서 유도되었는지는 설명되어 있지 않습니다. → **코드에 명시되어
있지 않음** (물리적 도출식 없이 직접 지정된 상수).

| 필드 | 기본값 | 정의 줄 | 사용 줄(값이 읽히는 곳) |
|---|---|---|---|
| `g_struct_max` | 9.0 [g] | L44 | L64, L68 |
| `g_struct_min` | −3.0 [g] | L48 | L86 |
| `kcas_corner_lo` | 330.0 [KCAS] | L49 | L64 |
| `kcas_corner_hi` | 440.0 [KCAS] | L50 | (파일 내 미사용) |
| `p_max_dps` | 220.0 [deg/s] | L51 | L114, L120 |
| `r_max_dps` | 30.0 [deg/s] | L52 | L115, L123 |

### 3.4 `class CombinedLimiter` (L55-129)

#### 3.4.1 `__init__` (L58-59)

```python
# limiter.py, L55-59
55   class CombinedLimiter:
56       """코너 플래토 + AoA→G ∩ 9G 를 각속도 setpoint 에 씌우는 안전 실행기."""
57   
58       def __init__(self, config: LimiterConfig | None = None):
59           self.cfg = config or LimiterConfig()
```

`config`가 주어지지 않으면 `LimiterConfig()`의 기본값 세트를 사용합니다.

#### 3.4.2 `_g_aero`, `max_load_factor`, `min_load_factor` (L61-68, L84-86)

```python
# limiter.py, L61-68
61       def _g_aero(self, kcas: float) -> float:
62           """동압이 낼 수 있는 G 크기 (부호 없음)."""
63           c = self.cfg
64           return c.g_struct_max * (max(kcas, 0.0) / c.kcas_corner_lo) ** 2
65   
66       def max_load_factor(self, kcas: float) -> float:
67           """허용 최대 하중배수 = min(구조 9G, 공력 G(동압)). **순간** 봉투다."""
68           return float(min(self.cfg.g_struct_max, self._g_aero(kcas)))
```

```python
# limiter.py, L84-86
84       def min_load_factor(self, kcas: float) -> float:
85           """허용 최소(음의) 하중배수 = max(구조 -3G, -공력 G(동압))."""
86           return float(max(self.cfg.g_struct_min, -self._g_aero(kcas)))
```

**[코드 근거] §3.1의 $G_{aero}$식을 그대로 구현. 순간(instantaneous) 포락선:**
$$
G_{aero}(V) = g_{struct,max}\left(\frac{\max(V,0)}{V_{corner,lo}}\right)^2
$$
$$
n_{max}(V) = \min(g_{struct,max},\ G_{aero}(V))
$$
$$
n_{min}(V) = \max(g_{struct,min},\ -G_{aero}(V))
$$
docstring이 강조하듯(L67) 이는 **순간(instantaneous)** 봉투이며, 아래 §3.4.3의
지속(sustained) 봉투와는 다른 개념입니다.

#### 3.4.3 `sustained_load_factor` (L70-82)

```python
# limiter.py, L70-82
70       def sustained_load_factor(self, kcas: float, alt_ft: float = 15000.0) -> float:
71           """Ps=0 지속 하중배수 — "계속 유지할 수 있는" G (순간 봉투와 다르다).
72   
73           순간 봉투는 맞다(실측 피크 9.1G). 하지만 그걸 **상시** 지령하면 기체는
74           스톱에 물린 채 에너지 언덕을 굴러내린다 — 실전 계측에서 elevator 명령이
75           당김 구간의 97% 를 포화 상태로 보냈고 지령 8.0G / 달성 5.9G 였다.
76           여기 표는 수평 지속 선회에서 dKCAS/dt=0 이 되는 지점의 **달성** G 실측치다
77           (scripts/measure_g_envelope.py sustained, 2026-07-28).
78           고도는 2점 선형보간, 표 밖은 np.interp 가 양끝값으로 고정.
79           """
80           g15 = np.interp(kcas, SUSTAINED_KCAS, SUSTAINED_G_15K)
81           g25 = np.interp(kcas, SUSTAINED_KCAS, SUSTAINED_G_25K)
82           return float(np.interp(alt_ft, (15000.0, 25000.0), (g15, g25)))
```

**[코드 근거]** 이 메서드는 물리식이 아니라 **실측 테이블의 이중 선형보간**입니다:
1. `kcas`를 이용해 15,000ft 테이블과 25,000ft 테이블에서 각각 KCAS→G 선형보간(L80-81).
2. 두 고도값을 다시 `alt_ft`로 선형보간(L82).

주석(L73-75)은 순간 포락선(예: 9.1G 실측 가능)을 상시 지령하면 조종면이 97% 시간
동안 포화되어 명목 지령 8.0G 대비 실제 달성 5.9G에 그쳤다는 **실제 계측 결과**를
근거로 이 메서드가 왜 필요한지 설명합니다. 보간 범위를 벗어나면(L78) `np.interp`의
기본 동작에 따라 양 끝 값으로 고정(클램프)되며 외삽(extrapolation)하지 않습니다.

`alt_ft` 기본값 15000.0(ft)은 L70에서 정의됩니다.

#### 3.4.4 `max_pitch_rate`, `min_pitch_rate` (L88-101)

```python
# limiter.py, L88-101
88       def max_pitch_rate(self, v_fps: float, kcas: float,
89                          g_lift: float = 0.0) -> float:
90           """최대 G 에 대응하는 body pitch-rate 상한 [rad/s]  (q = (n−g_lift)·g/V).
91   
92           g_lift = cosφ·cosθ (중력의 양력방향 성분; +1 수평정립, −1 배면, 0 나이프에지).
93           """
94           v = max(float(v_fps), 1.0)
95           return max(0.0, (self.max_load_factor(kcas) - g_lift) * G_FT_S2 / v)
96   
97       def min_pitch_rate(self, v_fps: float, kcas: float,
98                          g_lift: float = 0.0) -> float:
99           """음의 G 한계에 대응하는 pitch-rate 하한 [rad/s] (음수)."""
100          v = max(float(v_fps), 1.0)
101          return min(0.0, (self.min_load_factor(kcas) - g_lift) * G_FT_S2 / v)
```

**[코드 근거] §3.1에서 유도한 식을 그대로 구현:**
$$
q_{max}(V,\bar V_{KCAS},g_{lift}) = \max\!\big(0,\ (n_{max}(\bar V_{KCAS})-g_{lift})\cdot g/V\big)
$$
$$
q_{min}(V,\bar V_{KCAS},g_{lift}) = \min\!\big(0,\ (n_{min}(\bar V_{KCAS})-g_{lift})\cdot g/V\big)
$$
`v_fps`는 `max(v_fps, 1.0)`로 하한이 걸려(L94, L100) $V\to0$일 때 $0$으로 나누는
것을 방지합니다(1.0 ft/s라는 구체적 값의 물리적 근거는 코드에 명시되어 있지 않음 —
단지 0으로 나누기 방지용 바닥값으로 보입니다). 바깥쪽 `max(0.0, ...)` /
`min(0.0, ...)`은 계산 결과가 부호를 넘어가는 것(예: 매우 낮은 속도에서 상한이
음수가 되는 것)을 막는 안전 클램프입니다 — 이 클램프의 물리적 의미(즉 "당김
방향으로는 최소 0 이상의 여유를 보장한다"는 것)는 주석에 명시적으로 설명되어
있지 않습니다.

`g_lift` 기본값 0.0은 나이프에지 가정(§3.1)에 해당하는 값이지만, **왜 기본값이
나이프에지로 선택되었는지는 코드에 명시되어 있지 않음**.

#### 3.4.5 `limit_omega_sp` (L103-129) — 최종 클램프 + 감사 로그

```python
# limiter.py, L103-129
103      def limit_omega_sp(self, omega_sp, v_fps: float, kcas: float,
104                         g_lift: float = 0.0):
105          """omega_sp=[p,q,r] (rad/s) 를 기체 한계로 클램프.
106  
107          returns (clamped omega_sp, flags). flags 는 어떤 축이 포화됐는지 +
108          현재 허용 최대 G(g_max) 를 담는다 (감사 로그용).
109          """
110          c = self.cfg
111          omega_sp = np.asarray(omega_sp, float)
112          q_max = self.max_pitch_rate(v_fps, kcas, g_lift)
113          q_min = self.min_pitch_rate(v_fps, kcas, g_lift)   # 음수 — 밀기 한계(비대칭)
114          p_max = np.deg2rad(c.p_max_dps)
115          r_max = np.deg2rad(c.r_max_dps)
116          lo = np.array([-p_max, q_min, -r_max])
117          hi = np.array([p_max, q_max, r_max])
118          clamped = np.clip(omega_sp, lo, hi)
119          flags = {
120              "p_limited": bool(abs(omega_sp[0]) > p_max + 1e-9),
121              "q_limited": bool(omega_sp[1] > q_max + 1e-9
122                                or omega_sp[1] < q_min - 1e-9),
123              "r_limited": bool(abs(omega_sp[2]) > r_max + 1e-9),
124              "g_max": self.max_load_factor(kcas),
125              "g_min": self.min_load_factor(kcas),
126              "q_max": float(q_max),
127              "q_min": float(q_min),
128          }
129          return clamped, flags
```

**[코드 근거] 최종 클램프 식:**
$$
\mathbf{lo} = [-p_{max},\ q_{min},\ -r_{max}],\qquad
\mathbf{hi} = [p_{max},\ q_{max},\ r_{max}]
$$
$$
\boldsymbol\omega_{sp}^{clamped} = \mathrm{clip}(\boldsymbol\omega_{sp},\ \mathbf{lo},\ \mathbf{hi})
$$
$p_{max}=\deg2\text{rad}(p_{max,dps})$, $r_{max}=\deg2\text{rad}(r_{max,dps})$는
`LimiterConfig`의 고정 상수를 라디안으로 바꾼 것이고, $q_{max}, q_{min}$은 매
호출마다 §3.4.4의 물리식으로 재계산되는 값입니다. 즉 **롤·요 한계는 상수 사각형,
피치 한계만 매 순간 속도·고도(간접적으로 `kcas`를 통해)에 따라 변하는 비대칭
동적 한계**입니다.

`flags` 딕셔너리는 각 축이 실제로 클램프에 걸렸는지(부동소수점 오차 방지용
허용오차 $10^{-9}$, L120-123에 하드코딩)와 현재 허용 최대/최소 G, 피치레이트
한계값을 담아 반환합니다 — 모듈 docstring(L7-8)이 말한 "검사가능(auditable)"
요구사항을 구현한 부분입니다.

### 3.5 `limiter.py` 상수/기본값 총정리

| 상수/기본값 | 값 | 정의 줄 | 사용 줄 |
|---|---|---|---|
| `G_FT_S2` | 32.174 [ft/s²] | L33 | L95, L101 |
| `SUSTAINED_KCAS` | (250,300,350,400,450) [KCAS] | L37 | L80, L81 |
| `SUSTAINED_G_15K` | (3.59,4.64,4.79,4.81,3.68) [g] | L38 | L80 |
| `SUSTAINED_G_25K` | (3.27,3.88,3.86,3.27,1.97) [g] | L39 | L81 |
| `LimiterConfig.g_struct_max` | 9.0 [g] | L44 | L64, L68 |
| `LimiterConfig.g_struct_min` | −3.0 [g] | L48 | L86 |
| `LimiterConfig.kcas_corner_lo` | 330.0 [KCAS] | L49 | L64 |
| `LimiterConfig.kcas_corner_hi` | 440.0 [KCAS] | L50 | 미사용(참고용) |
| `LimiterConfig.p_max_dps` | 220.0 [deg/s] | L51 | L114, L120 |
| `LimiterConfig.r_max_dps` | 30.0 [deg/s] | L52 | L115, L123 |
| `sustained_load_factor.alt_ft` | 15000.0 [ft] | L70 | L82 |
| 고도 보간 앵커 | (15000.0, 25000.0) [ft] | L82 | L82 |
| `max_pitch_rate.g_lift` / `min_pitch_rate.g_lift` / `limit_omega_sp.g_lift` | 0.0 (나이프에지) | L89, L98, L104 | L95, L101, L112, L113 |
| 속도 하한(0-division 방지) | 1.0 [ft/s] | L94, L100 | L95, L101 |
| 포화 판정 허용오차 | 1e-9 | L120, L121, L122, L123 | 동일 |

---

## 4. 강조 질문 4가지 — 통합 정리

### 4.1 왜 `filt_hz`가 만드는 세 LPF(`f_acc`, `f_act`, `f_rate`)는 반드시 같은 차단주파수여야 하는가

**[코드 근거]** 모듈 docstring(indi.py L38-40)에 명시적으로 나와 있습니다:

> "A second-order low-pass filter is applied to BOTH the angular-acceleration
> estimate and the actuator command with identical dynamics, so the two signals
> are time-aligned (this synchronization is the crux of a working INDI loop)."

즉 코드/주석이 직접적으로 이유를 설명하는 것은 **`f_acc`와 `f_act` 두 개**에
대해서입니다. 실제로 `__init__`(L110-112)은 세 필터(`f_acc`, `f_act`, `f_rate`)를
모두 같은 `filt_hz`, 같은 `fs`로 생성하지만, `f_rate`까지 같아야 하는 이유는
docstring에 별도로 설명되어 있지 않습니다 → **코드에 명시되어 있지 않음.**

**[해설추가 — 코드에 명시되어 있지 않음, 일반 제어이론에 근거한 설명]**
INDI의 핵심 가정은 "다음 스텝의 실제 각가속도 ≈ 현재 측정된 각가속도 + $G\cdot$(실제
명령 변화량)"이며, `update()`에서 이 식은
$$
\Delta\mathbf{u} = G^{-1}(\boldsymbol\nu-\boldsymbol\alpha_f),\qquad
\boldsymbol\nu = K_{rate}(\boldsymbol\omega_{sp}-\boldsymbol\omega_f)
$$
로 구현됩니다. 여기서 $\boldsymbol\alpha_f$(측정 각가속도), $\mathbf{u}_f$(이전
명령, $\Delta\mathbf u$의 기준점), $\boldsymbol\omega_f$($\nu$ 계산에 쓰이는 각속도)
**세 신호가 모두 같은 시각 기준에서 "지금 이 순간의 상태"를 대표해야** 이 대수식이
의미를 가집니다. 만약 세 필터의 차단주파수(따라서 위상지연)가 서로 다르면, 각
필터는 서로 다른 크기의 군지연(group delay)을 갖게 되어 $\boldsymbol\alpha_f$가
대표하는 "시각"과 $\mathbf{u}_f$ 또는 $\boldsymbol\omega_f$가 대표하는 "시각"이
어긋납니다. 이 경우 $\Delta\mathbf u$는 실제로는 존재하지 않는(위상이 어긋난)
오차를 보정하려 들게 되어, 진동(oscillation)이나 정상상태 편차를 유발할 수
있습니다. 이것이 원 논문(Smeur, Chu & de Croon 2016, docstring L10-12에 인용됨)류
INDI 문헌에서 "synchronization filter"라고 부르는 것의 일반적 근거이며, docstring이
"crux of a working INDI loop"(L40)이라고 강조하는 이유입니다. 다만 이 구체적
설명(위상지연/군지연 논증)은 코드 주석 자체에 쓰인 문장은 아니므로, 논문에는
반드시 별도로 표준 INDI 참고문헌을 인용해야 합니다.

### 4.2 `k_rate`가 물리적으로 무슨 의미인가 (단위 1/s의 해석)

**[코드 근거]** docstring(indi.py L92-93): "proportional gains on body-rate
error -> desired angular accel [1/s]. Larger = faster, noisier. Typical 4-12."

**[해설추가 — 코드에 명시되어 있지 않음, 제어 법칙으로부터의 직접 유도]**
INDI가 $G$, $\boldsymbol\alpha_f$를 정확히 추정한다고 가정하면(이상적인 경우),
실제 각가속도는 목표 각가속도와 같아집니다: $\dot{\boldsymbol\omega}=\boldsymbol\nu
=K_{rate}(\boldsymbol\omega_{sp}-\boldsymbol\omega)$. 각 축을 독립적으로 보면
1차 선형 미분방정식
$$
\dot\omega_i + k_{rate,i}\,\omega_i = k_{rate,i}\,\omega_{sp,i}
$$
이며, 이는 시定수 $\tau_i = 1/k_{rate,i}$의 1차 지연 시스템(극점 $s=-k_{rate,i}$)과
같습니다. 즉 **`k_rate`의 각 성분은 "그 축의 각속도 폐루프 대역폭(bandwidth)"이자
"1차 응답 시상수의 역수"**입니다. 기본값 $(8,8,6)$(indi.py L98)은
$\tau_p=\tau_q=0.125$s, $\tau_r\approx0.167$s를 의미하며(대역폭 약 1.27Hz,
0.95Hz), 실제 `pilot.py`(대상 파일 아님, L53)에서는 $(9,9,6)$을 써서
$\tau_p=\tau_q\approx0.111$s로 약간 더 빠르게 설정되어 있습니다. `k_rate`가 클수록
루프는 더 빨리 응답하지만, 미분에 가까운 고이득 피드백이라 센서 잡음도 그만큼
증폭됩니다 — docstring의 "Larger = faster, noisier"(L93)가 바로 이 트레이드오프를
말합니다. 이 유도는 제어 법칙 수식 자체로부터 나오는 수학적 필연이지만, 코드
주석에 "1차 시상수"라는 말로 쓰여 있지는 않으므로 해설추가로 표시합니다.

### 4.3 `G` 행렬의 동압 스케줄링은 어떤 가정 위에 서 있는가

**[코드 근거]** 모듈 docstring(indi.py L33-36):

> "control effectiveness scales (approximately) with dynamic pressure
> qbar = 0.5*rho*V^2, so G is gain-scheduled on qbar. Because alpha is
> *measured*, G only has to be roughly correct in direction and scale."

구현(L159): $G(\bar q) = \dfrac{\max(\bar q,\bar q_{min})}{\bar q_{ref}}G_0$.

**핵심 가정(코드에 명시된 것만):**
1. 공력 모멘트는 $M = \bar q\, S\, \bar c\, C_M(\delta,\dots)$ 형태이고, 조종면
   미분계수 $C_{M,\delta}$가 동압과 무관하게 대략 일정하다고 가정하면
   $\partial M/\partial u \propto \bar q$가 되어, $G_0$을 식별한 기준 동압
   $\bar q_{ref}$ 대비 현재 동압의 **선형 비율**로만 스케일합니다. 즉 이 스케줄링은
   Mach수, 받음각(AoA), Reynolds수 등에 따른 $C_{M,\delta}$ 자체의 변화는
   반영하지 않는 **1차(동압 비례) 근사**입니다 — 이 세부 사항(Mach/AoA 영향
   무시)은 코드 주석에 별도로 언급되어 있지는 않지만, "qbar = 0.5*rho*V^2에
   비례한다"는 가정 자체가 함의하는 바입니다.
2. INDI 구조 자체가 이 근사의 오차를 상당 부분 흡수합니다: $\boldsymbol\alpha$가
   **측정값**이기 때문에(모델이 아니라 실측 각가속도를 매 스텝 빼주므로), $G$는
   "방향과 크기가 대략만 맞으면"(L36 "roughly correct in direction and scale")
   충분합니다 — 이는 INDI가 근본적으로 모델 오차에 강건(robust)하도록 설계된
   incremental 구조이기 때문입니다.
3. `qbar_min`(기본 20.0, L100)으로 하한을 두는 이유(docstring L96): "저속에서
   $G$가 반전 불가능(non-invertible)해지지 않도록" — 동압이 0에 가까워지면
   $G\to0$이 되어 `update()`의 L160-161에서 $\det G\approx0$이 되고, 이 경우
   유사역행렬로 폴백하더라도 $\Delta\mathbf u$가 비정상적으로 커질 수 있는
   상황을 방지합니다.

**[해설추가 — 코드에 명시되어 있지 않음]** 이 스케줄링은 **등방적(isotropic)
스케일링**이라는 점도 주목할 만합니다 — $G_0$ 행렬 전체에 스칼라 하나($\bar
q/\bar q_{ref}$)를 곱하므로, aileron/elevator/rudder 세 채널이 동압에 대해
정확히 같은 비율로 변한다고 가정합니다. 실제 항공기에서는 각 조종면의 효과도가
동압에 반응하는 정도가 채널마다 다를 수 있는데, 코드는 이를 구분하지 않고 하나의
스칼라로 묶어 스케일합니다. 이 단순화가 타당한지 여부는 코드/주석에 논의되어
있지 않습니다.

### 4.4 리미터(`limiter.py`)의 각 한계는 어떤 물리에서 나왔는가

| 한계 | 물리적 근거 | 코드 위치 |
|---|---|---|
| `g_struct_max` = +9G | F-16 구조 설계 한계(당김) — **[코드 근거]** L12-14, L44 | `LimiterConfig.g_struct_max` |
| `g_struct_min` = −3G | F-16 구조 설계 한계(밀기), 극한하중 −4.5G, 조종사 내성이 아니라 기골 하중 — **[코드 근거]** L12-14, L45-48 | `LimiterConfig.g_struct_min` |
| $G_{aero}(V)$ (코너 스피드 이하 공력 한계) | 최대양력계수에서 낼 수 있는 G는 동압 $\propto V^2$에 비례, 코너 하한에서 구조한계와 정확히 만나도록 정의 — **[코드 근거]** L15-17, `_g_aero` L61-64 | `CombinedLimiter._g_aero` |
| $q_{max}, q_{min}$ (피치레이트 한계) | 양력방향 뉴턴 제2법칙 + 중력의 양력방향 성분($\cos\phi\cos\theta$) 보정 — **[코드 근거]** L18-26, `max_pitch_rate`/`min_pitch_rate` L88-101 | `CombinedLimiter.max_pitch_rate`/`min_pitch_rate` |
| `p_max_dps` = 220 deg/s | **코드에 명시되어 있지 않음** — 물리식 없이 고정 상수로 지정 | `LimiterConfig.p_max_dps` (L51) |
| `r_max_dps` = 30 deg/s | **코드에 명시되어 있지 않음** — 물리식 없이 고정 상수로 지정 | `LimiterConfig.r_max_dps` (L52) |
| `sustained_load_factor` 표 | 물리식이 아니라 **실측 데이터**(정상상태 추력=항력, $P_s=0$ 지점의 달성 G) — **[코드 근거]** L70-79 | `SUSTAINED_KCAS/G_15K/G_25K` |

핵심은 **피치(pitch)축만 물리식으로 매 순간 동적으로 계산되고, 롤·요축은 상수로
고정**되어 있다는 비대칭적 설계입니다. 이는 docstring 서두(L4)가 "L2 가이드가
요청한 각속도 setpoint(**특히 pitch q**)를 기체 한계로 클램프한다"라고 명시한
것과 일치합니다 — 이 리미터가 원래 목표로 하는 것은 G-하중 관리(=pitch)이며,
롤/요 한계는 부차적인 안전판입니다.

---

## 5. 실제 호출값 (참고 — 대상 세 파일 밖의 코드)

아래 값들은 대상 파일 안의 "기본값"이 아니라, 다른 파일에서 이 클래스들을
**실제로 생성할 때 넘기는 값**입니다. 대상 파일 세 개만 다루라는 요구사항에 따라
본문에는 포함하지 않았지만, 기본값과 실사용값이 다르다는 점이 논문에서 오해를
피하는 데 도움이 되므로 참고로 남깁니다.

```python
# pilot.py, L37-38 (참고, 대상 파일 아님)
37       self.shim = QuaternionAttitudeShim(k_att=4.0, k_yaw_damp=1.5,
38                                          rate_limit_dps=(180.0, 60.0, 30.0))
```
```python
# pilot.py, L52-53 (참고, 대상 파일 아님)
52       self.indi = INDIRateController(self.dt_phys, G0, qbar_ref,
53                                      k_rate=(9.0, 9.0, 6.0), filt_hz=25.0)
```

| 파라미터 | `attitude.py`/`indi.py` 기본값 | `pilot.py` 실사용값 |
|---|---|---|
| `k_att` | 4.5 | 4.0 |
| `rate_limit_dps` | (120, 60, 30) | (180, 60, 30) |
| `k_rate` | (8, 8, 6) | (9, 9, 6) |
| `filt_hz` | 20.0 | 25.0 |
| `dt` (INDI) | (인자 필수, 기본값 없음) | `dt_phys` = 1/120 s (물리 스텝 주파수 120Hz, pilot.py L27) |

`LimiterConfig`도 `bfm_guidance.py`(대상 파일 아님, L112-114)에서
`kcas_corner_lo`/`kcas_corner_hi`를 `Doctrine` 객체값으로 덮어쓰지만, 구체적 값은
`bfm_guidance.py`/`Doctrine` 정의를 봐야 하므로 이 문서(대상: limiter.py만)의
범위 밖입니다.

---

## 6. 부록 — "코드에 명시되어 있지 않음" 전체 목록

논문 작성 시 "가정" 또는 "한계점(limitation)" 절에 쓸 수 있도록, 본문에서 명시적으로
"코드에 근거 없음"이라 표시한 항목을 모읍니다.

1. `f_rate`(indi.py L112)가 `f_acc`/`f_act`와 같은 `filt_hz`를 써야 하는 이유는
   docstring이 명시적으로 설명하지 않음 (docstring은 `f_acc`/`f_act` 두 필터의
   동기화만 언급, L38-40). — §4.1
2. `max_pitch_rate`/`min_pitch_rate`(limiter.py L94, L100)의 속도 하한 1.0 ft/s의
   구체적 수치가 왜 1.0인지에 대한 물리적 근거 없음.
3. `max_pitch_rate`/`min_pitch_rate`의 바깥쪽 `max(0.0,...)`/`min(0.0,...)` 클램프의
   설계 의도(어떤 상황을 막기 위한 것인지)가 주석에 설명되어 있지 않음.
4. `g_lift` 기본값 0.0(나이프에지 가정)이 왜 기본값으로 선택되었는지 근거 없음
   (limiter.py L89, L98, L104).
5. `LimiterConfig.p_max_dps`(220 deg/s), `r_max_dps`(30 deg/s)의 물리적 도출식이
   코드/주석에 없음 — 피치 한계와 달리 상수로 직접 지정됨. — §4.4
6. `LimiterConfig.kcas_corner_hi`(440 KCAS)는 정의되어 있으나 `limiter.py` 내
   어떤 계산에서도 사용되지 않음(참고용 상수로만 존재).
7. `identify_G0`의 `delta`(0.02), `settle`(3)이 왜 그 값인지(예: 특정 조종면
   해상도나 JSBSim 안정화 시간과의 관계)에 대한 근거 없음.
8. G 행렬 동압 스케줄링이 Mach수/AoA 등 동압 이외 요인에 의한 $C_{M,\delta}$
   변화를 무시한다는 점은 docstring에 직접 언급되어 있지 않고, "qbar에 비례"라는
   가정으로부터 추론한 것. — §4.3
