# 대화내역 저장 기능 기획서

## 1. 개요

| 항목 | 내용 |
|------|------|
| **기능명** | 대화내역 저장 (Conversation History) |
| **목적** | 봇과의 대화 맥락을 유지하여 연속적인 질문/답변이 가능하도록 함 |
| **보관 기간** | 7일 (자동 삭제) |
| **작성일** | 2026-04-03 |

## 2. 현재 상태 (As-Is)

- 봇은 **완전 stateless** — 매 멘션마다 독립적인 요청으로 처리
- Claude API 호출 시 `messages`에 단일 user 메시지만 전달
- 이전 대화 맥락을 전혀 알 수 없어 "아까 말한 거" 같은 후속 질문 불가
- 저장소/DB 없음, GitHub 캐시만 5분 TTL 메모리 캐시

## 3. 목표 상태 (To-Be)

- 동일 Slack 스레드 내 대화를 맥락으로 유지
- 7일이 지난 대화내역은 자동 정리
- Claude API 호출 시 이전 대화를 `messages` 배열에 포함하여 맥락 있는 응답 생성
- "아까 말한 프로젝트", "그거 좀 더 자세히" 같은 후속 질문 처리 가능

## 4. 저장소 설계

### 4.1 저장소 선택: SQLite

| 후보 | 장점 | 단점 | 결정 |
|------|------|------|------|
| **SQLite** | 설치 불필요, 파일 기반, Python 내장 | 동시 쓰기 제한 | **채택** |
| JSON 파일 | 단순 | 동시성 문제, 검색 느림 | 기각 |
| Redis | 빠름, TTL 내장 | 별도 서버 필요 | 기각 |
| PostgreSQL | 확장성 | 과도한 인프라 | 기각 |

> 단일 사용자 봇이므로 SQLite로 충분. 향후 다중 사용자 확장 시 Redis/PostgreSQL 고려.

### 4.2 테이블 스키마

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_ts   TEXT NOT NULL,          -- Slack 스레드 타임스탬프 (대화 그룹 키)
    channel_id  TEXT NOT NULL,          -- Slack 채널 ID
    role        TEXT NOT NULL,          -- 'user' | 'assistant'
    content     TEXT NOT NULL,          -- 메시지 본문
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_thread ON conversations(channel_id, thread_ts);
CREATE INDEX idx_created ON conversations(created_at);
```

### 4.3 파일 위치

```
data/conversations.db    # .gitignore에 추가
```

## 5. 구현 계획

### 5.1 신규 파일

```
src/
└── storage/
    ├── __init__.py
    └── conversation_store.py   # SQLite CRUD + 7일 정리
```

### 5.2 `conversation_store.py` 주요 함수

```python
# 초기화 — 앱 시작 시 1회 호출
def init_db() -> None

# 메시지 저장
def save_message(channel_id: str, thread_ts: str, role: str, content: str) -> None

# 스레드별 대화내역 조회 (Claude messages 형식으로 반환)
def get_thread_history(channel_id: str, thread_ts: str) -> list[dict]
# 반환 예: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

# 7일 초과 데이터 삭제
def cleanup_old_conversations(days: int = 7) -> int  # 삭제된 행 수 반환
```

### 5.3 기존 파일 수정

#### `src/main.py`
```python
# 추가
from storage.conversation_store import init_db, cleanup_old_conversations

# 앱 시작 시
init_db()
cleanup_old_conversations()  # 시작할 때 1회 정리
```

#### `src/handlers/briefing.py`
```python
# 추가
from storage.conversation_store import save_message, get_thread_history

# handle_mention 내부 흐름 변경:
# 1. 사용자 메시지 저장: save_message(channel, thread_ts, "user", text)
# 2. 대화내역 조회: history = get_thread_history(channel, thread_ts)
# 3. generate_briefing에 history 전달
# 4. 응답 저장: save_message(channel, thread_ts, "assistant", briefing_text)
```

#### `src/ai/claude.py`
```python
# generate_briefing 시그니처 변경
async def generate_briefing(
    projects, user_text, bot_info="", history=None
) -> str:

# Claude API 호출 시 messages 구성
messages = []
if history:
    messages.extend(history)       # 이전 대화 맥락
messages.append({"role": "user", "content": user_prompt})  # 현재 요청
```

## 6. 데이터 정리 (Cleanup) 전략

| 방식 | 시점 | 설명 |
|------|------|------|
| **앱 시작 시** | `main.py` 초기화 | PM2 재시작마다 오래된 데이터 정리 |
| **매 요청 시** | 확률적 실행 (1/20) | 매번이 아닌 약 5% 확률로 cleanup 호출하여 부하 최소화 |

```python
import random

def maybe_cleanup():
    if random.random() < 0.05:  # 5% 확률
        cleanup_old_conversations(days=7)
```

## 7. Claude API 토큰 관리

### 7.1 문제
- 대화가 길어지면 토큰 비용 증가 및 max_tokens 초과 가능
- 현재 모델: `claude-sonnet-4-6`, max input ~200K tokens

### 7.2 대응 방안

| 제한 | 값 | 설명 |
|------|-----|------|
| 스레드당 최대 저장 턴 수 | **20턴** (user+assistant 각 1턴) | 오래된 턴부터 잘림 |
| 메시지당 최대 저장 길이 | **2000자** | 긴 브리핑은 요약 후 저장 |

```python
def get_thread_history(channel_id, thread_ts, max_turns=20):
    # 최근 max_turns * 2 개 행만 조회 (user + assistant)
    ...
```

## 8. 동작 흐름 (변경 후)

```
1. @bot 멘션 수신
2. 사용자 메시지 DB 저장 (user)
3. "답변 준비 중..." 로딩 메시지
4. 병렬 데이터 수집 (md + github)
5. DB에서 스레드 대화내역 조회 (최근 20턴)
6. Claude API 호출 (history + 현재 질문)
7. 응답 텍스트 DB 저장 (assistant)
8. Block Kit 포맷팅 → 메시지 업데이트
```

## 9. 예상 사용 시나리오

### 시나리오 1: 후속 질문
```
사용자: @bot 오늘 할일 브리핑
봇:     [브리핑 내용...]

사용자: @bot slack_bot 프로젝트 좀 더 자세히 알려줘
봇:     [이전 브리핑 맥락을 기억하고 해당 프로젝트 상세 설명]
```

### 시나리오 2: 맥락 기반 대화
```
사용자: @bot GitHub PR 중에 급한 거 있어?
봇:     [PR 분석...]

사용자: @bot 그거 리뷰 포인트 정리해줘
봇:     ["그거"가 위에서 언급한 PR임을 이해하고 리뷰 포인트 정리]
```

## 10. 구현 일정 (예상)

| 단계 | 작업 | 예상 소요 |
|------|------|-----------|
| Step 1 | `conversation_store.py` 작성 + 테스트 | 1시간 |
| Step 2 | `briefing.py` 수정 — 저장/조회 연동 | 30분 |
| Step 3 | `claude.py` 수정 — history 반영 | 30분 |
| Step 4 | `main.py` 초기화 + cleanup 연동 | 15분 |
| Step 5 | 통합 테스트 (실제 Slack 메시지) | 30분 |
| Step 6 | PM2 배포 + 모니터링 | 15분 |

## 11. 고려사항 / 리스크

| 항목 | 대응 |
|------|------|
| SQLite 파일 손상 | `data/` 디렉토리 백업 또는 손상 시 자동 재생성 |
| 토큰 비용 증가 | 최대 턴 수 제한 (20턴), 메시지 길이 제한 (2000자) |
| 개인정보 | 대화내용이 로컬 파일에 저장됨 — 서버 접근 관리 필요 |
| 동시 요청 | SQLite WAL 모드 활성화로 읽기/쓰기 동시성 개선 |

## 12. .gitignore 추가

```
# Conversation DB
data/
```
