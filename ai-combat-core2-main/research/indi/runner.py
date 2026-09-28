"""INDI 연구 하네스 — 1경기 실행 (bridge.CompetitionMatch 의 연구판).

서버 계약(bridge·tournament)은 건드리지 않고, 여기서만 측별 INDIConfig 와
G 봉투(paper.md §0: 교범 해석 "manual")를 주입한다. 봉투는 양측 동일.

    python research/indi/runner.py                       # 스모크: 기준 vs 기준
    python research/indi/runner.py --k_q 14 --k_ff 1     # blue 만 변경
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aircombat.control.indi import INDIConfig, SensorConfig
from aircombat.engine.factory import load_policy, make_pilot
from aircombat.engine.match import Match
from aircombat.engine.scenarios import initial_conditions
from limits import attach

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENVELOPE = "manual"   # 연구 확정 기준 (paper.md §0)
MODEL = "f16fix"      # 연구용 수정 모델 — 롤→대칭 양력 결함 제거 (plan.md 9/25, 사용자 결정)
# Nz 보호 끔: 원본 모델의 10.7G 초과는 전부 롤→양력 결함 탓이었고, f16fix 에선 보호 없이
# 60기체·경기 초과 0(최대 7.83G). 켜면 튜닝 제어기의 오버슈트를 가려 한계 준수 판정이 흐려진다.
NZ_PROTECT: dict | None = None
NOMINAL_SIGMA_DPS = 0.1   # 명목 자이로 잡음 (paper.md §0, §8-C: 실기 ≈0.055°/s 환산의 약 2배)

# Dogfight 배터리 — blue 트리 고정, red = 대항군 5종(전부 기준 INDI), 시나리오 5종 × 시드.
BLUE_TREE = os.path.join(ROOT, "examples", "energy_fighter.yaml")
REDS = ("red_adaptive", "red_extender", "red_phangman", "red_prime", "red_reactive")
SCENS = ("headon", "perch_offense", "perch_defense", "neutral", "p1_neutral")


def battery(seeds=(1, 2), reds=REDS, scens=SCENS) -> list[tuple[str, str, int]]:
    return [(r, sc, sd) for r in reds for sc in scens for sd in seeds]


def _apply_cond(pilot, cond: dict, seed: int) -> None:
    """평가 조건을 setup 직후에 적용(엔진 무수정).
    g0_scale      : 식별 G0 × s — 효과행렬 오차 (논문 2·5: ±30%)
    turb_severity : JSBSim MIL-SPEC(Dryden) 난류 강도 1–7 (논문 5), 측별 시드 고정"""
    setup = pilot.setup

    def wrapped():
        setup()
        if cond.get("g0_scale", 1.0) != 1.0:
            pilot.indi.G0 = pilot.indi.G0 * float(cond["g0_scale"])
        sev = cond.get("turb_severity", 0)
        if sev:
            f = pilot.plant
            f["atmosphere/randomseed"] = int(seed) * 2 + (pilot.color == "Red")
            f["atmosphere/turb-type"] = 3
            f["atmosphere/turbulence/milspec/windspeed_at_20ft_AGL-fps"] = 30.0
            f["atmosphere/turbulence/milspec/severity"] = int(sev)
        return pilot
    pilot.setup = wrapped


def pmap(fn, jobs, workers: int = 7):
    """순서 보존 병렬 map (Windows spawn — fn 은 모듈 최상위 함수여야 함)."""
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(workers) as ex:
        return list(ex.map(fn, jobs))


def game(job) -> dict:
    """pmap 용 1경기: job = (blue_cfg_dict, red, scenario, seed, cond_dict, sigma_dps, delay_ticks).
    잡음 시드 = 경기 시드 → 같은 (red, scen, seed) 는 config 가 달라도 같은 잡음열(대응 비교)."""
    cfg, red, sc, sd, cond, sigma, delay = job
    r = play(BLUE_TREE, os.path.join(ROOT, "redteams", f"{red}.yaml"), sc, sd,
             blue_cfg=INDIConfig(**cfg), sensor=SensorConfig("gyro", sigma, delay, sd), cond=cond)
    r["red"] = red
    return r


def play(blue_yaml: str, red_yaml: str, scenario: str = "headon", seed: int | None = None,
         blue_cfg: INDIConfig | None = None, red_cfg: INDIConfig | None = None,
         duration_s: float = 300.0, envelope: str = ENVELOPE,
         sensor: SensorConfig | None = None, nz_protect: dict | None = NZ_PROTECT,
         model: str = MODEL, cond: dict | None = None) -> dict:
    """1경기 → 결과 dict (JSON 직렬화 가능). 참가자 DQ 개념 없음 — 예외는 그대로 전파.
    봉투·센서·Nz 보호는 평가 조건이라 양측 동일(잡음열만 측별로 다름).
    nz_protect: None = 끔, dict = LimiterConfig nz_* 필드 오버라이드({} = 기본값으로 켬)."""
    ic = initial_conditions(scenario, seed=seed)
    blue = make_pilot("Blue", ic["blue"], *load_policy(blue_yaml),
                      indi_cfg=blue_cfg, envelope=envelope, sensor_cfg=sensor, model=model)
    red = make_pilot("Red", ic["red"], *load_policy(red_yaml),
                     indi_cfg=red_cfg, envelope=envelope, sensor_cfg=sensor, model=model)
    if nz_protect is not None:
        for pl in (blue, red):
            pl.limiter.cfg = dataclasses.replace(pl.limiter.cfg, nz_protect=True, **nz_protect)
    for pl in (blue, red):
        _apply_cond(pl, cond or {}, seed or 0)
    mon = {"blue": attach(blue), "red": attach(red)}
    r = Match(blue, red, duration_s=duration_s, log_hz=0.0).run()
    wez = r.wez_time or {"blue": 0.0, "red": 0.0}
    ata = r.ata_mean or {"blue": 0.0, "red": 0.0}
    return dict(scenario=scenario, seed=seed, envelope=envelope, model=model,
                sensor=dataclasses.asdict(sensor or SensorConfig()), nz_protect=nz_protect, cond=cond or {},
                blue_cfg=dataclasses.asdict(blue_cfg or INDIConfig()),
                red_cfg=dataclasses.asdict(red_cfg or INDIConfig()),
                winner=r.winner, condition=r.condition, time_s=r.time_s,
                hp_blue=r.hp_blue, hp_red=r.hp_red,
                wez_blue=wez["blue"], wez_red=wez["red"],
                ata_blue=ata["blue"], ata_red=ata["red"],
                limits_blue=mon["blue"].summary(), limits_red=mon["red"].summary())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blue", default=os.path.join(ROOT, "examples", "energy_fighter.yaml"))
    ap.add_argument("--red", default=os.path.join(ROOT, "redteams", "red_textbook.yaml"))
    ap.add_argument("--scenario", default="headon")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--envelope", default=ENVELOPE, choices=("platform", "manual"))
    ap.add_argument("--sensor", default="truth", choices=("truth", "gyro"))
    ap.add_argument("--gyro_sigma_dps", type=float, default=SensorConfig.gyro_sigma_dps)
    ap.add_argument("--delay_ticks", type=int, default=0)
    for f in dataclasses.fields(INDIConfig):       # blue 측 노브: --k_p 12 ...
        ap.add_argument(f"--{f.name}", type=float, default=f.default)
    a = ap.parse_args()
    cfg = INDIConfig(**{f.name: getattr(a, f.name) for f in dataclasses.fields(INDIConfig)})
    print(play(a.blue, a.red, a.scenario, a.seed, blue_cfg=cfg,
               duration_s=a.duration, envelope=a.envelope,
               sensor=SensorConfig(a.sensor, a.gyro_sigma_dps, a.delay_ticks, a.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
