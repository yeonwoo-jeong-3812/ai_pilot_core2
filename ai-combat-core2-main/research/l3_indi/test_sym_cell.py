"""대칭 칸(indi_side="both") 점검 — 개정 A35 §7.

적군에도 같은 설정으로 INDI 가 재생성되는지, 청군 전용 칸은 그대로인지 본다.
사용: python research/l3_indi/test_sym_cell.py   (경기 3 판, 약 15 초)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l3_indi import dogfight as D  # noqa: E402


def run(name: str, calls: list) -> None:
    grid = D.load_grid()
    job = [j for j in D.build_jobs(grid, [name], n_salts=1, salt_offset=8)
           if j["red"] == grid["battery"]["reds"][0] and j["scenario"] == "headon"][0]
    calls.clear()
    D.play(job)


def main() -> int:
    calls = []
    orig = D.rebuild_indi
    D.rebuild_indi = lambda p, st, ns: (calls.append((st.lam_q, ns)), orig(p, st, ns))[1]

    run("BASE", calls)
    assert len(calls) == 1, f"기준은 청군에만 주입해야 한다: {calls}"

    run("V3_lam_25", calls)
    assert len(calls) == 1, f"indi_side='blue' 는 청군에만 주입해야 한다: {calls}"
    assert calls[0][0] == 25.0

    run("SYM_lam_25", calls)
    assert len(calls) == 2, f"indi_side='both' 는 양측에 주입해야 한다: {calls}"
    assert calls[0][0] == calls[1][0] == 25.0, f"양측 λ 가 같아야 한다: {calls}"
    assert calls[1][1] == calls[0][1] ^ 0x5F5E0FF, f"적군 잡음 시드는 청군과 달라야 한다: {calls}"

    try:
        D.Setting.from_dict({"indi_side": "red"})
    except ValueError:
        pass
    else:
        raise AssertionError("indi_side 검증이 없다")

    print("PASS 4/4 — 대칭 칸 점검")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
