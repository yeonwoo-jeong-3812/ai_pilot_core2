"""분류기 정답 검증 — 해석적으로 합성한 기동에 올바른 이름을 붙이는가.

실제 녹화에는 정답 라벨이 없다. 그래서 **모양을 아는 궤적을 직접 만들어** 분류기에
먹인다. 정탐만 보는 게 아니라 **오탐**을 특히 본다 — 수평선회를 임멜만이라 부르면
논문의 중심 수치가 통째로 무너지기 때문이다.

합성은 자세각 시계열(t, pitch, roll, yaw, alt)만 만든다. 분류기가 자세각만 쓰므로
비행역학을 모사할 필요가 없고, 오히려 역학을 섞지 않아야 판정 기준만 고립해서 볼 수 있다.

실행: pytest research/test_bfm_taxonomy.py -v
"""
from __future__ import annotations

import numpy as np
import pytest

from research import bfm_taxonomy as bt

HZ = 120.0


def _mk(dur_s, pitch, roll, yaw, alt, t0=0.0):
    """구간 하나를 만든다. 각 인자는 0..1 정규화 시간을 받는 함수 또는 상수."""
    n = max(2, int(dur_s * HZ))
    u = np.linspace(0.0, 1.0, n)
    f = lambda x: np.full(n, float(x)) if np.isscalar(x) else np.asarray(x(u), float)  # noqa: E731
    return (t0 + u * dur_s, f(pitch), f(roll), f(yaw), f(alt))


def _cat(*segs):
    """구간들을 시간축으로 이어붙인다."""
    t, th, ro, ya, al = [], [], [], [], []
    off = 0.0
    for s in segs:
        t.append(s[0] + off)
        th.append(s[1]); ro.append(s[2]); ya.append(s[3]); al.append(s[4])
        off += s[0][-1] + 1.0 / HZ
    return tuple(np.concatenate(x) for x in (t, th, ro, ya, al))


def _classify(series, **kw):
    """분류기의 판정부만 호출 (파일 I/O 우회)."""
    return bt.classify_series(series, **kw)


def _cruise(dur, yaw=0.0, alt=15000.0):
    return _mk(dur, 0.0, 0.0, yaw, alt)


def _half_loop_up(dur=9.0, alt0=15000.0, gain=6000.0, yaw0=0.0):
    """임멜만의 상승 반원 — 오일러 표현.

    피치 90°는 오일러 각의 특이점이라, 기수가 정상을 넘는 순간 **요와 롤이 동시에
    180° 뒤집힌다**. 실제 녹화도 이렇게 찍히므로 합성도 그 물리를 따라야 한다.
    (앞선 합성은 배면 전환을 정상보다 뒤로 미뤄 놨었고, 그래서 물리적으로 틀렸다.)
    상승 반원 뒤에 정립 복귀 반롤을 붙이면 임멜만이 완성된다.
    """
    up = _mk(dur,
             lambda u: 85.0 * np.sin(np.pi * np.clip(u / 0.9, 0, 1)),  # 0→85→0
             lambda u: np.where(u < 0.45, 0.0, 180.0),                 # 정상에서 배면
             lambda u: np.where(u < 0.45, yaw0, yaw0 + 180.0),         # 요도 동시 반전
             lambda u: alt0 + gain * np.clip(u / 0.9, 0, 1))
    roll_out = _mk(2.0, 0.0, lambda u: 180.0 - 180.0 * u,
                   yaw0 + 180.0, alt0 + gain)
    return up, roll_out


# ── 정탐: 교범 기동 ────────────────────────────────────────────────────────

def test_immelmann():
    """상승 반원 + 정상 반롤 → 방위 180° 반전, 고도 획득, 정립 이탈."""
    seq = _cat(_cruise(6.0), *_half_loop_up(), _cruise(6.0, yaw=180.0, alt=21000.0))
    kinds = [e["kind"] for e in _classify(seq)]
    assert kinds.count("임멜만") == 1, f"임멜만 1회여야 하는데 {kinds}"


def test_split_s():
    """반롤 + 하강 반원 → 방위 반전, 고도 상실."""
    seq = _cat(
        _cruise(6.0, alt=21000.0),
        _mk(2.0, 0.0, lambda u: 180 * u, 0.0, 21000.0),          # 배면으로 롤
        _mk(8.0, lambda u: -90 * np.sin(np.pi * u),               # 기수 아래로 반원
            lambda u: np.where(u < .8, 180.0, 0.0),
            lambda u: 180 * u, lambda u: 21000 - 6000 * u),
        _cruise(6.0, yaw=180.0, alt=15000.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert kinds.count("스플릿S") == 1, f"스플릿S 1회여야 하는데 {kinds}"


def test_loop():
    """수직면 360° — 방위·고도 모두 제자리로 복귀.

    오일러 표현에 주의: 피치는 ±90°를 넘지 못한다. 실제 루프는
    θ: 0→+85→0→−85→0 이고, 정상과 바닥에서 φ·ψ 가 180° 씩 뒤집힌다.
    (앞선 합성은 θ 를 180°까지 올려 오일러 각으로 불가능한 궤적이었다.)
    """
    q = 2.5   # 사분면당 초
    seq = _cat(
        _cruise(6.0),
        _mk(q, lambda u: 85 * u, 0.0, 0.0, lambda u: 15000 + 1500 * u),
        _mk(q, lambda u: 85 * (1 - u), 180.0, 180.0, lambda u: 16500 + 1500 * u),
        _mk(q, lambda u: -85 * u, 180.0, 180.0, lambda u: 18000 - 1500 * u),
        _mk(q, lambda u: -85 * (1 - u), 0.0, 360.0, lambda u: 16500 - 1500 * u),
        _cruise(6.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert "루프" in kinds, f"루프가 검출돼야 하는데 {kinds}"


def test_high_yoyo_is_not_inverted_maneuver():
    """하이 요요 — 배면 없이 기수만 올렸다 내림. 임멜만/스플릿S 로 불리면 안 된다."""
    seq = _cat(
        _cruise(5.0),
        _mk(8.0, lambda u: 75 * np.sin(np.pi * u), 45.0,
            lambda u: 40 * u, lambda u: 15000 + 3000 * np.sin(np.pi * u)),
        _cruise(5.0, yaw=40.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert "임멜만" not in kinds and "스플릿S" not in kinds, kinds
    assert "급상승" in kinds, f"급상승이어야 하는데 {kinds}"


# ── 오탐: 기동이 아닌 것 ──────────────────────────────────────────────────

def test_level_turn_not_detected():
    """고G 수평선회 180°. 뱅크 80°, 기수 살짝 위 — 절대 임멜만이 아니다."""
    seq = _cat(
        _cruise(5.0),
        _mk(12.0, 8.0, 80.0, lambda u: 180 * u, 15000.0),
        _cruise(5.0, yaw=180.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert not kinds, f"수평선회는 아무것도 검출되면 안 되는데 {kinds}"


def test_steep_bank_turn_with_climb_not_immelmann():
    """급뱅크 상승선회 — 방위 180° 반전 + 고도 획득. 임멜만과 결과가 같지만
    기수가 수직을 통과하지 않으므로 임멜만이 아니다. 가장 위험한 오탐 후보."""
    seq = _cat(
        _cruise(5.0),
        _mk(14.0, 25.0, 85.0, lambda u: 180 * u, lambda u: 15000 + 6000 * u),
        _cruise(5.0, yaw=180.0, alt=21000.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert "임멜만" not in kinds, f"급뱅크 상승선회를 임멜만으로 오판: {kinds}"


def test_level_cruise_silent():
    """직진 순항에서는 아무것도 안 나와야 한다."""
    assert not _classify(_cruise(60.0))


def test_knife_edge_not_inverted():
    """나이프에지(뱅크 90°) — 배면이 아니다. INVERT_DEG 경계 확인."""
    seq = _cat(
        _cruise(5.0),
        _mk(10.0, lambda u: 70 * np.sin(np.pi * u), 90.0, 0.0,
            lambda u: 15000 + 2000 * np.sin(np.pi * u)),
        _cruise(5.0),
    )
    kinds = [e["kind"] for e in _classify(seq)]
    assert "임멜만" not in kinds and "루프" not in kinds, kinds


# ── 강건성 ────────────────────────────────────────────────────────────────

def test_label_stable_under_threshold_perturbation():
    """임계값을 흔들어도 임멜만 판정이 유지되는가 — 손튜닝 의존성 점검."""
    seq = _cat(_cruise(6.0), *_half_loop_up(), _cruise(6.0, yaw=180.0, alt=21000.0))
    for kw in ({"vert": 50.0}, {"vert": 70.0}, {"turn_tol": 30.0},
               {"turn_tol": 60.0}, {"alt_tol": 300.0}, {"alt_tol": 1000.0},
               {"invert_up": -0.3}, {"invert_up": -0.7}, {"invert_s": 0.1},
               {"invert_s": 0.6}):
        kinds = [e["kind"] for e in _classify(seq, **kw)]
        assert "임멜만" in kinds, f"{kw} 에서 임멜만을 놓침: {kinds}"


def test_duplicate_timestamps_survive():
    """녹화에 같은 시각이 여러 번 찍혀도 판정이 흔들리면 안 된다(실측 결함)."""
    t, th, ro, ya, al = _cat(_cruise(6.0), *_half_loop_up(),
                             _cruise(6.0, yaw=180.0, alt=21000.0))
    t2 = t.copy()
    t2[1::7] = t2[0::7][:len(t2[1::7])]        # 인위적 중복 주입
    clean = [e["kind"] for e in _classify((t, th, ro, ya, al))]
    dirty = [e["kind"] for e in _classify((t2, th, ro, ya, al))]
    assert clean == dirty, f"중복 타임스탬프로 판정이 바뀜: {clean} vs {dirty}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
