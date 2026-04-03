# Slack Daily Briefing Bot - 구조 리포트

## 개요
Slack 멘션으로 오늘 할일을 AI 브리핑해주는 봇. Desktop 프로젝트의 `TASKS.md`와 GitHub Issues/PR을 수집하여 Claude AI가 분석 후 응답한다. 스레드 내 대화내역을 SQLite에 저장하여 맥락 있는 연속 대화를 지원한다.

## 기술 스택
| 구분 | 기술 |
|------|------|
| 언어 | Python |
| Slack | slack-bolt (Socket Mode) |
| GitHub | PyGithub |
| AI | Anthropic Claude Sonnet 4.6 |
| DB | SQLite (대화내역 저장, 7일 보관) |
| 프로세스 관리 | PM2 |

## 프로젝트 구조
```
src/
├── main.py                    # 엔트리포인트 (22줄)
├── handlers/
│   └── briefing.py            # 멘션 이벤트 핸들러 (90줄)
├── collectors/
│   ├── md_collector.py        # TASKS.md 파싱 (53줄)
│   └── github_collector.py    # GitHub API 수집 (112줄)
├── ai/
│   └── claude.py              # AI 프롬프트 조립 및 호출 (142줄)
├── formatter/
│   └── block_kit.py           # Slack Block Kit 포맷팅 (64줄)
└── storage/
    └── conversation_store.py  # SQLite 대화내역 관리 (79줄)

data/
└── conversations.db           # SQLite DB 파일 (자동 생성, .gitignore)

docs/
├── structure.md               # 구조 리포트 (이 파일)
└── feature_conversation_history.md  # 대화내역 저장 기획서
```

## 동작 흐름
```
@bot 멘션 수신
  → 사용자 메시지 DB 저장
  → 로딩 메시지 즉시 전송
  → 요청 유형 판단 (브리핑 / 스킬셋 / 일반)
  → TASKS.md 수집 → GitHub Issues/PR 수집
  → 스레드 대화내역 조회 (최근 20턴)
  → Claude AI 호출 (대화 맥락 + 현재 질문)
  → 봇 응답 DB 저장
  → Block Kit 포맷팅 → 로딩 메시지를 최종 응답으로 교체
```

## 모듈별 역할

### main.py
- Bolt App 초기화 + Socket Mode 시작
- `register_handlers()`로 이벤트 핸들러 등록
- 앱 시작 시 `init_db()` + `cleanup_old_conversations()` 실행

### handlers/briefing.py
- `app_mention` 이벤트 수신 및 전체 흐름 제어
- 브리핑 키워드 감지: `브리핑`, `할일`, `업무`, `진행상황`
- 봇 소개 키워드 감지: `기능`, `소개` → CLAUDE.md 읽어 전달
- 사용자 메시지 DB 저장 → 스레드 대화내역 조회 → 응답 후 봇 메시지 DB 저장
- `asyncio.new_event_loop()`으로 비동기 수집/생성 실행
- 요청마다 5% 확률로 오래된 대화 자동 정리

### collectors/md_collector.py
- `DESKTOP_PATH` 하위 프로젝트 폴더에서 `TASKS.md` 탐색
- 정규식으로 파싱: `- [ ] 할일` → todos, `- [x] 완료 (날짜)` → done

### collectors/github_collector.py
- `.git/config`에서 remote origin URL 파싱 (HTTPS/SSH)
- Open Issues (assignee 필터) + Open PRs (user 필터) 조회
- 5분 메모리 캐시, `asyncio.gather`로 병렬 조회

### ai/claude.py
- 시스템 프롬프트: 3가지 요청 유형 구분 + 말투 규칙("~해요" 체)
- 사용자 프롬프트 조립: 오늘 날짜, 질문, 프로젝트 데이터
- 완료 항목을 이번주/지난주로 분류하여 전달
- 대화내역(history)을 Claude messages 배열에 포함하여 맥락 유지
- API 실패 시 수집 데이터 원본 텍스트로 fallback

### formatter/block_kit.py
- 브리핑: 헤더 "오늘의 업무 브리핑" + AI 응답 + 프로젝트 현황(할일/완료 건수, Issue/PR 링크)
- 일반 질문: 헤더 "AI Agent" + AI 응답만
- 텍스트 3000자 초과 시 자동 분할

### storage/conversation_store.py
- SQLite 기반 대화내역 CRUD 모듈
- `init_db()`: 테이블 및 인덱스 생성 (앱 시작 시 1회)
- `save_message()`: 채널/스레드/역할/내용 저장 (메시지당 최대 2000자)
- `get_thread_history()`: 스레드별 최근 20턴 대화내역 조회 (Claude messages 형식)
- `cleanup_old_conversations()`: 7일 초과 데이터 삭제
- `maybe_cleanup()`: 5% 확률로 cleanup 실행 (요청마다 호출)
- WAL 모드로 읽기/쓰기 동시성 확보

## 오류 처리
| 상황 | 처리 |
|------|------|
| TASKS.md 없는 프로젝트 | skip |
| .git 없는 폴더 | GitHub 수집 skip |
| GitHub API 실패 | 오류 메시지 표시 후 계속 |
| Claude API 실패 | 수집 데이터 원본 텍스트 전송 |
| 전체 실패 | "브리핑 생성 중 오류가 발생했습니다" |
| DB 저장 실패 | 대화 맥락 없이 단일 메시지로 처리 |

## 기능 목록

### 1. 업무 브리핑
- `@bot 오늘 할일 브리핑` 등으로 호출
- 키워드: `브리핑`, `할일`, `업무`, `진행상황`
- 로컬 프로젝트 TASKS.md에서 할일/완료 항목 수집
- GitHub Open Issues, Open PRs 수집
- Claude AI가 우선순위 분석 후 브리핑 생성
- 프로젝트 현황 요약 (할일/완료 건수, Issue/PR 링크) 함께 표시

### 2. 스킬셋 질문 응답
- `@bot 스킬셋 알려줘` 등으로 호출
- 사전 정의된 SKILLSET_INFO 기반으로만 응답 (AI/ML, 백엔드, 프론트엔드, 인프라)
- 프로젝트 데이터나 도구 기술을 스킬로 언급하지 않음

### 3. 봇 소개/기능 안내
- `@bot 기능 소개해줘` 등으로 호출
- 키워드: `기능`, `소개`
- CLAUDE.md를 읽어 봇 정보로 전달

### 4. 일반 질문 응답
- 위 키워드에 해당하지 않는 자유 질문
- 브리핑 형식 없이 AI가 일반 대화로 응답
- 프로젝트 관련 내용 언급하지 않음

### 5. 빈 멘션 처리
- `@bot` 만 입력 시 인사 응답 반환

### 6. 완료 항목 주간 분류
- TASKS.md의 완료 항목을 이번주/지난주로 자동 분류
- 월요일 기준으로 주 구분, 2주 이상 지난 항목은 제외

### 7. GitHub 데이터 캐싱
- GitHub API 응답을 5분간 메모리 캐시
- 반복 요청 시 API 호출 절감

### 8. 오류 시 Fallback
- Claude API 실패 시 수집 데이터 원본 텍스트로 대체 응답
- GitHub API 실패 시 오류 표시 후 나머지 데이터로 계속 진행

### 9. 대화내역 저장 및 맥락 유지
- 스레드 단위로 대화내역을 SQLite에 저장
- 동일 스레드 내 후속 질문 시 이전 대화 맥락 반영
- 스레드당 최대 20턴, 메시지당 2000자 제한
- 7일 경과 데이터 자동 삭제

## 환경변수
`SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `DESKTOP_PATH`, `GITHUB_USERNAME`
