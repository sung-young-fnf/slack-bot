# Slack Daily Briefing Bot

Desktop의 개발 프로젝트 `.md` 파일과 GitHub Issues/PR을 읽어 Slack 멘션 한 번으로 오늘 할일을 AI 브리핑해주는 봇.

## 기술 스택

- **언어**: Python
- **Slack SDK**: slack-bolt (Socket Mode)
- **GitHub SDK**: PyGithub
- **AI**: anthropic (`claude-sonnet-4-20250514`)
- **프로세스 관리**: PM2

## 프로젝트 구조

```
src/
├── main.py                  # 엔트리포인트, Bolt 앱 초기화
├── handlers/briefing.py     # 멘션 이벤트 핸들러
├── collectors/
│   ├── md_collector.py      # Desktop .md 파일 수집 및 파싱
│   └── github_collector.py  # GitHub Issues/PR 수집 (5분 캐시)
├── ai/claude.py             # Claude API 호출, 프롬프트 조립
└── formatter/block_kit.py   # Slack Block Kit 메시지 포맷팅
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

1. `@bot 오늘 할일 브리핑` 멘션 수신
2. "로딩 중..." 즉시 응답
3. `asyncio.gather`로 병렬 데이터 수집
   - Desktop `.md` 파일에서 할일/완료 항목 파싱
   - GitHub Open Issues / Open PRs 조회
4. Claude API로 우선순위 분석 + 브리핑 생성
5. Slack Block Kit으로 포맷팅 후 메시지 업데이트

## 오류 처리 방침

| 상황 | 처리 |
|------|------|
| `.md` 없는 프로젝트 | skip |
| GitHub API 실패 | "GitHub 정보를 가져올 수 없습니다" 표시 후 계속 |
| `.git` 없는 폴더 | GitHub 수집 skip |
| Claude API 실패 | 수집 데이터 원본 텍스트 그대로 전송 |
| 전체 실패 | "브리핑 생성 중 오류가 발생했습니다" 메시지 |

## 개발 시 유의사항

- `src/` 를 working directory로 실행하므로 import는 `src/` 기준 상대경로 사용
- GitHub API 응답은 `github_collector.py` 내 딕셔너리로 5분 캐시됨
- Block Kit 텍스트 블록은 3000자 제한 — `_split_text()`로 자동 분할
- `.env` 는 절대 커밋하지 않음 (`.gitignore` 포함됨)
