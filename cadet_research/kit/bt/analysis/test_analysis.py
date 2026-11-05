"""분석 코드 시험 (TASK_A·TASK_B 완료 기준). 합성 데이터 (fixtures/synth.py) 와 정답으로 확인한다.

  python bt/analysis/test_analysis.py         # cadet_research/kit/ 에서 (pytest 로도 돈다). 수 분
"""
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import anova  # noqa: E402
import confirm  # noqa: E402
import morris  # noqa: E402
import surrogate  # noqa: E402
from fixtures import synth  # noqa: E402

TMP = tempfile.mkdtemp()
DESIGN = os.path.join(KIT, "bt", "thetas", "main_morris_r16.csv")
LHS = os.path.join(KIT, "bt", "thetas", "main_lhs64.csv")


def _data(name):
    p = os.path.join(TMP, f"{name}.csv")
    if not os.path.exists(p):
        getattr(synth, name)(p)
    return anova.load(p)


def test_anova_recovers_truth_and_balance():
    df = _data("rq1")
    e = anova.eta2(df)
    assert all(abs(e[k] - v) < synth.TRUTH_RQ1["tolerance"] for k, v in synth.TRUTH_RQ1["eta2"].items()), e
    b1 = anova.eta2_bootstrap(df, n_boot=200)
    assert (b1.ci_lo <= b1.eta2 + 1e-12).all() and (b1.eta2 <= b1.ci_hi + 1e-12).all()
    assert b1.equals(anova.eta2_bootstrap(df, n_boot=200))
    for bad in (df.drop(df.index[5]), df.iloc[list(range(len(df))) + [7]]):       # 빠진 칸, 겹친 칸
        try:
            anova.eta2(bad)
        except ValueError as ex:
            assert str(df.iloc[5 if len(bad) < len(df) else 7].theta_id) in str(ex)
            continue
        raise AssertionError("균형 검사 실패")
    rng = np.random.default_rng(3)
    rs = anova.resample_thetas(df, rng)
    assert rs.theta_id.nunique() == 64 and (rs.groupby("theta_id").size() == 48).all()
    anova.check_balance(rs)
    orig = rs.theta_id.str.split("#").str[0]
    assert orig.nunique() < 64                                                   # 중복 추출이 실제로 있다
    assert rs.theta_id.nunique() - 1 == 63                                       # θ 자유도 63


def test_anova_pilot_sample_cli():
    df = anova.load(os.path.join(HERE, "fixtures", "pilot2_sample.csv"))
    e = anova.eta2(df)
    assert abs(sum(e.values()) - 1) < 1e-9


def test_confirm_truth():
    df = _data("confirm")
    th = synth.confirm_thetas()
    import make_tree as mt
    ids = {mt.theta_id(t): n for n, t in th.items()}
    base = next(i for i, n in ids.items() if n == "baseline")
    t = confirm.compare(df, base)
    for r in t.itertuples():
        c = synth.TRUTH_CONFIRM["candidates"][ids[r.theta_id]]
        assert abs(r.mean - c["delta"]) < 1e-9
        assert (bool(r.better), bool(r.practically_better), bool(r.equivalent)) == (c["better"], c["practically_better"], c["equivalent"]), (ids[r.theta_id], r)
        assert abs(r.ci_lo - c["ci95"][0]) < 1e-3 and abs(r.ci_hi - c["ci95"][1]) < 1e-3
        assert round(r.p_one_sided, 3) == round(c["p_one_sided"], 3) or r.p_one_sided < 1e-10
    try:
        confirm.compare(df.drop(df[df.theta_id != base].index[0]), base)
    except ValueError:
        pass
    else:
        raise AssertionError("짝 불일치 검사 실패")


def test_morris_new_rule():
    df = _data("morris_null")
    r = morris.analyze(df, DESIGN)
    T = synth.TRUTH_MORRIS_NULL
    assert all(r["important"][p] for p in T["important"]) and not any(r["important"][p] for p in T["not_important"]), r["table"]
    assert r["dummy_exact_zero"] and (r["table"].loc["dummy", ["mu_star", "mu", "sigma", "mu_star_lo", "mu_star_hi", "noise_floor"]] == 0).all()
    ee = morris.elementary_effects(r["steps"])
    assert len(ee) == 176
    g = morris.geometry_compare(df, DESIGN)
    pr = g["pairs"]
    assert pr[(pr.param == "floor_ft")].differs.any()
    assert not pr[(pr.param == "fight_kcas")].differs.any()
    assert morris.noise_floor(r["steps"], 50) == morris.noise_floor(r["steps"], 50)


def test_morris_indices_old_data():
    df = _data("morris")
    t = morris.analyze(df, DESIGN)["table"]
    for p, v in synth.TRUTH_MORRIS["mu_star"].items():
        assert abs(t.mu_star[p] - v) < 0.4, (p, t.mu_star[p])
    assert t.sigma["threat_aspect_deg"] > t.sigma["fight_kcas"]


def test_surrogate_holdout():
    df = _data("surrogate")
    tt = surrogate.theta_table(df, [LHS, DESIGN])
    assert len(tt) == 256
    fit = surrogate.fit_holdout(tt)
    assert len(fit["test_ids"]) == 49 and len(fit["train_ids"]) == 207
    assert set(fit["test_trajectories"]) == synth.TRUTH_SURROGATE["holdout_trajectory_ids"]
    m = tt[tt.design == "morris"]
    assert all(m[m.trajectory == t].theta_id.isin(fit["test_ids"]).nunique() == 1 for t in range(16))
    lhs_ids = list(tt[tt.design == "lhs"].theta_id)
    mor = tt[tt.design == "morris"]
    hold, _ = synth.holdout_ids(lhs_ids, list(mor.theta_id), list(mor.trajectory.astype(int)))
    assert set(fit["test_ids"]) == hold
    assert fit["r2_holdout"] >= 0.5 and abs(fit["r2_holdout"] - surrogate.fit_holdout(tt)["r2_holdout"]) < 1e-12
    out = tempfile.mkdtemp(dir=TMP)
    assert surrogate.shap_report(fit, tt, out) and os.path.exists(os.path.join(out, "surrogate_shap.csv"))
    tt2 = tt.assign(y=np.random.default_rng(1).normal(size=len(tt)))
    f2 = surrogate.fit_holdout(tt2)
    out2 = tempfile.mkdtemp(dir=TMP)
    assert f2["r2_holdout"] < 0.5 and not surrogate.shap_report(f2, tt2, out2) and not os.listdir(out2)


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn()
                print("[ok]", name, flush=True)
        print("분석 시험 통과")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
