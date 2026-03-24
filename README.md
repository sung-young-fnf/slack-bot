# Slack Daily Briefing Bot

Desktop의 개발 프로젝트 `.md` 파일과 GitHub Issues/PR을 읽어,
Slack 멘션 한 번으로 오늘 할일을 AI가 브리핑해주는 Bot.

- 배포 없이 로컬 머신에서 Socket Mode로 상시 운영
- Claude AI로 우선순위 분석 및 브리핑 생성
- PM2로 프로세스 관리 (재부팅 후 자동 재시작)

---

## 프로젝트 구조

```
slack_bot/
├── src/
│   ├── main.py                   # 엔트리포인트, Bolt 앱 초기화
│   ├── handlers/
│   │   └── briefing.py           # 멘션 이벤트 핸들러
│   ├── collectors/
│   │   ├── md_collector.py       # Desktop .md 파일 수집 및 파싱
│   │   └── github_collector.py   # GitHub Issues/PR 수집
│   ├── ai/
│   │   └── claude.py             # Claude API 호출, 프롬프트 조립
│   └── formatter/
│       └── block_kit.py          # Slack Block Kit 메시지 포맷팅
├── .env                          # 환경변수 (gitignore됨)
├── .env.example                  # 환경변수 샘플
├── .gitignore
├── requirements.txt
├── ecosystem.config.js           # PM2 설정
└── CLAUDE.md                     # Claude Code 프로젝트 컨텍스트
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
DESKTOP_PATH=/Users/yourname/Desktop  # 프로젝트 폴더 경로
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

### 4. 실행

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

Slack 채널에서 봇을 멘션합니다.

```
@bot 오늘 할일 브리핑        # 전체 프로젝트 브리핑
@bot project-a 브리핑       # 특정 프로젝트만 브리핑
```

**응답 예시**

```
━━━━━━━━━━━━━━━━━━━
오늘의 개발 브리핑
━━━━━━━━━━━━━━━━━━━

오늘의 우선순위 Top 3
1. [project-a] API 인증 모듈 완성
2. [project-b] PR #42 리뷰 요청 처리
3. [project-a] 유닛 테스트 작성

project-a  할일 3건 | 완료 5건
Issues: #12 로그인 버그, #15 성능 개선

project-b  할일 1건 | 완료 2건
PR: #42 feat: 결제 모듈 추가 (리뷰 대기)
```

---

## .md 파일 할일 파싱 규칙

프로젝트 폴더 내 `.md` 파일에서 아래 형식을 인식합니다.

```markdown
## 할일 (또는 TODO)
- [ ] 해야 할 작업
- [ ] 또 다른 작업

## 완료 (또는 Done)
- [x] 완료된 작업
```

---