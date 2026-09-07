"""SDK 소스 배포판 빌드 — 사설 저장소(core2) → 참가자 배포 산출물.

올해는 내부 대회 → 소스 배포(D5 확정): Cython 없이 **필터-복사 + 레퍼런스 자동
생성 + 버전/엔진커밋 스탬프**. 미배포 자산(bridge/tests/tmp/redteams/내부 스크립트)은
복사 대상에서 제외하고, 빌드 말미에 FORBIDDEN 검사로 이중 차단한다.

사용:
    python scripts/build_sdk.py                      # → ../ai-combat-sdk2
    python scripts/build_sdk.py --output DIR --version 0.2.0
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
import gen_references  # noqa: E402

# 디렉토리 통복사 (원본 → 산출물). __pycache__/*.pyc 는 항상 제외.
COPY_TREES = [
    ("aircombat", "aircombat"),
    ("config", "config"),           # 엔진 전용: sim.yaml · tactics.yaml(기본트리)
    ("examples", "examples"),       # 아키타입 참조 (스파링 상대)
    ("jsbsim_data", "jsbsim_data"),
    ("sdk/tools", "tools"),
    ("sdk/docs", "docs"),            # RULEBOOK · MEASURED_BEHAVIOR (REFERENCE 는 자동 생성)
    ("sdk/.vscode", ".vscode"),      # YAML 스키마 자동 적용 + 확장 추천
    ("tools/acmi_viewer", "tools/acmi_viewer"),   # run_match --view (Tacview 없이 브라우저 복기)
]
COPY_FILES = [
    ("scripts/run_match.py", "scripts/run_match.py"),
    ("scripts/analyze_wez.py", "scripts/analyze_wez.py"),   # run_match --analyze 의존
    ("sdk/requirements.txt", "requirements.txt"),           # 참가자 런타임 서브셋(research 제외)
    ("sdk/sdk.gitignore", ".gitignore"),
    ("LICENSE", "LICENSE"),
]
# 복사 트리 안에서 추가 제외할 상대경로 (서버 전용 어댑터)
# tournament 은 bridge 를 import 하는 운영자 도구 — 배포되면 import 조차 실패한다.
TREE_EXCLUDES = {"aircombat/bridge.py", "aircombat/engine/tournament.py"}
# 산출물에 존재하면 빌드 실패 처리 (미배포 자산 이중 차단)
FORBIDDEN = ["aircombat/bridge.py", "aircombat/engine/tournament.py",
             "tests", "tmp", "redteams", "lab",
             "scripts/build_sdk.py", "scripts/gen_references.py",
             "scripts/verify_bridge.py", "docs/ARCHITECTURE.md"]


def _clean_output(out: str) -> None:
    """산출물 정리 — .git/.venv 는 보존 (V1 build_sdk 관행)."""
    if not os.path.isdir(out):
        os.makedirs(out)
        return
    for item in os.listdir(out):
        if item in (".git", ".venv"):
            continue
        path = os.path.join(out, item)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)


def _copy_tree(src: str, dst: str, rel_prefix: str) -> int:
    n = 0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".pyc"):
                continue
            sp = os.path.join(dirpath, fn)
            rel = os.path.relpath(sp, src).replace("\\", "/")
            if f"{rel_prefix}/{rel}" in TREE_EXCLUDES:
                continue
            dp = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copy2(sp, dp)
            n += 1
    return n


def _pyd_exists(py_path: str) -> bool:
    """py_path 옆에 대응 확장모듈(<stem>.<abi>.pyd)이 있는가."""
    d, stem = os.path.dirname(py_path), os.path.basename(py_path)[:-3]
    return any(f.startswith(stem + ".") and f.endswith(".pyd") for f in os.listdir(d))


def _leaked(out: str, rel: str) -> bool:
    """미배포 자산이 산출물에 남았는가.

    --compile 릴리스에선 .py 가 .pyd 로 바뀌어 경로 존재 검사만으로는 유출을 놓친다
    (실제로 engine/tournament 이 그렇게 sdk2 로 새어 나갔다). 확장모듈도 함께 본다.
    """
    p = os.path.join(out, rel)
    if os.path.exists(p):
        return True
    return rel.endswith(".py") and os.path.isdir(os.path.dirname(p)) and _pyd_exists(p)


def _compile_aircombat(out: str) -> None:
    """산출물의 aircombat/*.py → .pyd (소스 미배포). 릴리스 전용.

    빈 __init__.py 는 패키지 초기화용으로 소스 유지(로직 없음). 나머지 .py 는
    Cython 으로 .pyd 컴파일 후 .py/.c 를 제거해 소스를 남기지 않는다.
    Cython + C 컴파일러(Windows=MSVC, setuptools 가 자동 탐지) 필요.
    """
    try:
        from Cython.Build import cythonize
        from setuptools import Extension, setup
    except ImportError as exc:
        raise SystemExit(f"❌ --compile 빌드 의존성 누락({exc.name}): "
                         "pip install cython setuptools")

    pkg = os.path.join(out, "aircombat")
    py_files, exts = [], []
    for dirpath, dirnames, filenames in os.walk(pkg):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py") or fn == "__init__.py":
                continue
            sp = os.path.join(dirpath, fn)
            modname = os.path.relpath(sp, out)[:-3].replace(os.sep, ".").replace("/", ".")
            py_files.append(sp)
            exts.append(Extension(modname, [sp]))

    cwd = os.getcwd()
    os.chdir(out)   # build_ext --inplace 기준 디렉토리 = 산출물 루트
    try:
        setup(name="aircombat_compiled",
              ext_modules=cythonize(exts, language_level="3", quiet=True,
                                    compiler_directives={"emit_code_comments": False}),
              script_args=["build_ext", "--inplace"])
    finally:
        os.chdir(cwd)

    for sp in py_files:                       # 소스/중간산출물 제거 — .pyd 만 남김
        for f in (sp, sp[:-3] + ".c"):
            if os.path.exists(f):
                os.remove(f)
    shutil.rmtree(os.path.join(out, "build"), ignore_errors=True)

    missing = [os.path.relpath(sp, out) for sp in py_files if not _pyd_exists(sp)]
    if missing:
        raise SystemExit(f"❌ 컴파일 누락(.pyd 없음): {missing}")
    print(f"  aircombat 컴파일 → .pyd {len(py_files)}개 (소스 제거)")


def _engine_commit() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return f"{rev}-dirty" if dirty else rev   # 감사: 미커밋 상태 빌드를 구분
    except Exception:
        return "unknown"


def build(output: str, version: str, allow_dirty: bool = False,
          compile_engine: bool = False) -> int:
    commit = _engine_commit()
    if commit.endswith("-dirty") and not allow_dirty:
        print(f"❌ 빌드 거부 — 워킹트리가 dirty({commit}). 커밋 후 빌드하거나 --allow-dirty 사용.")
        print("   (metadata.json 의 engine_commit 이 매치 재현·감사 기준이라 dirty 릴리스 금지)")
        return 1

    out = os.path.abspath(output)
    print(f"SDK 빌드: {ROOT} → {out}  (version {version})")
    _clean_output(out)

    total = 0
    for src_rel, dst_rel in COPY_TREES:
        src = os.path.join(ROOT, src_rel)
        if not os.path.isdir(src):
            print(f"  (건너뜀 — 없음: {src_rel})")
            continue
        n = _copy_tree(src, os.path.join(out, dst_rel), src_rel)
        print(f"  {src_rel:<14} → {dst_rel:<10} {n:4d} 파일")
        total += n
    for src_rel, dst_rel in COPY_FILES:
        src = os.path.join(ROOT, src_rel)
        dp = os.path.join(out, dst_rel)
        os.makedirs(os.path.dirname(dp) or out, exist_ok=True)
        shutil.copy2(src, dp)
        total += 1

    # aircombat 소스 보호 — .pyd 컴파일 (릴리스). 미지정 시 소스 노출 경고.
    if compile_engine:
        _compile_aircombat(out)
    else:
        print("  ⚠ --compile 미지정 — 산출물에 aircombat 소스(.py)가 그대로 포함됨(개발용).")

    # README — 버전 스탬프
    with open(os.path.join(ROOT, "sdk", "README.md"), encoding="utf-8") as f:
        readme = f.read().replace("{{SDK_VERSION}}", version)
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(readme)

    # 레퍼런스 자동 생성 — 코드가 단일 진실, 문서 드리프트 구조적 차단
    refs = gen_references.write_all(os.path.join(out, "docs"))
    print(f"  레퍼런스 자동 생성 → docs/ ({', '.join(os.path.basename(p) for p in refs)})")

    # 작업 디렉토리 — my_agents/ = 참가자 에이전트 여러 버전 (구 submissions/·agents/)
    os.makedirs(os.path.join(out, "my_agents"), exist_ok=True)
    os.makedirs(os.path.join(out, "replays"), exist_ok=True)
    open(os.path.join(out, "my_agents", ".gitkeep"), "w").close()

    # 메타데이터 — 매치 레코드 감사용 엔진 커밋 고정
    meta = {"sdk_version": version, "engine_commit": commit,
            "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with open(os.path.join(out, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # 미배포 자산 이중 차단
    leaked = [p for p in FORBIDDEN if _leaked(out, p)]
    if leaked:
        print(f"❌ 빌드 실패 — 미배포 자산 유출: {leaked}")
        return 1

    print(f"✅ 빌드 완료: 파일 {total}개 + 레퍼런스 {len(refs)}건, "
          f"engine_commit={meta['engine_commit']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=os.path.join(ROOT, "..", "ai-combat-sdk2"))
    ap.add_argument("--version", default="0.1.0-dev")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="dirty 워킹트리 빌드 허용 (개발용 — 릴리스 금지)")
    ap.add_argument("--compile", action="store_true", dest="compile_engine",
                    help="aircombat 을 .pyd 로 컴파일하고 소스 제거 (릴리스 배포용, Cython 필요)")
    args = ap.parse_args()
    return build(args.output, args.version, allow_dirty=args.allow_dirty,
                 compile_engine=args.compile_engine)


if __name__ == "__main__":
    raise SystemExit(main())
