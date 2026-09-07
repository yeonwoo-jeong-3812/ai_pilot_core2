# 릴리스 프로세스

비공개 저장소(ai-combat)에서 공개 저장소(ai-combat-sdk)로 릴리스하는 프로세스입니다.

---

## 📋 사전 준비

### 1. GitHub Secrets 설정

공개 저장소로 자동 푸시하려면 GitHub Secrets에 토큰을 설정해야 합니다.

**비공개 저장소 (ai-combat-core) Settings > Secrets and variables > Actions:**

- `PUBLIC_REPO_TOKEN`: 공개 저장소 접근 권한이 있는 Personal Access Token
  - Scopes: `repo`, `workflow`
  - 생성: GitHub Settings > Developer settings > Personal access tokens

### 2. 의존성 확인

```bash
pip install cython numpy
```

---

## 🚀 릴리스 절차

### Step 1: 개발 완료 및 테스트

**dev_0.4 브랜치에서 작업:**

```bash
# 모든 변경사항 커밋
git add .
git commit -m "feat: 파라미터화 시스템 구현"

# 테스트 실행
python -m pytest test/

# 매치 테스트
python scripts/run_match.py --agent1 viper1 --agent2 eagle1 --rounds 3
```

### Step 2: main 브랜치로 병합

```bash
# main 브랜치로 전환
git checkout main

# dev_0.4 병합
git merge dev_0.4

# 충돌 해결 (필요시)
# ...

# 푸시
git push origin main
```

### Step 3: 태그 생성

```bash
# 태그 생성
git tag -a v0.4.0 -m "Release v0.4.0

주요 변경사항:
- 파라미터화된 노드 시스템
- 상세한 파라미터 레퍼런스 문서
- 예제 에이전트 업데이트 (viper1, eagle1)
- Cython 컴파일 지원
"

# 태그 푸시
git push origin v0.4.0
```

### Step 4: GitHub Actions 자동 빌드

태그를 푸시하면 GitHub Actions가 자동으로:

1. SDK 빌드 (`scripts/build_sdk.py`)
2. 아카이브 생성 (`.tar.gz`)
3. GitHub Release 생성
4. 공개 저장소로 푸시

**진행 상황 확인:**
- https://github.com/songhyonkim/ai-combat-core/actions

### Step 5: 공개 저장소 확인

**https://github.com/rokafa-daslab/ai-combat-sdk 확인:**

- [ ] 파일이 정상적으로 복사되었는지
- [ ] 태그가 생성되었는지
- [ ] README.md가 올바른지
- [ ] 예제 에이전트가 포함되었는지

---

## 🛠️ 수동 빌드 (옵션)

GitHub Actions를 사용하지 않고 수동으로 빌드할 수 있습니다.

### 로컬 빌드

```bash
# SDK 빌드
python scripts/build_sdk.py --output ../ai-combat-sdk

# 결과 확인
cd ../ai-combat-sdk
ls -la
```

### 공개 저장소로 푸시

```bash
cd ../ai-combat-sdk

# Git 초기화 (최초 1회만)
git init
git remote add origin https://github.com/rokafa-daslab/ai-combat-sdk.git

# 커밋 및 푸시
git add .
git commit -m "Release v0.4.0"
git tag v0.4.0
git push origin main
git push origin v0.4.0
```

---

## 📦 빌드 결과물

### 공개 저장소 구조

```
ai-combat-sdk/
├── README.md                  # SDK_README.md에서 복사
├── .gitignore                 # SDK_GITIGNORE.txt에서 복사
├── requirements.txt
├── sdk/                       # 문서 및 도구
├── examples/                  # 예제 에이전트
├── submissions/               # 참여자 템플릿 + 예제
│   ├── viper1/
│   ├── eagle1/
│   └── README.md
├── config/                    # 설정 파일
├── lib/                       # 컴파일된 핵심 코드 (.pyc)
├── scripts/                   # 실행 스크립트
└── replays/                   # 빈 폴더
```

### 제외된 항목

- `src/` (원본 소스 → `lib/`로 컴파일됨)
- `external_repo/`
- `docs/` (내부 문서)
- `test/`
- `.venv/`, `__pycache__/`
- `examples/archived/`

---

## 🔍 검증 체크리스트

릴리스 전 확인사항:

### 코드 품질
- [ ] 모든 테스트 통과
- [ ] Lint 경고 없음
- [ ] 예제 에이전트 정상 작동

### 문서
- [ ] README.md 최신화
- [ ] PARAMETER_REFERENCE.md 완성
- [ ] NODE_REFERENCE.md 업데이트
- [ ] CHANGELOG 작성

### 빌드
- [ ] SDK 빌드 성공
- [ ] 컴파일된 파일 정상 작동
- [ ] 의존성 목록 정확

### 공개 저장소
- [ ] 민감 정보 제거
- [ ] 라이센스 파일 포함
- [ ] 예제 에이전트 포함

---

## 🐛 문제 해결

### GitHub Actions 실패

**로그 확인:**
```bash
# Actions 탭에서 실패한 워크플로우 클릭
# 각 단계의 로그 확인
```

**일반적인 원인:**
1. `PUBLIC_REPO_TOKEN` 미설정
2. 빌드 스크립트 오류
3. 의존성 누락

### 수동 재시도

```bash
# 태그 삭제 후 재생성
git tag -d v0.4.0
git push origin :refs/tags/v0.4.0

# 수정 후 재생성
git tag -a v0.4.0 -m "Release v0.4.0"
git push origin v0.4.0
```

---

## 📝 버전 관리

### 버전 번호 규칙

**Semantic Versioning (MAJOR.MINOR.PATCH):**

- `v0.4.0`: 메이저 기능 추가
- `v0.4.1`: 버그 수정
- `v0.5.0`: 다음 메이저 기능

### 브랜치 전략

```
main          (안정 릴리스)
  ↑
dev_0.4       (개발 중)
  ↑
feature/*     (기능 개발)
```

---

## 🔄 핫픽스 프로세스

긴급 버그 수정이 필요한 경우:

```bash
# main에서 핫픽스 브랜치 생성
git checkout main
git checkout -b hotfix/v0.4.1

# 수정
# ...

# 커밋
git commit -m "fix: Hard Deck 판정 버그 수정"

# main으로 병합
git checkout main
git merge hotfix/v0.4.1

# 태그 생성
git tag -a v0.4.1 -m "Hotfix v0.4.1: Hard Deck 판정 버그 수정"
git push origin main
git push origin v0.4.1

# dev 브랜치에도 병합
git checkout dev_0.4
git merge hotfix/v0.4.1
git push origin dev_0.4
```

---

## 📊 릴리스 체크리스트

### 릴리스 전

- [ ] 모든 기능 구현 완료
- [ ] 테스트 통과
- [ ] 문서 업데이트
- [ ] CHANGELOG 작성
- [ ] 버전 번호 결정

### 릴리스 중

- [ ] dev → main 병합
- [ ] 태그 생성 및 푸시
- [ ] GitHub Actions 성공 확인
- [ ] 공개 저장소 확인

### 릴리스 후

- [ ] Release Notes 작성
- [ ] 참여자에게 공지
- [ ] 피드백 수집
- [ ] 다음 버전 계획

---

## 📅 릴리스 일정 (예시)

| 버전 | 날짜 | 주요 기능 |
|------|------|----------|
| v0.4.0 | 2026-02-01 | 파라미터화 시스템 |
| v0.5.0 | 2026-03-01 | 멀티플레이어 지원 |
| v1.0.0 | 2026-06-01 | 정식 릴리스 |

---

**릴리스 담당자: songhyonkim**
