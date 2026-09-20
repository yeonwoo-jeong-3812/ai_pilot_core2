# 실험 설계 노트 — INDI 파라미터(k_rate, filt_hz)가 기동 실현 충실도·모델 불확실성 강건성에 미치는 영향

이 문서는 위 연구 주제를 진행하기 위해 **지금 이 저장소에 실제로 존재하는 코드**만
근거로 정리한 실험 설계 노트입니다. 제어 법칙 자체의 수식/기호 설명은
[`docs/LEARNING_L3.md`](./LEARNING_L3.md)에 이미 있으므로 여기서는 반복하지 않고,
**"실험을 어떻게 돌리고, 무엇을 고정하고, 무엇을 기록해야 하는가"**에만 집중합니다.

**표기 규칙**은 `LEARNING_L3.md`와 동일합니다: **[코드 근거]** / **[해설추가 — 코드에
명시되어 있지 않음]**, 그리고 코드 인용 블록에는 실제 줄 번호를 붙입니다.

## 0. 연구 질문과 실험 스크립트의 대응

저장소에는 이 연구를 위한 스윕(sweep) 스크립트가 이미 두 개 존재합니다(둘 다
`git status`상 아직 커밋 안 된 새 파일):

| 스크립트 | 시나리오 | k_rate/filt_hz 그리드 | 출력 |
|---|---|---|---|
| `scripts/run_indi_step_sweep.py` | 뱅크각 스텝 응답 (45°→bank_deg 목표) | `k_scale`×`filt_hz` (+`bank_deg`) | `results/indi_step_sweep/{timeseries,summary}.csv` |
| `scripts/run_corner_pull_sweep.py` | 코너 스피드 지속 당김 (목표 G 지령) | `k_scale`×`filt_hz` (+`g_target`) | `results/corner_pull_sweep/{timeseries,summary}.csv` |

둘 다 **`k_rate` 자체가 아니라 `k_scale`**(운용값 `(9.0,9.0,6.0)`에 곱하는 배율)을
그리드 변수로 씁니다. `filt_hz`는 그대로 그리드 변수입니다. 이 문서 1절은 이
`k_scale`/`filt_hz`가 실제로 어떻게 `k_rate`로 바뀌고 최종 조종면 명령까지 가는지를
줄 단위로 추적합니다.

---

## 1. k_rate / filt_hz 주입 경로 — 호출 순서 추적

### 1.1 `run_indi_step_sweep.py` 기준 전체 경로

**① 그리드 상수 정의**

```python
# scripts/run_indi_step_sweep.py, L46-50
46   K_RATE_BASE = (9.0, 9.0, 6.0)          # 실제 운용값 (run_indi_step.py 와 동일)
47   BANK_DEG_GRID = (0.0, 15.0, 30.0, 45.0, 60.0)
48   K_SCALE_GRID = (0.5, 0.75, 1.0, 1.5, 2.0)
49   FILT_HZ_GRID = (10.0, 15.0, 25.0, 35.0, 50.0)
50   FILT_HZ_DEFAULT = 25.0                  # run_indi_step.py 의 기본값 (quick 모드 고정값)
```

**② 그리드 순회 → `run_one` 호출**

```python
# scripts/run_indi_step_sweep.py, L172-181, L208-209
172  def iter_grid(quick: bool):
173      if quick:
174          for bank_deg in BANK_DEG_GRID[:2]:
175              for k_scale in K_SCALE_GRID[:2]:
176                  yield bank_deg, k_scale, FILT_HZ_DEFAULT
177      else:
178          for bank_deg in BANK_DEG_GRID:
179              for k_scale in K_SCALE_GRID:
180                  for filt_hz in FILT_HZ_GRID:
181                      yield bank_deg, k_scale, filt_hz
...
208      for i, (bank_deg, k_scale, filt_hz) in enumerate(combos, 1):
209          rows, summary = run_one(bank_deg, k_scale, filt_hz)
```

**③ `k_scale` → `k_rate` 벡터로 변환 (여기가 "주입"이 실제로 일어나는 첫 지점)**

```python
# scripts/run_indi_step_sweep.py, L70-79
70   def run_one(bank_deg: float, k_scale: float, filt_hz: float,
71               dt: float = DT, t_total: float = T_TOTAL):
...
78       run_id = f"bank{bank_deg:g}_k{k_scale:g}_f{filt_hz:g}"
79       k_rate = tuple(k * k_scale for k in K_RATE_BASE)
```

$$
\mathbf{k}_{rate} = k_{scale}\cdot(9.0,\ 9.0,\ 6.0)
$$

**④ `INDIRateController` 생성자에 `k_rate`, `filt_hz` 전달**

```python
# scripts/run_indi_step_sweep.py, L86-90
86       G0, qbar_ref = identify_G0(p.fdm)
87       rate = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
88       rate.reset(u0=[p["fcs/aileron-cmd-norm"],
89                      p["fcs/elevator-cmd-norm"],
90                      p["fcs/rudder-cmd-norm"]])
```

이 호출은 `aircombat/control/indi.py`의 `INDIRateController.__init__`(L98-115)으로
들어갑니다. 그 안에서:

```python
# aircombat/control/indi.py, L104, L108-112
104          self.k_rate = np.asarray(k_rate, float)
...
108          fs = 1.0 / self.dt
110          self.f_acc = SecondOrderLPF(filt_hz, fs, 3)
111          self.f_act = SecondOrderLPF(filt_hz, fs, 3)
112          self.f_rate = SecondOrderLPF(filt_hz, fs, 3)   # rate used in the error term
```

`k_rate`는 인스턴스 속성 `self.k_rate`로 저장되고, `filt_hz`는 그 자리에서 소비되어
(다시 꺼낼 수 없는 형태로) 세 `SecondOrderLPF` 필터 계수(`b0,b1,b2,a1,a2`, 같은 파일
L52-62)로 변환됩니다.

**⑤ 매 제어 스텝에서 실제로 사용되는 지점**

```python
# scripts/run_indi_step_sweep.py, L106-125
106      for k in range(n):
107          t = k * dt
...
117          psi = p["attitude/psi-rad"]
118          omega_sp = shim.rate_setpoint_euler(phi, theta, psi,
119                                              phi_sp, theta_trim, psi, r_cur=omega[2])
120  
121          u = rate.update(omega, omega_sp, qbar, ang_accel=ang_acc)
122          p["fcs/aileron-cmd-norm"] = u[0]
123          p["fcs/elevator-cmd-norm"] = u[1]
124          p["fcs/rudder-cmd-norm"] = u[2]
125          p.step(1)
```

`rate.update(...)` 호출은 `indi.py`의 `update()`(L123-167)로 들어가고, 그 안에서:

```python
# aircombat/control/indi.py, L145, L148, L151, L154, L159-163
145          alpha_f = self.f_acc(alpha_raw)          # filt_hz로 만든 필터 #1 사용
148          u_f = self.f_act(self.u_prev)            # filt_hz로 만든 필터 #2 사용
151          omega_f = self.f_rate(omega)              # filt_hz로 만든 필터 #3 사용
154          nu = self.k_rate * (omega_sp - omega_f)   # k_rate 사용 지점
...
159          G = (max(qbar, self.qbar_min) / self.qbar_ref) * self.G0
160          du = np.linalg.solve(G, nu - alpha_f) if abs(np.linalg.det(G)) > 1e-9 \
161              else np.linalg.pinv(G) @ (nu - alpha_f)
162  
163          u = np.clip(u_f + du, self.u_min, self.u_max)
```

즉 `k_rate`는 오직 L154 한 곳(비례 오차 게인)에서, `filt_hz`는 L145/L148/L151
세 필터의 "속도"(위상지연)를 통해 간접적으로 L154·L159·L160의 모든 계산에 영향을
줍니다. 결과 `u`(L163, `indi.py`)가 `update()`의 반환값이 되어 `run_one`의 L121로
돌아옵니다.

**⑥ 최종 조종면 명령 도달**

L122-124(`run_indi_step_sweep.py`)에서 `u[0],u[1],u[2]`가 JSBSim 프로퍼티
`fcs/aileron-cmd-norm`, `fcs/elevator-cmd-norm`, `fcs/rudder-cmd-norm`에 직접
대입되고, L125의 `p.step(1)`(→ `aircombat/fdm/plant.py` `F16Plant.step`, L108-111,
내부적으로 `self.fdm.run()`)에서 JSBSim이 이 명령으로 한 스텝 적분합니다.
**cmd-norm 값이 실제 조종면 편향각으로 바뀌는 과정(F-16 native FLCS)은 JSBSim
XML 모델(`jsbsim_data/`) 내부이며, 이 저장소의 파이썬 코드 범위 밖 — 코드에
명시되어 있지 않음** (`plant.py` L10-11 주석이 "JSBSim fcs/*-cmd-norm 경유 →
native FLCS 안정성증강 적용 후 조종면"이라고만 언급).

**⑦ 기록**

같은 루프에서 L130-136이 `u[0],u[1],u[2]`를 포함한 한 행을 `rows`에 쌓고,
`main()`의 L210(`w_ts.writerows(rows)`)에서 `timeseries.csv`에 씁니다(§4 참조).

**정리하면 주입 경로는:**
```
K_SCALE_GRID/FILT_HZ_GRID (L48-49, 상수)
  → iter_grid (L172-181)
  → run_one(bank_deg, k_scale, filt_hz) (L70)
  → k_rate = k_scale * K_RATE_BASE (L79)
  → INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz) (L87)
      → indi.py __init__: self.k_rate (L104), f_acc/f_act/f_rate 생성 (L110-112)
  → 매 스텝 rate.update(...) (L121)
      → indi.py update(): f_acc/f_act/f_rate 호출 (L145,148,151)
                           → nu = k_rate*(omega_sp-omega_f) (L154)
                           → G, du, u = clip(u_f+du,...) (L159-163)
  → u[0..2] → p["fcs/*-cmd-norm"] = u[...] (L122-124)
  → p.step(1) → JSBSim FLCS/공력모델(코드 범위 밖) → 실제 조종면·모멘트
  → rows.append(...) (L130-136) → timeseries.csv (L210)
```

### 1.2 `run_corner_pull_sweep.py`와의 차이점

구조는 동일하되 두 지점이 다릅니다:

1. **리미터가 경로에 추가됨.** `omega_sp`가 INDI에 들어가기 전에
   `CombinedLimiter.limit_omega_sp`를 거칩니다:
   ```python
   # scripts/run_corner_pull_sweep.py, L122-130
   122          g_allowed = limiter.max_load_factor(kcas)
   123          g_cmd = min(g_target, g_allowed)     # 안전 상한(리미터) 안에서 목표G 지령
   124          q_cmd = (g_cmd - g_lift) * G_FT_S2 / max(v_fps, 1.0)
   125  
   126          q_cur = euler_to_quat(phi, theta, psi)
   127          q_des = quat_mul(q_cur, euler_to_quat(phi_target - phi, 0.0, 0.0))
   128          omega_sp = shim.rate_setpoint(q_cur, q_des, r_cur=pqr[2])
   129          omega_sp[1] = q_cmd
   130          omega_sp, flags = limiter.limit_omega_sp(omega_sp, v_fps, kcas, g_lift=g_lift)
   ```
   즉 `k_rate`/`filt_hz`가 INDI에 미치는 영향을 보기 전에, 이미 리미터가 `omega_sp`를
   한 번 클램프한다는 점을 잊으면 안 됩니다(§2에서 이 리미터 자체는 고정 대상임을 다룹니다).
2. **조종면 전달 방식이 다름.** `p["fcs/*-cmd-norm"]=...` 대신
   `p.set_input([1.0, u[1], u[0], u[2]])`(L135, `F16Plant.set_input`,
   `plant.py` L121-125 경유 — 내부는 결국 동일한 `fcs/*-cmd-norm` 프로퍼티에 씀)를
   씁니다. 스로틀은 `1.0`(풀 애프터버너, "지속 선회 속도 유지"를 위해 L88에서
   `throttle-cmd-norm=1.0`으로 트림).
3. `k_rate`/`filt_hz`가 `INDIRateController`에 주입되는 지점은 동일한 패턴입니다
   (L91-92): `indi = INDIRateController(dt, G0, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)`.

---

## 2. 절대 바꾸면 안 되는 값

| 값 | 현재 고정값 | 스윕 스크립트에서의 위치 | 왜 고정해야 하는가 (근거) |
|---|---|---|---|
| **dt** (제어/물리 공통 스텝) | `1/120` s | `DT = 1.0/120.0` (`run_indi_step_sweep.py` L42, `run_corner_pull_sweep.py` L45); `F16Plant(dt=dt)`(각 L81/L86); `INDIRateController(dt, ...)`(각 L87/L92) | **[코드 근거]** `indi.py` L108: `fs = 1.0/self.dt`. `filt_hz`로 만드는 biquad 계수(`indi.py` L54-62)는 `fs`(=`1/dt`)에 의존합니다. `dt`를 실험마다 바꾸면 "같은 `filt_hz` 숫자"가 매번 다른 이산 필터가 되어, `filt_hz`의 효과만 분리해서 보려는 이 실험의 전제(§0)가 깨집니다. 또한 `pilot.py` L3-7 주석은 L3/L4(제어/물리)가 항상 120Hz로 위상 동기화됨을 명시하며, `LEARNING_L3.md` §4.1이 설명하듯 이 동기화가 INDI 성립의 전제입니다. |
| **qbar_min** | `20.0` (기본값, 두 스크립트 모두 override 안 함) | `INDIRateController.__init__` 기본값 (`indi.py` L100); 두 스윕 스크립트의 생성자 호출(`run_indi_step_sweep.py` L87, `run_corner_pull_sweep.py` L92)에 인자로 전달되지 않음 → 기본값 그대로 사용 | **[코드 근거]** `indi.py` L96 docstring: "floor on qbar to keep G invertible at low airspeed." 이 값은 저속에서 $G$가 0에 가까워져 특이(singular)해지는 것을 막는 **수치적 안전장치**이지 연구 대상인 제어 이득이 아닙니다. 바꾸면 저속 구간에서만 별도의 교란 변수가 추가되어 `k_rate`/`filt_hz`의 효과와 뒤섞입니다. |
| **u_min / u_max** | `(-1,-1,-1)` / `(1,1,1)` (기본값, override 없음) | `INDIRateController.__init__` 기본값 (`indi.py` L99) | **[코드 근거]** `indi.py` L94 docstring: "actuator command saturation (e.g. -1..1 normalised)" — 이는 F-16 조종면의 **물리적 이동 범위**를 나타내는 하드웨어 제약이지 제어 이득이 아닙니다. 또한 두 스윕 스크립트의 포화율 지표(`sat_aileron_pct` 등)가 `np.abs(u) > 0.999`(`run_indi_step_sweep.py` L139, `run_corner_pull_sweep.py` L151)로 **정확히 이 ±1 경계에 맞춰 계산**되므로, `u_min/u_max`를 바꾸면 포화율 수치 자체가 다른 기준으로 계산되어 조합 간 비교가 무의미해집니다. |
| **리미터 한계** (`LimiterConfig`의 `g_struct_max/min`, `kcas_corner_lo/hi`, `p_max_dps`, `r_max_dps`) | 전부 기본값 (9.0, −3.0, 330.0, 440.0, 220.0, 30.0) | `run_corner_pull_sweep.py` L97: `limiter = CombinedLimiter(LimiterConfig())` (인자 없이 기본값 사용). **`run_indi_step_sweep.py`는 리미터를 아예 호출하지 않음**(import·인스턴스화 없음) — 즉 이 스크립트에서는 "고정"할 대상 자체가 코드 경로에 존재하지 않음. | **[코드 근거]** `limiter.py` L44-52 및 `LEARNING_L3.md` §4.4: 이 값들은 F-16의 **구조/공력 한계(D6 불변식)** 이며 제어기 파라미터가 아닙니다. 연구 질문은 "INDI가 주어진 지령을 얼마나 충실히 추종하는가"이지 "봉투를 넓히면 포화가 줄어드는가"가 아니므로, 리미터 값을 `k_scale`/`filt_hz`와 같이 흔들면 두 요인이 뒤섞여 인과관계를 해석할 수 없습니다. |

---

## 3. G0를 왜곡해 모델 불확실성을 주입하는 방법

`identify_G0`(`indi.py` L179-204)는 **JSBSim 플랜트를 실제로 흔들어 측정한 값**이므로,
이 자체는 "참값"입니다. 모델 불확실성을 만들려면 **컨트롤러가 믿는 값과 플랜트의
실제 반응 사이에 인위적인 차이**를 만들어야 합니다. 삽입 지점 기준으로 세 가지
방법을 제시합니다(모두 "코드에 이렇게 삽입하면 된다"는 설계 제안이며, 현재
코드에는 구현되어 있지 않습니다 — 즉 아래 코드는 **제안**이지 기존 코드 인용이
아닙니다).

### 방법 A — G0 자체를 사후 왜곡 (컨트롤러 내부 모델만 오염)

**삽입 지점:** `identify_G0` 호출 직후, `INDIRateController` 생성 직전
(`run_indi_step_sweep.py` L86-87 사이 / `run_corner_pull_sweep.py` L91-92 사이).

```python
G0, qbar_ref = identify_G0(p.fdm)
G0_used = G0 @ D_scale        # 또는 G0 + noise_matrix (구조적 왜곡)
rate = INDIRateController(dt, G0_used, qbar_ref, k_rate=k_rate, filt_hz=filt_hz)
```

- `D_scale`이 대각행렬이면 채널별(aileron/elevator/rudder) 효과도 배율 오차,
  비대각 성분을 넣으면 축간 교차결합(cross-coupling) 오차(예: 손상으로 인한
  비대칭 효과)를 표현합니다.

| 장점 | 단점 |
|---|---|
| "실제 물리(plant)"와 "컨트롤러가 믿는 모델"을 완전히 분리 — `LEARNING_L3.md` §4.3에서 다룬 "G는 방향·크기만 대략 맞으면 된다"는 가정을 직접 검증 가능. `D_scale`을 고정된 행렬로 주면 재현 가능한 결정론적 스윕 변수가 됨. | INDI는 $\boldsymbol\alpha$를 **측정**하므로(`indi.py` L144, 두 스윕 스크립트 모두 `ang_accel=ang_acc`로 실측값 전달), 대각(채널 독립) 오차 상당 부분이 피드백으로 상쇄됨 — 눈에 띄는 효과를 보려면 왜곡을 꽤 크게 주거나 비대각 성분이 필요할 수 있음. 또한 왜곡이 커서 $G$가 특이에 가까워지면 `indi.py` L160-161의 `solve`→`pinv` 분기가 조용히 바뀌는데, 이 전환점 자체가 결과에 불연속을 만들 수 있어 **어느 분기를 탔는지 별도로 기록**해야 함(§5 참조). |

### 방법 B — qbar_ref만 왜곡 (스케줄링 기준점 오염)

**삽입 지점:** `INDIRateController` 생성자의 두 번째 위치 인자
(`run_indi_step_sweep.py` L87 / `run_corner_pull_sweep.py` L92).

```python
rate = INDIRateController(dt, G0, qbar_ref * ref_bias, k_rate=k_rate, filt_hz=filt_hz)
```

`ref_bias`(예: 0.7~1.3)를 새 그리드 축으로 추가.

| 장점 | 단점 |
|---|---|
| 파라미터 하나로 `LEARNING_L3.md` §4.3이 지적한 "동압 비례 가정"의 오차를 정확히 표현 — `identify_G0`를 잘못된 트림 조건에서 돌렸거나 트림이 서서히 변한 상황과 동일. 해석이 쉬움: 임의 시점의 유효 스케일 오차는 $\bar q_{ref,true}/\bar q_{ref,used}$로 **속도에 무관한 상수 배율**이라 이론값과 직접 비교 가능. | 스칼라 하나짜리 균일 오차만 표현 가능 — 축별(예: 에일러론만 효과 저하)이나 국소적(특정 받음각에서만) 오차는 표현 못함. `ref_bias`가 크면 `qbar_min` 클램프(`indi.py` L159, 이 값 자체는 §2에서 고정 대상)와 상호작용하는 영역이 넓어지므로 저속 구간 해석에 주의 필요. |

### 방법 C — plant 쪽 조종면 효과를 실제로 저하 (액추에이터 결함 주입)

**삽입 지점:** INDI 출력이 플랜트에 쓰이는 지점
(`run_indi_step_sweep.py` L122-124 / `run_corner_pull_sweep.py` L135).

```python
eff = np.array([eff_ail, eff_ele, eff_rud])   # 예: (1.0, 1.0, 1.0)=정상
u_applied = u * eff
p["fcs/aileron-cmd-norm"] = u_applied[0]
p["fcs/elevator-cmd-norm"] = u_applied[1]
p["fcs/rudder-cmd-norm"] = u_applied[2]
```

| 장점 | 단점 |
|---|---|
| A/B와 성격이 다른 실험 — 컨트롤러 내부 모델(`G0`,`qbar_ref`)은 그대로 두고 **플랜트 자체**를 바꾸므로, INDI 문헌이 주장하는 "실측 가속도 덕분에 액추에이터/공력 모델 오차에 강건하다"(`indi.py` L35-36, `LEARNING_L3.md` §4.3 항목 2)는 성질을 직접 검증. `ang_accel`이 실제 JSBSim 가속도(L113-115/L132-133)에서 오므로 INDI가 다음 스텝에 결함을 "본다". | INDI가 이런 결함에 원래 강해야 하는 성질이므로, 지표가 거의 안 움직이는 "널 결과"가 나올 수 있음 — 이를 "모델 불확실성(G) 영향 없음"으로 오독하면 안 되고, "액추에이터 결함에 대한 강건성 확인/반증"으로 별도 해석해야 함(A/B와 다른 가설). 결함이 언제 `alpha_f`에 반영되는지는 `filt_hz`(동기화 필터, `LEARNING_L3.md` §4.1)에 달려 있어, 스윕 대상인 `filt_hz`와 이 조작이 서로 얽힘 — 의도한 교란 변수인지 확인 필요. |

**권장:** A(또는 B)는 "INDI 역변환 단계의 모델 오차 강건성", C는 "INDI 폐루프의
실제 결함 강건성"이라는 **서로 다른 연구 질문**에 대응합니다. 논문 제목이
"모델 불확실성 강건성"이라면 A/B가 더 직접적인 조작이고, C는 대조 실험(비교군)으로
같이 넣으면 논지가 강해집니다.

---

## 4. `timeseries.csv` 열 대응표

두 스크립트가 각자 `timeseries.csv`를 만들며 헤더가 다릅니다(공통 부분이 대부분).

### 4.1 `results/indi_step_sweep/timeseries.csv` (또는 `--out-dir`로 지정한 경로)

```python
# scripts/run_indi_step_sweep.py, L52-58
52   TS_HEADER = [
53       "run_id", "bank_deg", "k_scale", "filt_hz", "t",
54       "omega_sp_p_dps", "omega_sp_q_dps", "omega_sp_r_dps",
55       "omega_p_dps", "omega_q_dps", "omega_r_dps",
56       "cmd_aileron", "cmd_elevator", "cmd_rudder",
57       "alpha_deg", "qbar_psf",
58   ]
```

행 생성:
```python
# scripts/run_indi_step_sweep.py, L130-136
130      rows.append([
131          run_id, bank_deg, k_scale, filt_hz, round(t, 6),
132          *np.rad2deg(omega_sp).round(6),
133          *np.rad2deg(omega).round(6),
134          round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
135          round(float(alpha_deg), 6), round(float(qbar), 6),
136      ])
```

| CSV 열 | 소스 변수/식 | 정의 줄 |
|---|---|---|
| `run_id` | `f"bank{bank_deg:g}_k{k_scale:g}_f{filt_hz:g}"` | L78 |
| `bank_deg` | 그리드 값(뱅크각 목표, deg) | L47(그리드), L70(인자) |
| `k_scale` | 그리드 값(k_rate 배율) | L48(그리드), L70(인자) |
| `filt_hz` | 그리드 값(Hz) 또는 quick 모드 시 `FILT_HZ_DEFAULT` | L49-50, L70(인자) |
| `t` | `k * dt` | L107 |
| `omega_sp_p_dps/q/r` | `np.rad2deg(omega_sp)`, `omega_sp = shim.rate_setpoint_euler(...)` (INDI에 들어가는 지령, 이 스크립트엔 리미터 없음) | L118-119, L132 |
| `omega_p/q/r_dps` | `np.rad2deg(omega)`, `omega = [p["velocities/p-rad_sec"], q, r]` — **원시(raw) 측정값**, `indi.py`가 내부적으로 필터링한 `omega_f`가 아님 | L109-111, L133 |
| `cmd_aileron/elevator/rudder` | `u[0],u[1],u[2] = rate.update(...)` — INDI 최종 출력, 같은 값이 다음 줄에서 `fcs/*-cmd-norm`에 그대로 대입됨 | L121-124, L134 |
| `alpha_deg` | `np.rad2deg(p["aero/alpha-rad"])` — 받음각(정보용, 제어 루프 입력 아님) | L128, L135 |
| `qbar_psf` | `p["aero/qbar-psf"]` — 그 스텝에서 `rate.update()`에 넘긴 동압 | L112, L135 |

### 4.2 `results/corner_pull_sweep/timeseries.csv`

```python
# scripts/run_corner_pull_sweep.py, L57-63
57   TS_HEADER = [
58       "run_id", "g_target", "k_scale", "filt_hz", "t",
59       "omega_sp_p_dps", "omega_sp_q_dps", "omega_sp_r_dps",
60       "omega_p_dps", "omega_q_dps", "omega_r_dps",
61       "cmd_aileron", "cmd_elevator", "cmd_rudder",
62       "alpha_deg", "qbar_psf",
63   ]
```

행 생성:
```python
# scripts/run_corner_pull_sweep.py, L143-149
143      rows.append([
144          run_id, g_target, k_scale, filt_hz, round(t, 6),
145          *np.rad2deg(omega_sp).round(6),
146          *np.rad2deg(pqr).round(6),
147          round(float(u[0]), 6), round(float(u[1]), 6), round(float(u[2]), 6),
148          round(alpha_deg, 6), round(float(qbar), 6),
149      ])
```

| CSV 열 | 소스 변수/식 | 정의 줄 |
|---|---|---|
| `run_id` | `f"G{g_target:g}_k{k_scale:g}_f{filt_hz:g}"` | L83 |
| `g_target` | 그리드 값(지령 목표 G) — `bank_deg` 대신 이 열이 들어감 | L52(그리드), L75(인자) |
| `k_scale`, `filt_hz` | §4.1과 동일 | L53-55, L75 |
| `t` | `k * dt` | L114 |
| `omega_sp_p_dps/q/r` | `np.rad2deg(omega_sp)` — **리미터를 거친 뒤의 값**(`omega_sp, flags = limiter.limit_omega_sp(...)`, L130) | L126-130, L145 |
| `omega_p/q/r_dps` | `np.rad2deg(pqr)`, `pqr = [p["velocities/p-rad_sec"], q, r]` — 원시 측정값 | L117-118, L146 |
| `cmd_aileron/elevator/rudder` | `u[0],u[1],u[2] = indi.update(...)` | L134, L147 |
| `alpha_deg` | `float(np.degrees(p["aero/alpha-rad"]))` | L140, L148 |
| `qbar_psf` | `p["aero/qbar-psf"]` | L141, L148 |

두 파일의 차이는 실질적으로 `bank_deg` ↔ `g_target` 한 열뿐이며, 나머지 12개 열은
이름·의미가 동일합니다. 단, **`omega_sp_*`가 corner_pull에서는 리미터 통과 후
값**이고 indi_step에서는 리미터가 아예 없다는 점은 두 CSV를 같이 분석할 때
반드시 구분해야 합니다.

---

## 5. 지금 기록되지 않지만 필요할 수 있는 값

연구 질문(모델 불확실성 강건성)을 검증하려면 아래 값들이 필요할 가능성이 높은데,
현재 두 스크립트 모두 기록하지 않습니다. 항목별로 "코드를 고쳐야 하는지, 아니면
스윕 스크립트에서 이미 공개된(public) 속성을 읽기만 하면 되는지"를 구분했습니다
— `indi.py`의 `INDIRateController`/`SecondOrderLPF`는 모든 속성이 밑줄(`_`) 없이
공개되어 있어(예: `self.k_rate`, `self.f_acc`, `self.G0`), 상당수는 **`indi.py`를
전혀 건드리지 않고** 스윕 스크립트 쪽에서 `rate.update(...)` 호출 직후 값을
읽기만 하면 얻을 수 있습니다.

| 필요한 값 | 지금 기록 안 되는 이유 | 기록 방법 |
|---|---|---|
| **리미터 개입 플래그** (`p_limited`,`q_limited`,`r_limited`,`g_max`,`g_min`,`q_max`,`q_min`) | `run_corner_pull_sweep.py` L130에서 `flags`가 계산되지만 **버려짐**(TS_HEADER/summary 어디에도 안 들어감). `run_indi_step_sweep.py`는 리미터 자체를 호출하지 않음. | **corner_pull_sweep.py**: 이미 계산된 `flags`(L130) 딕셔너리를 `TS_HEADER`(L57-63)에 열 추가 후 `rows.append(...)`(L143-149)에 `flags["p_limited"]` 등을 추가하면 됨 — **간단한 수정**. **indi_step_sweep.py**: 이 시나리오엔 리미터가 아예 없으므로, 플래그를 얻으려면 `CombinedLimiter` 인스턴스를 새로 만들고 `omega_sp`를 실제로 클램프하는 로직을 추가해야 함 — 이는 로깅이 아니라 **실험 설계 자체의 변경**(현재는 뱅크 스텝에 리미터가 개입하지 않는 것이 의도된 시나리오인지 확인 필요). |
| **G 행렬의 실시간 값** ($G(\bar q)$, 3×3, `indi.py` L159) | `update()` 내부 지역변수 `G`로만 존재하고 `self`에 저장되지 않음(계산 후 폐기). | **`indi.py`를 고치지 않아도 됨.** `rate.qbar_min`, `rate.qbar_ref`, `rate.G0`가 모두 공개 속성(`indi.py` L102-107)이므로, 스윕 스크립트에서 매 스텝 `qbar`를 이미 알고 있는 채로 `G_now = (max(qbar, rate.qbar_min)/rate.qbar_ref) * rate.G0`를 직접 재계산해 로그에 추가하면 됩니다. `solve` vs `pinv` 분기(L160-161) 여부도 `abs(np.linalg.det(G_now)) > 1e-9`로 동일하게 재현 가능. |
| **필터 내부 상태** ($\alpha_f$, $u_f$, $\omega_f$) | `update()` 내부 지역변수(`alpha_f`,`u_f`,`omega_f`)로만 존재. | **`indi.py`를 고치지 않아도 됨.** `SecondOrderLPF.__call__`(`indi.py` L71-77)이 매 호출 끝에 `self.y1[:] = y`(L76)로 최신 출력을 저장하므로, `rate.update(...)` 호출 **직후** `rate.f_acc.y1`(=그 스텝의 $\alpha_f$), `rate.f_act.y1`(=$u_f$), `rate.f_rate.y1`(=$\omega_f$)를 그대로 읽으면 됩니다. |
| **목표 각가속도 $\nu$, 증분 $\Delta u$** | `update()` 내부 지역변수(`nu`,`du`)로만 존재. | **`indi.py`를 고치지 않아도 됨** (위 두 항목의 조합). `nu = rate.k_rate * (omega_sp - rate.f_rate.y1)`(호출 직후 재계산), `du = u - rate.f_act.y1`(`u`는 `update()`의 반환값). |
| **원시 각가속도** ($\dot p,\dot q,\dot r$, `ang_accel`로 전달되는 값) | `alpha_deg`(받음각)만 기록되고, INDI에 실제로 들어가는 `ang_acc` 리스트 자체는 로그에 없음. | **코드 수정 불필요, 로그 추가만 필요.** 두 스크립트 모두 이 값을 이미 지역변수로 갖고 있음(`run_indi_step_sweep.py` L113-115의 `ang_acc`, `run_corner_pull_sweep.py` L132-133) — `TS_HEADER`에 열 추가 후 `rows.append(...)`에 포함시키면 됨. |
| **G0 왜곡 계수 자체** (§3에서 방법 A/B/C 채택 시) | 현재 코드에 왜곡 메커니즘 자체가 없음. | §3에서 추가한 `D_scale`/`ref_bias`/`eff` 값을 `run_id`나 별도 열로 `TS_HEADER`/`SUMMARY_HEADER`에 추가해야, 나중에 CSV만 보고도 어떤 왜곡 조건이었는지 재구성 가능. 이건 §3 구현과 함께 반드시 같이 추가해야 하는 항목. |

---

## 6. 부록 — 코드에 명시되어 있지 않음 목록

1. JSBSim FLCS가 `fcs/*-cmd-norm`을 실제 조종면 편향각으로 바꾸는 내부 로직 —
   이 저장소의 파이썬 코드가 아니라 `jsbsim_data/`의 F-16 XML 모델 내부(§1.1 ⑥).
2. `run_indi_step_sweep.py`에 리미터가 왜 빠져 있는지(의도적 설계인지 누락인지)에
   대한 설명은 코드/주석에 없음 — 모듈 docstring(L1-24)은 "run_indi_step.py 기반"
   이라고만 하고 리미터 유무를 언급하지 않음.
3. `identify_G0`의 `delta=0.02`, `settle=3`이 이 특정 F-16 트림 조건에 왜 충분한지
   (수치적 근거)는 `indi.py`에 없음(`LEARNING_L3.md` 부록에도 동일 항목 있음).
4. G0 왜곡(§3)이 실제로 어느 정도 크기부터 `solve`→`pinv` 분기 전환이나 발산을
   일으키는지에 대한 수치적 임계값은 코드에 없음 — 실험으로 직접 확인해야 함.
