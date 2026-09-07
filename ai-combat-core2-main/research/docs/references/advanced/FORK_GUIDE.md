# Fork 방식으로 SDK 사용하기

## 🎯 왜 Fork를 사용하나요?

Fork 방식을 사용하면:
- ✅ SDK 업데이트 시 충돌 없이 깔끔하게 병합
- ✅ 자신의 에이전트를 GitHub에 백업 가능
- ✅ 팀원과 협업 가능
- ✅ SDK 개선 사항을 Pull Request로 기여 가능

---

## 📖 설치 가이드

### 1단계: GitHub에서 Fork 생성

1. https://github.com/rokafa-daslab/ai-combat-sdk 접속
2. 우측 상단 **"Fork"** 버튼 클릭
3. 자신의 계정으로 Fork 생성 완료

![Fork 버튼](https://docs.github.com/assets/cb-23088/mw-1000/images/help/repository/fork_button.png)

---

### 2단계: Fork한 저장소 클론

```bash
# 자신의 Fork 저장소 클론 (YOUR_USERNAME을 본인 계정으로 변경)
git clone https://github.com/YOUR_USERNAME/ai-combat-sdk.git
cd ai-combat-sdk

# 가상환경 생성 및 활성화
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 의존성 설치
pip install -r requirements.txt
```

---

### 3단계: 에이전트 개발

```bash
# submissions 폴더 생성 (최초 1회)
mkdir submissions
cd submissions

# 에이전트 폴더 생성
mkdir my_agent
cd my_agent

# my_agent.yaml 작성
# (에디터로 작성)
```

---

### 4단계: 작업물 백업 (선택사항)

자신의 에이전트를 GitHub에 백업하려면:

```bash
# submissions/ 폴더를 Git 추적 대상에 포함
git add submissions/my_agent/
git commit -m "feat: my_agent 추가"
git push origin main
```

> ⚠️ **주의**: 기본적으로 `submissions/`는 `.gitignore`에 의해 제외됩니다.
> 백업을 원하면 위 명령어로 강제 추가하세요.

---

### 5단계: SDK 업데이트

SDK가 업데이트되면 다음 방법으로 최신 버전을 받을 수 있습니다.

#### 방법 1: GitHub UI (추천, 가장 간편)

1. 자신의 Fork 저장소 페이지 접속 (`https://github.com/YOUR_USERNAME/ai-combat-sdk`)
2. 상단에 "This branch is X commits behind songhyonkim:main" 메시지 확인
3. **"Sync fork"** 버튼 클릭
4. **"Update branch"** 클릭
5. 로컬에서 업데이트 받기:
   ```bash
   git pull origin main
   ```

![Sync Fork](https://docs.github.com/assets/cb-49937/mw-1000/images/help/repository/update-branch-button.png)

---

#### 방법 2: CLI (고급 사용자)

```bash
# 최초 1회만: upstream 원격 저장소 추가
git remote add upstream https://github.com/rokafa-daslab/ai-combat-sdk.git

# 업데이트 시마다 실행
git fetch upstream
git merge upstream/main

# 또는 한 줄로
git pull upstream main
```

---

## 🔧 충돌 해결

### submissions/ 폴더 충돌

기본적으로 `submissions/`는 `.gitignore`에 의해 제외되므로 충돌이 발생하지 않습니다.

만약 `submissions/`를 커밋한 경우:
```bash
# 충돌 발생 시
git status  # 충돌 파일 확인

# 자신의 버전 유지
git checkout --ours submissions/my_agent/my_agent.yaml
git add submissions/my_agent/my_agent.yaml

# 병합 완료
git commit
```

### 기타 파일 충돌

SDK 파일(예제, 문서 등)을 수정한 경우:
```bash
# SDK 버전 우선 (권장)
git checkout --theirs path/to/file

# 자신의 버전 우선
git checkout --ours path/to/file

# 수동 병합
# 에디터로 파일을 열어 충돌 마커(<<<<<<, ======, >>>>>>)를 수동 해결
```

---

## 🆚 Fork vs Clone 비교

| 항목 | Fork (추천) | Clone (기존 방식) |
|------|------------|------------------|
| **설치** | Fork → Clone | Clone |
| **업데이트** | Sync fork 버튼 | `git pull` (충돌 가능) |
| **백업** | GitHub에 자동 백업 | 로컬만 |
| **협업** | 팀원 초대 가능 | 불가 |
| **기여** | Pull Request 가능 | 불가 |
| **충돌 관리** | GitHub UI에서 명확 | CLI에서 수동 해결 |

---

## 💡 FAQ

### Q1: Fork 없이 Clone만 해도 되나요?
A: 가능하지만 권장하지 않습니다. SDK 업데이트 시 `.pyd` 파일 등 82개의 변경사항이 표시되어 혼란스러울 수 있습니다.

### Q2: Fork한 저장소를 Private으로 만들 수 있나요?
A: GitHub 무료 계정에서는 Public 저장소의 Fork는 Public으로만 유지됩니다. Private 백업을 원하면 별도 저장소를 생성하세요.

### Q3: 팀원과 협업하려면?
A: Fork한 저장소에 팀원을 Collaborator로 초대하세요 (Settings → Collaborators).

### Q4: SDK에 버그를 발견했어요!
A: Fork에서 수정 후 원본 저장소에 Pull Request를 보내주세요. 기여를 환영합니다!

---

## 🔗 참고 자료

- [GitHub Fork 공식 문서](https://docs.github.com/en/get-started/quickstart/fork-a-repo)
- [Sync Fork 가이드](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork)
- [Git 충돌 해결](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/addressing-merge-conflicts)
