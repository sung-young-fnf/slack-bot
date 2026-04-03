# Slack Daily Briefing Bot - 구조 리포트

## 개요
Slack 멘션으로 오늘 할일을 AI 브리핑해주는 봇. Desktop 프로젝트의 `TASKS.md`와 GitHub Issues/PR을 수집하여 Claude AI가 분석 후 응답한다. 스레드 내 대화내역을 SQLite에 저장하여 맥락 있는 연속 대화를 지원하고, Slack에서 직접 할일 추가/완료 처리 시 Git PR을 자동 생성한다. 모든 요청 분류는 Claude Haiku AI가 수행하며, 키워드 매칭은 fallback으로만 사용한다.

## 기술 스택
| 구분 | 기술 |
|------|------|
| 언어 | Python |
| Slack | slack-bolt (Socket Mode) |
| GitHub | PyGithub |
| AI | Anthropic Claude Sonnet 4.6 (브리핑/응답), Haiku 4.5 (요청 분류) |
| DB | SQLite (대화내역 저장, 7일 보관, 최대 6턴) |
| Git | subprocess + PyGithub (브랜치/커밋/PR 자동화) |
| 프로세스 관리 | PM2 |

## 프로젝트 구조
```
src/
├── main.py                    # 엔트리포인트 (25줄)
├── handlers/
│   ├── briefing.py            # 멘션 이벤트 핸들러 + AI 라우팅 (100줄)
│   └── task_manager.py        # TASKS.md 할일 추가/완료 + Git PR (277줄)
├── collectors/
│   ├── md_collector.py        # TASKS.md 파싱 (53줄)
│   └── github_collector.py    # GitHub API 수집 (112줄)
├── ai/
│   └── claude.py              # AI 요청 분류 + 브리핑 생성 (222줄)
├── executor/
│   └── git_manager.py         # Git 브랜치/커밋/푸시/PR 관리 (142줄)
├── formatter/
│   └── block_kit.py           # Slack Block Kit 포맷팅 (64줄)
└── storage/
    └── conversation_store.py  # SQLite 대화내역 관리 (86줄)

data/
└── conversations.db           # SQLite DB 파일 (자동 생성, .gitignore)

docs/
├── structure.md               # 구조 리포트 (이 파일)
├── feature_conversation_history.md  # 대화내역 저장 기획서
└── feature_auto_code_pr.md    # 반자동화 코드 수정 & PR 생성 기획서
```

## 동작 흐름
```
@bot 멘션 수신
  → 텍스트 없으면 인사 응답
  → 대화내역 DB 저장 + 스레드 history 조회 (최대 6턴)
  → Claude Haiku로 요청 분류 (task_add / task_done / briefing / general)
    → task_add/task_done:
        TASKS.md 수정 → Git 브랜치/커밋/PR → Slack에 PR 링크 전송
    → briefing:
        TASKS.md 수집 → GitHub Issues/PR 수집
        → Claude Sonnet 브리핑 생성 → Block Kit 포맷팅 → 응답
    → general:
        Claude Sonnet 일반 응답 → Block Kit 포맷팅 → 응답
```

## 모듈별 역할

### main.py
- Bolt App 초기화 + Socket Mode 시작
- `register_handlers()`로 이벤트 핸들러 등록
- 앱 시작 시 `init_db()` + `cleanup_old_conversations()` 실행 (실패 시 skip)

### handlers/briefing.py
- `app_mention` 이벤트 수신 및 전체 흐름 제어
- 대화내역 저장/조회 (할일 관리 + 브리핑 공통)
- `classify_request()`로 AI 요청 분류 → 유형별 라우팅
- task_add/task_done → `handle_task_management()`
- briefing/general → `generate_briefing()` + Block Kit

### handlers/task_manager.py
- AI 분류 결과(`classification`)를 받아 할일 추가/완료 실행
- 키워드 매칭은 AI 결과 보완용 fallback으로만 사용
- Git 연동 프로젝트: 브랜치 생성 → TASKS.md 수정 → 커밋 → 푸시 → PR 생성
- Git 미연동 프로젝트: 로컬 파일 직접 수정
- AI가 추출한 날짜로 완료 처리 가능 (예: "3월 31자로")

### collectors/md_collector.py
- `DESKTOP_PATH` 하위 프로젝트 폴더에서 `TASKS.md` 탐색
- 정규식으로 파싱: `- [ ] 할일` → todos, `- [x] 완료 (날짜)` → done

### collectors/github_collector.py
- `.git/config`에서 remote origin URL 파싱 (HTTPS/SSH, 토큰 포함 URL 지원)
- Open Issues (assignee 필터) + Open PRs (user 필터) 조회
- 5분 메모리 캐시, `asyncio.gather`로 병렬 조회

### ai/claude.py
- `classify_request()`: Haiku 모델로 요청 분류 (task_add/task_done/briefing/general)
  - 대화 맥락(history) 포함하여 후속 질문도 인식
  - JSON 코드블록(```json) 파싱 처리
- `generate_briefing()`: Sonnet 모델로 브리핑/일반 응답 생성
  - 시스템 프롬프트: 3가지 요청 유형 구분 + 말투 규칙("~해요" 체)
  - 대화내역(history)을 messages 배열에 포함하여 맥락 유지
  - API 실패 시 수집 데이터 원본 텍스트로 fallback

### executor/git_manager.py
- `has_git()`: 프로젝트 .git 존재 여부 확인
- `get_default_branch()`: 기본 브랜치명 자동 감지 (main/master)
- `get_remote_url()`: remote origin URL에서 owner/repo 추출 (토큰 포함 URL 지원)
- `create_branch()`: 최신 기본 브랜치에서 새 브랜치 생성
- `commit_and_push()`: 파일 스테이징 → 커밋 → 푸시
- `create_pr()`: PyGithub으로 PR 생성
- `cleanup_branch()` / `restore_branch()`: 작업 후 복귀 / 실패 시 롤백
- subprocess에 `encoding="utf-8"` 설정 (Windows cp949 문제 방지)

### formatter/block_kit.py
- 브리핑: 헤더 "오늘의 업무 브리핑" + AI 응답 + 프로젝트 현황(할일/완료 건수, Issue/PR 링크)
- 일반 질문: 헤더 "AI Agent" + AI 응답만
- 텍스트 3000자 초과 시 자동 분할

### storage/conversation_store.py
- SQLite 기반 대화내역 CRUD 모듈
- `init_db()`: 테이블 및 인덱스 생성 (앱 시작 시 1회)
- `save_message()`: 채널/스레드/역할/내용 저장 (메시지당 최대 2000자)
- `get_thread_history()`: 스레드별 최근 6턴 대화내역 조회 (Claude messages 형식)
- `cleanup_old_conversations()`: 7일 초과 데이터 삭제
- `maybe_cleanup()`: 5% 확률로 cleanup 실행
- WAL 모드 + busy_timeout 10초로 동시성 확보
- 모든 함수에 try/except — DB 에러 시 봇 크래시 방지

## 오류 처리
| 상황 | 처리 |
|------|------|
| TASKS.md 없는 프로젝트 | skip |
| .git 없는 폴더 | GitHub 수집 skip, 할일 관리는 로컬 수정 |
| GitHub API 실패 | 오류 메시지 표시 후 계속 |
| Claude API 실패 | 수집 데이터 원본 텍스트 전송 |
| AI 분류 실패 | general로 fallback |
| Git push 실패 | 변경사항 롤백 후 오류 메시지 |
| PR 생성 실패 | 푸시는 완료, PR 실패 사유 전달 |
| DB locked/실패 | 에러 무시, 맥락 없이 진행 |
| PM2 재시작 시 DB locked | cleanup skip, 봇 정상 시작 |
| 전체 실패 | "브리핑 생성 중 오류가 발생했습니다" |

## 기능 목록

### 1. AI 요청 분류 (통합 라우터)
- Claude Haiku가 모든 멘션을 자동 분류
- task_add / task_done / briefing / general 4가지 유형
- 대화 맥락 포함하여 후속 질문도 인식
- 키워드 매칭 충돌 문제 해결 (AI가 메인, 키워드는 fallback)

### 2. 업무 브리핑
- AI가 briefing으로 분류한 요청
- 로컬 프로젝트 TASKS.md에서 할일/완료 항목 수집
- GitHub Open Issues, Open PRs 수집
- Claude Sonnet이 우선순위 분석 후 브리핑 생성
- 프로젝트 현황 요약 (할일/완료 건수, Issue/PR 링크) 함께 표시

### 3. 할일 관리 (TASKS.md → Git PR)
- Slack 멘션으로 할일 추가 / 완료 처리
- AI가 프로젝트명/항목/날짜를 자연어에서 추출
- Git 연동: 브랜치 생성 → TASKS.md 수정 → 커밋 → 푸시 → PR 생성 → PR 링크 전송
- Git 미연동: 로컬 파일 직접 수정

### 4. 스킬셋 질문 응답
- AI가 general로 분류한 스킬셋 관련 질문
- 사전 정의된 SKILLSET_INFO 기반으로만 응답

### 5. 봇 소개/기능 안내
- AI가 general로 분류한 봇 기능 관련 질문
- CLAUDE.md를 읽어 봇 정보로 전달

### 6. 일반 질문 응답
- AI가 general로 분류한 나머지 질문
- 브리핑 형식 없이 AI가 일반 대화로 응답

### 7. 대화내역 저장 및 맥락 유지
- 스레드 단위로 대화내역을 SQLite에 저장
- 동일 스레드 내 후속 질문 시 이전 대화 맥락 반영
- 스레드당 최대 6턴, 메시지당 2000자 제한
- 7일 경과 데이터 자동 삭제

### 8. 완료 항목 주간 분류
- TASKS.md의 완료 항목을 이번주/지난주로 자동 분류
- 월요일 기준으로 주 구분

### 9. GitHub 데이터 캐싱
- GitHub API 응답을 5분간 메모리 캐시
- 반복 요청 시 API 호출 절감

### 10. 오류 시 Fallback
- Claude API 실패 시 수집 데이터 원본 텍스트로 대체 응답
- GitHub API 실패 시 오류 표시 후 나머지 데이터로 계속 진행
- DB 실패 시 맥락 없이 단일 메시지로 처리

## 환경변수
`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `DESKTOP_PATH`, `GITHUB_USERNAME`
