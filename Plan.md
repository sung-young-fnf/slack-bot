Slack Daily Briefing Bot — PLAN.md
프로젝트 개요
Desktop에 있는 개발 프로젝트들의 .md 파일과 GitHub Issues/PR을 읽어서, Slack 멘션 한 번으로 오늘 할일을 AI 브리핑해주는 Bot.
* 배포 없이 로컬 머신에서 Socket Mode로 상시 운영
* Claude API (claude-sonnet-4)로 우선순위 분석 및 브리핑 생성
* PM2로 프로세스 관리 (재부팅 후 자동 재시작)

기술 스택
항목	선택	비고
언어	Python   ..	
Slack SDK	slack-bolt	Socket Mode 지원
GitHub SDK	PyGithub	REST API 래퍼
AI	anthropic	claude-sonnet-4
파일 탐색	pathlib + glob	표준 라이브러리
환경변수	python-dotenv	토큰 관리
프로세스 관리	pm2	파이썬도 지원
비동기	asyncio	병렬 데이터 수집
프로젝트 디렉토리 구조
slack-briefing-bot/
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
├── .env                          # 환경변수 (gitignore 필수)
├── .env.example                  # 환경변수 샘플
├── .gitignore
├── requirements.txt
├── ecosystem.config.js           # PM2 설정
└── PLAN.md                       # 이 파일

환경변수 목록 (.env)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
GITHUB_TOKEN=ghp_...
ANTHROPIC_API_KEY=sk-ant-...
DESKTOP_PATH=/Users/yourname/Desktop
GITHUB_USERNAME=your-github-username

requirements.txt
slack-bolt
PyGithub
anthropic
python-dotenv

전체 프로세스 플로우
[Slack 멘션] @bot 오늘 할일 브리핑
      |
      v
[Step 1] Bolt Socket Mode로 멘션 이벤트 수신
      |
      v
[Step 2] 명령어 파싱
         - "오늘 할일 브리핑" → 전체 브리핑
         - "프로젝트명 브리핑" → 특정 프로젝트만
      |
      v
[Step 3] 병렬 데이터 수집 (asyncio.gather)
      ├── [3-A] Desktop FS 수집
      │         DESKTOP_PATH 하위 폴더 재귀 탐색
      │         각 폴더에서 .md 파일 탐색
      │         할일/완료 섹션 파싱
      │
      └── [3-B] GitHub 수집
                각 프로젝트 폴더의 .git/config에서 remote URL 파싱
                PyGithub으로 Open Issues 조회 (assignee=me)
                PyGithub으로 Open PRs 조회 (author=me)
      |
      v
[Step 4] 수집 데이터 구조화
         { project, todos, done, issues, prs }[] 형태로 취합
      |
      v
[Step 5] Claude API 호출
         구조화된 데이터 → 프롬프트 조립
         우선순위 분석 + 오늘 브리핑 텍스트 생성
      |
      v
[Step 6] Slack Block Kit 포맷팅
         섹션별 구분, 프로젝트별 요약, GitHub 링크 첨부
      |
      v
[Step 7] Slack 채널 메시지 전송

구현 태스크 (순서대로)
Phase 1 — 프로젝트 셋업
* [ ] 가상환경 생성 및 패키지 설치 python -m venv venvsource venv/bin/activatepip install slack-bolt PyGithub anthropic python-dotenvpip freeze > requirements.txt
* 
* [ ] .env 및 .env.example 작성
* [ ] .gitignore 설정 (.env, venv/, __pycache__/ 포함)
* [ ] Slack App 생성 (api.slack.com)
    * Socket Mode 활성화
    * app_mentions:read, chat:write 스코프 추가
    * Bot Token, App-Level Token 발급
Phase 2 — Bot 뼈대
* [ ] src/main.py — Bolt 앱 초기화 + Socket Mode 연결
* [ ] src/handlers/briefing.py — 멘션 이벤트 수신 + "로딩 중..." 즉시 응답
* [ ] 정상 동작 확인 (멘션 → 고정 텍스트 응답)
Phase 3 — Desktop .md 수집
* [ ] src/collectors/md_collector.py 구현
    * pathlib.Path(DESKTOP_PATH).rglob("*.md")로 재귀 탐색
    * ## 할일, ## TODO, ## 완료, ## Done 섹션 파싱
    * 체크박스 항목 (- [ ], - [x]) 정규식으로 추출
* [ ] 파싱 결과 구조화 테스트
Phase 4 — GitHub 수집
* [ ] src/collectors/github_collector.py 구현
    * 프로젝트 폴더의 .git/config 파싱 → remote origin URL 추출
    * configparser로 파싱 후 owner/repo 추출
    * PyGithub으로 Issues 조회 (open, assignee=GITHUB_USERNAME)
    * PyGithub으로 PRs 조회 (open, author=GITHUB_USERNAME)
    * Rate limit 대응: 응답 캐시 5분 (딕셔너리 + timestamp)
* [ ] 오류 처리: private 레포 접근 실패, .git 없는 폴더 skip
Phase 5 — Claude API 브리핑 생성
* [ ] src/ai/claude.py 구현
    * 수집 데이터를 구조화된 프롬프트로 조립
    * anthropic.Anthropic().messages.create() 호출
    * 모델: claude-sonnet-4-20250514
    * 시스템 프롬프트: 한국어 브리핑, 우선순위 Top 3 제안
    * 오류 처리: API 실패 시 fallback 메시지
Phase 6 — Slack Block Kit 포맷팅
* [ ] src/formatter/block_kit.py 구현
    * Header 섹션: "오늘의 개발 브리핑"
    * 프로젝트별 섹션 구분
    * GitHub Issues/PR 링크 첨부
    * 우선순위 Top 3 하이라이트
Phase 7 — PM2 설정 및 운영
* [ ] ecosystem.config.js 작성 module.exports = {  apps: [{    name: 'slack-briefing-bot',    script: 'src/main.py',    interpreter: './venv/bin/python',    watch: false,    restart_delay: 3000,  }]}
* 
* [ ] pm2 start ecosystem.config.js
* [ ] pm2 startup + pm2 save
* [ ] 재부팅 후 자동 실행 확인

Claude 프롬프트 설계
시스템 프롬프트
당신은 개발자의 일일 업무 브리핑을 도와주는 어시스턴트입니다.
주어진 프로젝트별 할일 목록과 GitHub 이슈/PR 정보를 바탕으로
오늘 집중해야 할 작업을 한국어로 간결하게 브리핑해주세요.

출력 형식:
1. 프로젝트별 할일 요약
2. 처리가 필요한 GitHub 이슈/PR
3. 한 줄 코멘트 
유저 프롬프트 구조
[프로젝트: project-name]
할일: ...
완료: ...
GitHub Issues: ...
GitHub PRs: ...

[프로젝트: another-project]
...

Slack Block Kit 메시지 예시
━━━━━━━━━━━━━━━━━━━
📋 오늘의 개발 브리핑
━━━━━━━━━━━━━━━━━━━

🎯 오늘의 할일
1. [project-a] API 인증 모듈 완성
2. [project-b] PR #42 리뷰 요청 처리
3. [project-a] 유닛 테스트 작성

📁 project-a
  할일 3건 | 완료 5건
  Issues: #12 로그인 버그, #15 성능 개선

📁 project-b
  할일 1건 | 완료 2건
  PR: #42 feat: 결제 모듈 추가 (리뷰 대기)


오류 처리 방침
상황	처리 방식
.md 파일 없는 프로젝트	skip, 브리핑에서 제외
GitHub API 실패	"GitHub 정보를 가져올 수 없습니다" 표시 후 계속
.git 없는 폴더	GitHub 수집 skip
Claude API 실패	수집 데이터 원본 텍스트 그대로 전송
전체 실패	"브리핑 생성 중 오류가 발생했습니다" 메시지
확장 가능한 기능 (v2 이후)
* 스케줄 브리핑: 매일 오전 9시 자동 발송 (schedule 라이브러리)
* 특정 프로젝트 지정: @bot project-a 브리핑
* 완료 처리 인터랙션: Slack 버튼으로 체크박스 toggle
* 멀티 유저 지원: 유저별 Desktop 경로 설정
* 주간 회고 브리핑: @bot 이번 주 정리
