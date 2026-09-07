# SDK 업데이트 가이드 - 사용자 파일 충돌 방지

## 📋 변경 사항 요약

SDK 구조를 개선하여 사용자가 생성한 파일과 SDK 업데이트 간의 Git 충돌을 방지했습니다.

### 주요 변경사항

1. **사용자 작업 공간 분리**
   - `submissions/` (커스텀 노드 포함), `tournament_data/` 폴더를 Git에서 제외
   - SDK 업데이트 시 사용자 파일이 손실되거나 충돌하지 않음

2. **템플릿 구조 제공**
   - `submissions/.gitkeep` 및 `submissions/README.md`만 버전 관리
   - 사용자가 생성한 에이전트 파일은 Git에서 추적하지 않음

3. **문서 개선**
   - SDK README에 "SDK 업데이트 및 사용자 파일 관리" 섹션 추가
   - 백업 권장사항 및 작업 공간 구조 명시

---

## 🔄 기존 사용자를 위한 마이그레이션 가이드

### 상황 1: 이미 SDK를 사용 중인 경우

```bash
# 1. 현재 작업물 백업
cd ai-combat-sdk
cp -r submissions/ ../submissions_backup/

# 2. SDK 업데이트
git stash  # 로컬 변경사항 임시 저장
git pull origin main

# 3. 백업한 파일 복원
cp -r ../submissions_backup/* submissions/

# 4. 정상 작동 확인
python scripts/run_match.py --agent1 my_agent --agent2 simple
```

### 상황 2: Git 충돌이 발생한 경우

```bash
# 1. 충돌 파일 확인
git status

# 2. submissions/ 폴더의 충돌 무시
git checkout --theirs submissions/README.md
git checkout --theirs submissions/.gitkeep

# 3. 나머지 충돌 해결 후 커밋
git add .
git commit -m "Merge SDK update"

# 4. 사용자 에이전트는 이제 Git에서 추적되지 않음
```

### 상황 3: 새로 시작하는 경우

```bash
# 1. SDK 클론
git clone https://github.com/rokafa-daslab/ai-combat-sdk.git
cd ai-combat-sdk

# 2. 가상환경 설정
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. 에이전트 개발
mkdir submissions/my_agent
# my_agent.yaml 작성

# 4. SDK 업데이트는 언제든지 안전
git pull origin main  # submissions/ 내용은 보존됨
```

---

## 📂 새로운 디렉토리 구조

```
ai-combat-sdk/
├── .gitignore                # 사용자 작업 공간 제외 패턴 추가
├── submissions/              # 🔒 Git에서 제외됨
│   ├── .gitkeep              # ✅ 폴더 유지용 (Git 추적)
│   ├── README.md             # ✅ 사용 가이드 (Git 추적)
│   └── my_agent/             # ❌ 사용자 파일 (Git 제외)
│       ├── my_agent.yaml
│       └── nodes/            # 커스텀 노드 (선택)
├── tournament_data/          # 🔒 Git에서 제외됨
│   └── .gitkeep              # ✅ 폴더 유지용 (Git 추적)
├── replays/                  # 🔒 Git에서 제외됨
├── examples/                 # ✅ SDK 제공 (Git 추적)
├── scripts/                  # ✅ SDK 제공 (Git 추적)
└── src/                      # ✅ SDK 엔진 (Git 추적)
```

---

## 🛠️ 개발자를 위한 빌드 가이드

### SDK 빌드 프로세스 변경사항

`build_sdk.py` 스크립트가 다음과 같이 개선되었습니다:

```python
# 기존: submissions/ 폴더 완전 제외
# 변경: submissions/ 템플릿 구조 생성

# 4. Submissions 폴더 템플릿 생성 (사용자 작업 공간)
submissions_dir = output_path / "submissions"
submissions_dir.mkdir(exist_ok=True)

# .gitkeep 파일 생성 (빈 폴더 유지)
(submissions_dir / ".gitkeep").touch()

# README.md 템플릿 생성
submissions_readme = submissions_dir / "README.md"
submissions_readme.write_text("""# Submissions
이 폴더는 여러분의 AI 에이전트를 개발하는 작업 공간입니다.
...
""", encoding='utf-8')
```

### SDK 빌드 및 배포

```bash
# 1. ai-combat 저장소에서 SDK 빌드
cd ai-combat
python scripts/build_sdk.py --output ../ai-combat-sdk

# 2. SDK 저장소로 이동
cd ../ai-combat-sdk

# 3. 변경사항 확인
git status
# 출력 예시:
# modified:   .gitignore
# modified:   README.md
# new file:   submissions/.gitkeep
# new file:   submissions/README.md

# 4. 커밋 및 푸시
git add .
git commit -m "feat: 사용자 파일 충돌 방지 구조 개선"
git push origin main
```

---

## ✅ 검증 체크리스트

### 빌드 후 확인사항

- [ ] `submissions/.gitkeep` 파일이 생성되었는가?
- [ ] `submissions/README.md` 파일이 생성되었는가?
- [ ] `.gitignore`에 `submissions/*` 패턴이 추가되었는가?
- [ ] SDK README에 "SDK 업데이트 및 사용자 파일 관리" 섹션이 있는가?

### 사용자 테스트

```bash
# 1. 새 에이전트 생성
mkdir submissions/test_agent
echo "name: test_agent" > submissions/test_agent/test_agent.yaml

# 2. Git 상태 확인 (추적되지 않아야 함)
git status
# 출력: nothing to commit, working tree clean

# 3. SDK 업데이트 시뮬레이션
git stash
git pull origin main
# 출력: Already up to date.

# 4. 사용자 파일 보존 확인
ls submissions/test_agent/
# 출력: test_agent.yaml (파일이 그대로 존재)
```

---

## 🎯 기대 효과

1. **사용자 경험 개선**
   - SDK 업데이트 시 작업물 손실 걱정 없음
   - Git 충돌 해결 불필요

2. **유지보수 용이성**
   - 사용자 파일과 SDK 코어 명확히 분리
   - 버전 관리 복잡도 감소

3. **협업 효율성**
   - 팀원 간 SDK 버전 동기화 용이
   - 개인 작업물은 독립적으로 관리

---

## 📞 문제 해결

### Q: 기존 에이전트가 Git에 이미 커밋되어 있는 경우?

```bash
# Git 히스토리에서 제거 (로컬 파일은 유지)
git rm --cached -r submissions/my_agent/
git commit -m "Remove user files from version control"
```

### Q: SDK 업데이트 후 에이전트가 실행되지 않는 경우?

```bash
# 1. 의존성 재설치
pip install -r requirements.txt --upgrade

# 2. 에이전트 검증
python tools/validate_agent.py submissions/my_agent/my_agent.yaml

# 3. 호환성 확인
python scripts/run_match.py --agent1 my_agent --agent2 simple
```

### Q: 여러 컴퓨터에서 동일한 에이전트를 사용하려면?

**방법 1: 수동 복사**
```bash
# 컴퓨터 A
zip -r my_agent.zip submissions/my_agent/

# 컴퓨터 B
unzip my_agent.zip -d submissions/
```

**방법 2: 별도 Git 저장소**
```bash
# submissions/ 폴더를 별도 저장소로 관리
cd submissions
git init
git remote add origin https://github.com/yourname/my-agents.git
git add .
git commit -m "My agents"
git push -u origin main
```

---

## 📚 관련 문서

- [SDK README](../sdk/README.md) - 사용자 파일 관리 가이드
- [build_sdk.py](../scripts/build_sdk.py) - SDK 빌드 스크립트
- [.gitignore](../.gitignore) - Git 제외 패턴

---

**마지막 업데이트**: 2026-03-12  
**작성자**: AI Combat Team
