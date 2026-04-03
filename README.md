# Slack Daily Briefing Bot

Desktop의 개발 프로젝트 `TASKS.md`와 GitHub Issues/PR을 읽어,
Slack 멘션 한 번으로 오늘 할일을 AI가 브리핑해주는 Bot.

- 배포 없이 로컬 머신에서 Socket Mode로 상시 운영
- Claude AI로 우선순위 분석 및 브리핑 생성
- 스레드 내 대화내역 저장으로 맥락 있는 연속 대화 지원
- Slack 멘션으로 TASKS.md 할일 추가/완료 처리 (Git PR 자동 생성)
- PM2로 프로세스 관리 (재부팅 후 자동 재시작)

---

## 프로젝트 구조

```
slack_bot/
├── src/
│   ├── main.py                    # 엔트리포인트, Bolt 앱 초기화
│   ├── handlers/
│   │   ├── briefing.py            # 멘션 이벤트 핸들러 + 라우팅
│   │   └── task_manager.py        # TASKS.md 할일 추가/완료 처리
│   ├── collectors/
│   │   ├── md_collector.py        # TASKS.md 파싱
│   │   └── github_collector.py    # GitHub Issues/PR 수집
│   ├── ai/
│   │   └── claude.py              # Claude API 호출 + 할일 의도 분석
│   ├── executor/
│   │   └── git_manager.py         # Git 브랜치/커밋/푸시/PR 관리
│   ├── formatter/
│   │   └── block_kit.py           # Slack Block Kit 메시지 포맷팅
│   └── storage/
│       └── conversation_store.py  # SQLite 대화내역 관리
├── data/                          # SQLite DB (자동 생성, gitignore)
├── docs/                          # 기획서, 구조 문서
├── .env                           # 환경변수 (gitignore됨)
├── .env.example                   # 환경변수 샘플
├── .gitignore
├── requirements.txt
├── ecosystem.config.js            # PM2 설정
├── TASKS.md                       # 프로젝트 할일 관리
└── CLAUDE.md                      # Claude Code 프로젝트 컨텍스트
```

---

## 시작 방법

### 1. Slack App 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 에서 새 앱 생성
2. **Socket Mode** 활성화 → App-Level Token 발급 (`connections:write` 스코프)
3. **OAuth & Permissions** → Bot Token Scopes 추가
   - `app_mentions:read`
   - `chat:write`
4. **Event Subscriptions** → `app_mention` 이벤트 구독
5. 앱을 워크스페이스에 설치 → Bot Token 복사 (`xoxb-`)

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 입력합니다.

```env
SLACK_BOT_TOKEN=xoxb-...          # Slack Bot Token
SLACK_APP_TOKEN=xapp-...          # Slack App-Level Token
GITHUB_TOKEN=ghp_...              # GitHub Personal Access Token
ANTHROPIC_API_KEY=sk-ant-...      # Anthropic API Key
DESKTOP_PATH=C:\Users\...\project # 프로젝트 폴더 경로
GITHUB_USERNAME=your-github-username  # GitHub 사용자명
```

### 3. 가상환경 및 패키지 설치

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

### 4. Git 인증 설정 (PR 자동 생성용)

```bash
git remote set-url origin https://<GITHUB_TOKEN>@github.com/<owner>/<repo>.git
```

### 5. 실행

**개발 환경 (직접 실행)**

```bash
python src/main.py
```

**운영 환경 (PM2)**

```bash
# 시작
pm2 start ecosystem.config.js

# 재부팅 후 자동 시작 등록
pm2 startup
pm2 save

# 상태 확인
pm2 status

# 로그 확인
pm2 logs slack-briefing-bot
```

---

## 사용 방법

### 업무 브리핑

```
@bot 오늘 할일 브리핑        # 전체 프로젝트 브리핑
@bot 진행상황 정리해줘       # 진행 상황 요약
```

### 할일 관리 (TASKS.md → Git PR)

```
@bot slack_bot에 할일 추가해줘 — "API 에러 핸들링", "README 업데이트"
@bot slack_bot에서 "API 에러 핸들링" 완료 처리해줘
@bot fnf-process에 "기획서 작성" 완료로 3월 31자로 작성해줘
```

- Git 연동된 프로젝트: 브랜치 생성 → 커밋 → 푸시 → PR 생성 → PR 링크 전송
- Git 미연동 프로젝트: 로컬 파일 직접 수정
- 키워드 매칭 우선, 실패 시 Claude AI로 자연어 의도 분석

### 일반 질문

```
@bot 스킬셋 알려줘           # 스킬셋 질문
@bot 기능 소개해줘           # 봇 기능 안내
@bot 파이썬에서 데코레이터가 뭐야?  # 일반 질문
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 업무 브리핑 | TASKS.md + GitHub Issues/PR 수집 → AI 분석 → 우선순위 브리핑 |
| 할일 추가/완료 | Slack 멘션으로 TASKS.md 수정 → Git PR 자동 생성 |
| 대화 맥락 유지 | 스레드 내 대화내역을 SQLite에 저장 (7일 보관, 최대 20턴) |
| AI 의도 분석 | 키워드 매칭 실패 시 Claude Haiku로 자연어 분석 fallback |
| 스킬셋/기능 안내 | 사전 정의된 정보 기반 응답 |
| GitHub 캐싱 | API 응답 5분 메모리 캐시 |
| 오류 Fallback | Claude API 실패 시 수집 데이터 원본 텍스트 전송 |

---

## TASKS.md 파싱 규칙

프로젝트 폴더 내 `TASKS.md`에서 아래 형식을 인식합니다.

```markdown
- [ ] 해야 할 작업
- [x] 완료된 작업 (2026-03-25)
```

---

## 환경변수

| 변수 | 설명 |
|------|------|
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-`) |
| `SLACK_APP_TOKEN` | Slack App-Level Token (`xapp-`) |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `DESKTOP_PATH` | 프로젝트들이 있는 로컬 경로 |
| `GITHUB_USERNAME` | GitHub 사용자명 |
