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


def test_tuning_report():
    """win_test 의 McNemar·CI·TOST 와 tuning.py 끝까지 실행 (합성 승패, 정답: V2 만 V0 보다 높고 나머지는 V0 와 같다)."""
    import pandas as pd
    import tuning
    d = np.array([1] * 30 + [-1] * 10 + [0] * 60)
    r = tuning.win_test(d)
    assert np.isclose(r["diff"], 0.2) and (r["b"], r["c"]) == (30, 10)
    from math import comb
    assert np.isclose(r["p_mcnemar"], 2 * sum(comb(40, k) for k in range(30, 41)) / 2 ** 40)     # 양측 정확 이항
    assert tuning.win_test(np.zeros(100))["p_tost"] == 0.0
    var = tuning.read_design(tuning.VARIANTS)
    paths = {}
    for s, opps in (("patched", ["A", "B", "C", "D"]), ("heldout", ["E", "F", "G", "H"])):
        rows = []
        for v, tid in zip(var.variant, var.theta_id):
            for sc in ("g1", "g2", "g3"):
                for o in opps:
                    for k in range(36):
                        u = ((37 * k + 11 * ord(o) + 7 * int(sc[1])) % 100) / 100     # 셀마다 같은 값 → V2 외 변형은 V0 와 똑같다
                        p = 0.0 if o in ("D", "H") else 0.4 + (0.25 if v == "V2" else 0.0)
                        win = u < p
                        rows.append(dict(theta_id=tid, scenario=sc, opponent=o, opponent_set=s, seed_salt=f"x-{k}",
                                         winner="blue" if win else "red", end_reason="health_zero", win_mode="shootdown" if win else "",
                                         wez_blue=1.0 * win, wez_red=1.0 - win, hp_blue_raw=100.0, hp_red_raw=100.0 - 50 * win,
                                         e_adv_ft=0.0, node_frac='{"energy_recover": 0.5, "break_defense": 0.5}',
                                         code_commit="abc", engine_sha="1e0101026959"))
        paths[s] = os.path.join(TMP, f"tuning_{s}.csv")
        pd.DataFrame(rows).to_csv(paths[s], index=False)
    out = tempfile.mkdtemp(dir=TMP)
    argv = sys.argv
    sys.argv = ["tuning.py", "--patched", paths["patched"], "--heldout", paths["heldout"], "--out", out]
    try:
        tuning.main()
    finally:
        sys.argv = argv
    rep = open(os.path.join(out, "tuning_report.md"), encoding="utf-8").read()
    main_rows = [x for x in rep.split("## 2.")[0].splitlines() if x.startswith(("| patched |", "| heldout |"))]
    assert [x.split(" | ")[1] for x in main_rows if "**예**" in x] == ["V2", "V2"], main_rows
    assert "patched **동등**" in rep and "heldout **동등**" in rep
    assert "D †" in rep and "H †" in rep and "| patched | 2592 | 2592 | 0 | 0 | 0 | abc |" in rep
    assert os.path.exists(os.path.join(out, "tuning_winrate.png")) and os.path.exists(os.path.join(out, "tuning_nodefrac.png"))


def test_generalize_report():
    """판정 문장 4가지와 generalize.py 끝까지 실행 (합성: V2 승 증가, V3 패 → 무접촉, V6 은 V0 와 같다)."""
    import pandas as pd
    import generalize as g
    assert g.verdict(0.1, 0.01, -0.1, 0.01) == "일반화됨" and g.verdict(0.1, 0.01, 0.1, 0.01) == "일반화됨"
    assert g.verdict(-0.1, 0.01, -0.1, 0.01) == "악화" and g.verdict(0.0, 0.5, 0.1, 0.01) == "악화"
    assert g.verdict(0.01, 0.5, -0.1, 0.01) == "생존만 일반화됨" and g.verdict(0.01, 0.5, -0.01, 0.5) == "일반화 안 됨"
    var = g.read_design(g.VARIANTS)
    paths = {}
    for s, opps in (("patched", "ABCD"), ("heldout", "EFGH"), ("newtypes", "IJKLMN")):
        rows = []
        for v, tid in zip(var.variant, var.theta_id):
            for sc in ("g1", "g2", "g3"):
                for o in opps:
                    for k in range(36):
                        u = ((37 * k + 11 * ord(o) + 7 * int(sc[1])) % 100) / 100
                        win = u < (0.0 if o == "N" else 0.3 + (0.3 if v == "V2" else 0.0))
                        nc = (not win) and v == "V3" and u > 0.6
                        rows.append(dict(theta_id=tid, scenario=sc, opponent=o, opponent_set=s, seed_salt=f"x-{k}",
                                         winner="blue" if win else "draw" if nc else "red",
                                         end_reason="no_contact" if nc else "health_zero", win_mode="shootdown" if win else "",
                                         wez_blue=1.0 * win, wez_red=1.0 - win, hp_blue_raw=100.0, hp_red_raw=100.0 - 50 * win,
                                         e_adv_ft=0.0, node_frac='{"energy_recover": 0.5, "break_defense": 0.5}',
                                         code_commit="abc", engine_sha="1e0101026959"))
        paths[s] = os.path.join(TMP, f"gen_{s}.csv")
        pd.DataFrame(rows).to_csv(paths[s], index=False)
    out = tempfile.mkdtemp(dir=TMP)
    argv = sys.argv
    sys.argv = ["generalize.py", *[x for k, v in paths.items() for x in ("--" + k, v)], "--out", out]
    try:
        g.main()
    finally:
        sys.argv = argv
    rep = open(os.path.join(out, "generalize_report.md"), encoding="utf-8").read()
    assert "| V2 | **일반화됨** |" in rep and "| V3 | **생존만 일반화됨** |" in rep and "| V6 | **일반화 안 됨** |" in rep, rep[:1500]
    assert "N †" in rep and "| 2592 | 2592 | 0 | 0 | 0 | abc |" in rep
    assert os.path.exists(os.path.join(out, "generalize_diffs.png")) and os.path.exists(os.path.join(out, "generalize_outcomes.png"))


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                fn()
                print("[ok]", name, flush=True)
        print("분석 시험 통과")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
