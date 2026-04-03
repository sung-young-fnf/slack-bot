# Slack Daily Briefing Bot

Desktop의 개발 프로젝트 `TASKS.md`와 GitHub Issues/PR을 읽어 Slack 멘션 한 번으로 오늘 할일을 AI 브리핑해주는 봇. Slack에서 할일 추가/완료 처리 시 Git PR을 자동 생성한다.

## 기술 스택

- **언어**: Python
- **Slack SDK**: slack-bolt (Socket Mode)
- **GitHub SDK**: PyGithub
- **AI**: anthropic (Sonnet 4.6: 브리핑, Haiku 4.5: 요청 분류)
- **DB**: SQLite (대화내역 저장, 7일 보관)
- **Git**: subprocess + PyGithub (브랜치/커밋/PR 자동화)
- **프로세스 관리**: PM2

## 프로젝트 구조

```
src/
├── main.py                    # 엔트리포인트, Bolt 앱 초기화
├── handlers/
│   ├── briefing.py            # 멘션 이벤트 핸들러 + AI 라우팅
│   └── task_manager.py        # TASKS.md 할일 추가/완료 + Git PR
├── collectors/
│   ├── md_collector.py        # TASKS.md 파싱
│   └── github_collector.py    # GitHub Issues/PR 수집 (5분 캐시)
├── ai/
│   └── claude.py              # AI 요청 분류 + 브리핑 생성
├── executor/
│   └── git_manager.py         # Git 브랜치/커밋/푸시/PR 관리
├── formatter/
│   └── block_kit.py           # Slack Block Kit 포맷팅
└── storage/
    └── conversation_store.py  # SQLite 대화내역 관리
```

## 환경변수 (.env)

| 변수 | 설명 |
|------|------|
| `SLACK_BOT_TOKEN` | Slack Bot Token (`xoxb-`) |
| `SLACK_APP_TOKEN` | Slack App-Level Token (`xapp-`) |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `DESKTOP_PATH` | 프로젝트들이 있는 로컬 경로 |
| `GITHUB_USERNAME` | GitHub 사용자명 |

## 실행

```bash
# 개발
source venv/bin/activate
python src/main.py

# 운영 (PM2)
pm2 start ecosystem.config.js
pm2 startup && pm2 save
```

## 주요 동작 흐름

1. `@bot` 멘션 수신
2. 대화내역 DB 저장 + 스레드 history 조회
3. Claude Haiku로 요청 분류 (task_add / task_done / briefing / general)
4. 분류 결과에 따라:
   - **task_add/task_done**: TASKS.md 수정 → Git 브랜치/커밋/PR → Slack에 PR 링크 전송
   - **briefing**: 데이터 수집 → Claude Sonnet 브리핑 생성 → Block Kit 포맷팅
   - **general**: Claude Sonnet 일반 응답

## 오류 처리 방침

| 상황 | 처리 |
|------|------|
| TASKS.md 없는 프로젝트 | skip |
| GitHub API 실패 | "GitHub 정보를 가져올 수 없습니다" 표시 후 계속 |
| `.git` 없는 폴더 | GitHub 수집 skip, 할일 관리는 로컬 수정 |
| Claude API 실패 | 수집 데이터 원본 텍스트 그대로 전송 |
| Git push/PR 실패 | 롤백 후 오류 메시지 전달 |
| DB locked/실패 | 에러 무시, 맥락 없이 진행 |
| 전체 실패 | "브리핑 생성 중 오류가 발생했습니다" 메시지 |

## 개발 시 유의사항

- `src/` 를 working directory로 실행하므로 import는 `src/` 기준 상대경로 사용
- GitHub API 응답은 `github_collector.py` 내 딕셔너리로 5분 캐시됨
- Block Kit 텍스트 블록은 3000자 제한 — `_split_text()`로 자동 분할
- `.env` 는 절대 커밋하지 않음 (`.gitignore` 포함됨)
- Git remote URL에 토큰 포함 시 파싱 주의 (`rstrip` 대신 `endswith` 사용)
- Haiku가 JSON을 ```json 코드블록으로 감쌀 수 있음 — 파싱 시 코드블록 제거 필요
- SQLite DB 에러 시 봇이 크래시하지 않도록 모든 DB 함수에 try/except 적용
