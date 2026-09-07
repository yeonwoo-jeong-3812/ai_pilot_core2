"""공정3 스냅 생성기 — 증류트리(joblib) → 명시 분기 데이터(base_tree.json).

sklearn 트리의 (feature, threshold, left, right, leaf_class) 배열을 JSON 으로
내보낸다. 런타임은 이 데이터를 명시 순회(x[f] <= thr — sklearn 과 동일 비교)
하므로 joblib/sklearn 없이 비트-동일 판정이 성립한다(루프6 tier-C 계보).
threshold 는 json repr 왕복으로 double 이 보존된다.

검증: 무작위 20만 벡터 + 임계값-정확 벡터에서 원본 clf 와 리프 클래스 전수 일치.

usage: python -m research.gen_base_snap <out.json>
"""
from __future__ import annotations

import json
import sys

import numpy as np

sys.path.insert(0, ".")
from research import champion_core as C                       # noqa: E402
from research.transcribe import tree_leaf_class               # noqa: E402


def export(clf) -> dict:
    t = clf.tree_
    leaf = [-1] * t.node_count
    for n in range(t.node_count):
        if t.children_left[n] == t.children_right[n]:
            leaf[n] = int(t.value[n][0].argmax())
    return dict(classes=[str(c) for c in clf.classes_],
                n_features=int(t.n_features),
                feature=t.feature.tolist(),
                threshold=t.threshold.tolist(),
                left=t.children_left.tolist(),
                right=t.children_right.tolist(),
                leaf_class=leaf)


def walk(snap: dict, x) -> str:
    n = 0
    while snap["left"][n] != snap["right"][n]:
        n = (snap["left"][n] if x[snap["feature"][n]] <= snap["threshold"][n]
             else snap["right"][n])
    return snap["classes"][snap["leaf_class"][n]]


def verify(clf, snap: dict, n_random: int = 200_000) -> None:
    rng = np.random.default_rng(0)
    thr = np.array([v for v in snap["threshold"] if v != -2.0])
    lo, hi = float(thr.min()) - 1.0, float(thr.max()) + 1.0
    X = rng.uniform(lo, hi, size=(n_random, snap["n_features"]))
    # 임계값-정확 표본: 각 임계값을 해당 특징 위치에 그대로 심는다(경계 동치까지 검사)
    t = clf.tree_
    for n in range(t.node_count):
        if t.children_left[n] != t.children_right[n]:
            row = rng.uniform(lo, hi, size=snap["n_features"])
            row[t.feature[n]] = t.threshold[n]
            X = np.vstack([X, row])
    bad = 0
    for x in X:
        if tree_leaf_class(clf, x) != walk(snap, x):
            bad += 1
    assert bad == 0, f"스냅 불일치 {bad}/{len(X)}"
    print(f"검증 통과: {len(X):,} 벡터(임계값-정확 {t.node_count - len(thr)}종 포함) 전수 일치")


def main(out: str) -> None:
    clf = C.load_clf()
    snap = export(clf)
    verify(clf, snap)
    json.dump(snap, open(out, "w"))
    print(f"리프 {sum(1 for v in snap['leaf_class'] if v >= 0)} / 노드 "
          f"{len(snap['leaf_class'])} → {out}")


if __name__ == "__main__":
    main(sys.argv[1])
