# 반자동화 코드 수정 & PR 생성 기획서

## 1. 개요

| 항목 | 내용 |
|------|------|
| **기능명** | Slack 멘션 기반 코드 수정 & PR 자동 생성 |
| **목적** | 브리핑에서 확인한 할일을 Slack에서 바로 지시하면, 봇이 코드 변경 계획을 제안하고 승인 후 브랜치/PR을 자동 생성 |
| **방식** | 반자동화 (계획 제안 → 사용자 승인 → 실행) |
| **작성일** | 2026-04-03 |

## 2. 대상 프로젝트

`DESKTOP_PATH` 하위 디렉토리를 스캔하여 `TASKS.md`가 존재하는 프로젝트를 **자동으로** 작업 대상으로 인식한다. 고정 목록이 아니라 새 프로젝트 폴더에 `TASKS.md`를 추가하면 자동으로 대상에 포함된다.

### 프로젝트 인식 규칙
- `DESKTOP_PATH` 하위 디렉토리를 스캔
- `TASKS.md`가 존재하면 작업 대상 프로젝트로 자동 인식
- `.git`이 존재하는 프로젝트만 브랜치/PR 생성 가능 (`.git` 없으면 코드 수정만 가능, PR 불가)
- 프로젝트가 추가/삭제되면 별도 설정 없이 자동 반영
- 사용자가 프로젝트를 명시하지 않으면 대화 맥락에서 추론, 추론 불가 시 확인 질문

### 프로젝트 지정 방식
```
명시적: @bot slack_bot에서 로깅 추가해줘
맥락:   @bot 아까 브리핑에서 나온 그 할일 작업해줘  → 대화 맥락에서 프로젝트 추론
미지정: @bot API 타임아웃 수정해줘  → "어떤 프로젝트인지 알려주세요" 확인 질문
```

## 3. 사용자 시나리오

### 시나리오 A: 단순 작업 (설정/문서 변경)
```
사용자: @bot 오늘 할일 브리핑
봇:     [브리핑 결과 — "API 타임아웃 30초로 변경" 할일 포함]

사용자: @bot "API 타임아웃 30초로 변경" 작업해줘
봇:     📋 변경 계획
        ─────────────
        대상: src/config.py
        변경: API_TIMEOUT = 10 → API_TIMEOUT = 30
        브랜치: fix/api-timeout-30s
        ─────────────
        진행하시겠어요? (승인 / 취소)

사용자: @bot 승인
봇:     ✅ 완료!
        브랜치: fix/api-timeout-30s
        PR: https://github.com/user/repo/pull/42
```

### 시나리오 B: 코드 변경
```
사용자: @bot slack_bot에 로깅 미들웨어 추가해줘
봇:     📋 변경 계획
        ─────────────
        1. src/main.py — Bolt 미들웨어 등록 추가
        2. src/middleware/logging.py — (신규) 요청/응답 로깅 미들웨어
        브랜치: feat/logging-middleware

        [변경 미리보기]
        ```diff
        # src/main.py
        + from middleware.logging import LoggingMiddleware
        + app.use(LoggingMiddleware())
        ```
        ─────────────
        진행하시겠어요? (승인 / 수정 요청 / 취소)

사용자: @bot 수정 — 로그 레벨은 INFO로 해줘
봇:     📋 수정된 계획
        [업데이트된 diff 미리보기...]
        진행하시겠어요? (승인 / 수정 요청 / 취소)

사용자: @bot 승인
봇:     ✅ 완료! PR: https://github.com/user/repo/pull/43
```

### 시나리오 C: TASKS.md 할일 추가
```
사용자: @bot slack_bot에 할일 추가해줘 — "에러 로깅 미들웨어 추가", "README 업데이트"
봇:     📝 할일 추가 완료!
        ─────────────
        📁 프로젝트: slack_bot
        추가된 항목:
          - [ ] 에러 로깅 미들웨어 추가
          - [ ] README 업데이트
        ─────────────
```

### 시나리오 D: TASKS.md 할일 완료 처리
```
사용자: @bot slack_bot에서 "에러 로깅 미들웨어 추가" 완료 처리해줘
봇:     ✅ 완료 처리했어요!
        ─────────────
        📁 프로젝트: slack_bot
        - [x] 에러 로깅 미들웨어 추가 (2026-04-03)
        ─────────────
```

## 4. 동작 흐름

### 4-A. TASKS.md 관리 (할일 추가/완료)

```
@bot "XXX 할일 추가해줘" 또는 "XXX 완료 처리해줘" 멘션 수신
  → 키워드 감지 ("할일 추가", "추가해줘", "완료 처리", "완료해줘")
  → 대상 프로젝트 식별
  → TASKS.md 파일 읽기
  → 추가: "- [ ] {할일}" 항목 append
  → 완료: "- [ ] {항목}" → "- [x] {항목} (오늘날짜)" 로 변경
  → 파일 저장
  → Slack에 결과 메시지 전송
```

> 승인 단계 없이 **즉시 실행**. TASKS.md 수정은 텍스트 한 줄 추가/변경이라 리스크가 낮음.

### 4-B. 코드 수정 & PR 생성 (반자동화)

```
Phase 1: 요청 분석
─────────────────────
@bot "XXX 작업해줘" 멘션 수신
  → 작업 요청 키워드 감지 ("작업해줘", "수정해줘", "코드 변경", "변경해줘")
  → 대상 프로젝트 식별 (대화 맥락 또는 명시적 지정)
  → 대상 프로젝트 소스코드 읽기

Phase 2: 계획 생성
─────────────────────
  → Claude API 호출 (코드 분석 + 변경 계획 생성)
  → 변경 대상 파일, diff 미리보기, 브랜치명 제안
  → Slack에 계획 메시지 전송
  → 계획 상태를 DB에 저장 (status: pending_approval)

Phase 3: 승인 대기
─────────────────────
  → 사용자 응답 대기 (승인 / 수정 요청 / 취소)
  → "수정 요청" 시 Phase 2로 돌아가 계획 재생성
  → "취소" 시 작업 종료
  → "승인" 시 Phase 4로 진행

Phase 4: 실행
─────────────────────
  → git checkout -b {브랜치명}
  → Claude API로 실제 코드 생성
  → 파일 쓰기 + git add + git commit
  → git push origin {브랜치명}
  → GitHub API로 PR 생성
  → Slack에 PR 링크 전송
  → 계획 상태 업데이트 (status: completed)
```

## 5. 저장소 설계

### 4.1 기존 conversations 테이블 활용 + 신규 테이블 추가

```sql
CREATE TABLE IF NOT EXISTS code_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_ts     TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    project_name  TEXT NOT NULL,           -- 대상 프로젝트명
    request_text  TEXT NOT NULL,           -- 사용자 원본 요청
    plan_json     TEXT,                    -- 변경 계획 (JSON)
    branch_name   TEXT,                    -- 생성된 브랜치명
    pr_url        TEXT,                    -- 생성된 PR URL
    status        TEXT DEFAULT 'planning', -- planning → pending_approval → approved → executing → completed / cancelled / failed
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 plan_json 구조

```json
{
  "branch_name": "fix/api-timeout-30s",
  "commit_message": "Fix: API 타임아웃을 30초로 변경",
  "changes": [
    {
      "file_path": "src/config.py",
      "action": "modify",
      "description": "API_TIMEOUT 값을 10에서 30으로 변경",
      "diff_preview": "- API_TIMEOUT = 10\n+ API_TIMEOUT = 30"
    },
    {
      "file_path": "src/middleware/logging.py",
      "action": "create",
      "description": "요청/응답 로깅 미들웨어 신규 생성",
      "diff_preview": "+ class LoggingMiddleware:\n+     ..."
    }
  ]
}
```

## 6. 구현 계획

### 6.1 신규 파일

```
src/
├── handlers/
│   ├── task_manager.py        # TASKS.md 할일 추가/완료 핸들러
│   └── code_task.py           # 코드 작업 요청 핸들러
├── ai/
│   └── code_planner.py        # 코드 분석 + 변경 계획 생성
├── executor/
│   ├── __init__.py
│   ├── git_manager.py         # git 브랜치/커밋/푸시 관리
│   └── code_writer.py         # Claude 생성 코드 → 파일 쓰기
└── storage/
    └── code_task_store.py     # code_tasks 테이블 CRUD
```

### 6.2 기존 파일 수정

| 파일 | 변경 내용 |
|------|-----------|
| `main.py` | `register_task_manager_handlers()`, `register_code_task_handlers()` 등록 |
| `handlers/briefing.py` | 요청 유형별 라우팅 (할일 관리 / 코드 작업 / 기존 브리핑) |
| `storage/conversation_store.py` | `init_db()`에 `code_tasks` 테이블 생성 추가 |

### 6.3 모듈별 역할

#### `handlers/task_manager.py`
- 할일 추가 감지: "할일 추가", "태스크 추가", "할일 등록"
- 완료 처리 감지: "완료 처리", "완료해줘", "체크해줘"
- 대상 프로젝트 TASKS.md 파일 읽기/쓰기
- 추가: 파일 끝에 `- [ ] {할일}` 항목 append
- 완료: `- [ ] {항목}` → `- [x] {항목} (오늘날짜)` 변환
- 승인 없이 즉시 실행 (리스크 낮음)

#### `handlers/code_task.py`
- 코드 작업 요청 감지: "작업해줘", "수정해줘", "코드 변경", "변경해줘"
- 승인/취소/수정 요청 감지: "승인", "취소", "수정"
- 전체 흐름 제어 (계획 → 승인 → 실행)

#### `ai/code_planner.py`
- 대상 프로젝트 소스코드 읽기 (파일 목록 + 주요 파일 내용)
- Claude API로 변경 계획 생성 (plan_json 형식)
- Claude API로 실제 코드 생성 (승인 후)
- 별도 시스템 프롬프트: 코드 생성 전문

#### `executor/git_manager.py`
- `git checkout -b {branch}` — 브랜치 생성
- `git add` + `git commit -m {message}` — 커밋
- `git push origin {branch}` — 푸시
- 작업 완료 후 원래 브랜치로 복귀
- subprocess 기반, 대상 프로젝트 경로에서 실행

#### `executor/code_writer.py`
- plan_json의 changes를 순회하며 파일 생성/수정
- `action: "create"` → 파일 신규 생성
- `action: "modify"` → 기존 파일 읽기 + Claude가 생성한 코드로 교체
- `action: "delete"` → 파일 삭제

#### `storage/code_task_store.py`
- `create_task()` — 새 작업 생성
- `update_plan()` — 계획 저장/업데이트
- `update_status()` — 상태 변경
- `get_pending_task()` — 스레드의 대기 중 작업 조회

## 7. 안전장치

### 6.1 승인 기반 실행
- 모든 코드 변경은 **반드시 사용자 승인 후** 실행
- 계획 단계에서 diff 미리보기를 반드시 제공
- 승인 없이 10분 경과 시 자동 취소

### 6.2 작업 범위 제한

| 제한 항목 | 값 | 이유 |
|-----------|-----|------|
| 변경 가능 파일 수 | 최대 5개 | 대규모 변경 방지 |
| 파일당 변경 라인 수 | 최대 100줄 | 품질 보장 가능 범위 |
| 신규 파일 생성 수 | 최대 2개 | scope 폭발 방지 |
| 삭제 작업 | 불가 | 안전 우선 (파일 삭제는 수동으로) |

### 6.3 브랜치 보호
- `main`, `master` 브랜치에 직접 커밋 불가
- 반드시 새 브랜치에서 작업
- 브랜치명 자동 생성: `{type}/{short-description}` (예: `fix/api-timeout`)

### 6.4 롤백
- 실행 실패 시 생성된 브랜치 자동 삭제
- 로컬 변경사항 `git checkout .`으로 원복
- 실패 사유를 Slack에 전달

## 8. Claude 프롬프트 설계

### 7.1 계획 생성 프롬프트 (Phase 2)

```
당신은 코드 변경 계획을 세우는 시니어 개발자입니다.

[규칙]
- 사용자 요청을 분석하여 최소한의 변경으로 구현하세요.
- 반드시 JSON 형식으로 plan을 반환하세요.
- 변경 파일은 5개 이하로 제한하세요.
- 각 변경에 diff_preview를 포함하세요.
- 기존 코드 스타일과 패턴을 따르세요.

[프로젝트 소스코드]
{project_files}

[사용자 요청]
{request_text}

[이전 대화 맥락]
{conversation_history}
```

### 7.2 코드 생성 프롬프트 (Phase 4)

```
당신은 코드를 작성하는 개발자입니다.

[규칙]
- 승인된 변경 계획에 따라 정확히 코드를 작성하세요.
- 파일 전체 내용을 반환하세요 (부분 변경 아님).
- 기존 코드 스타일, 들여쓰기, 네이밍 규칙을 따르세요.
- 불필요한 변경을 하지 마세요.

[변경 계획]
{plan_json}

[기존 파일 내용]
{existing_file_contents}
```

## 9. Slack 메시지 포맷

### 8.1 계획 제안 메시지
```
📋 변경 계획
━━━━━━━━━━━━━━━━━━
📁 프로젝트: slack_bot
🌿 브랜치: fix/api-timeout-30s

변경 사항:
1. `src/config.py` — API_TIMEOUT 값 변경
   ```diff
   - API_TIMEOUT = 10
   + API_TIMEOUT = 30
   ```

━━━━━━━━━━━━━━━━━━
👉 승인 → 작업 실행
👉 수정 요청 → 계획 재수정
👉 취소 → 작업 취소
```

### 8.2 완료 메시지
```
✅ 코드 수정 & PR 생성 완료!
━━━━━━━━━━━━━━━━━━
🌿 브랜치: fix/api-timeout-30s
📝 커밋: "Fix: API 타임아웃을 30초로 변경"
🔗 PR: https://github.com/user/repo/pull/42
━━━━━━━━━━━━━━━━━━
```

## 10. 적합한 작업 유형

### 즉시 실행 (승인 불필요)
- TASKS.md 할일 추가
- TASKS.md 완료 처리 (체크박스 업데이트)

### 승인 후 실행 (코드 변경)
- 설정값 변경 (타임아웃, 포트, 환경변수 등)
- 간단한 함수 추가/수정
- 에러 핸들링 추가
- 로깅 추가
- 간단한 리팩토링 (변수명 변경, 함수 분리 등)

### 비권장 (사용자에게 안내 후 거절)
- 대규모 아키텍처 변경
- 새 프레임워크/라이브러리 도입
- DB 스키마 마이그레이션
- 보안 관련 코드 (인증/인가)
- 5개 파일 초과 변경이 필요한 작업

## 11. 구현 일정 (예상)

| 단계 | 작업 | 예상 소요 |
|------|------|-----------|
| Step 1 | `code_task_store.py` — DB 테이블 + CRUD | 1시간 |
| Step 2 | `code_planner.py` — 계획 생성 프롬프트 + 파싱 | 2시간 |
| Step 3 | `git_manager.py` — 브랜치/커밋/푸시/PR | 2시간 |
| Step 4 | `code_writer.py` — 파일 쓰기 로직 | 1시간 |
| Step 5 | `code_task.py` — 핸들러 + 상태 머신 | 2시간 |
| Step 6 | Block Kit 메시지 포맷팅 | 1시간 |
| Step 7 | 통합 테스트 | 2시간 |
| Step 8 | PM2 배포 + 모니터링 | 30분 |

## 12. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| AI 생성 코드 품질 | 승인 단계에서 diff 확인 필수, 파일/라인 수 제한 |
| 빌드 실패 코드 PR | PR description에 "AI 생성 — 리뷰 필수" 라벨 추가 |
| git 충돌 | 최신 main에서 브랜치 생성, 충돌 시 사용자에게 알림 |
| 권한 문제 | GITHUB_TOKEN에 repo 쓰기 권한 필요 (이미 설정됨) |
| 동시 작업 요청 | 스레드당 1개 작업만 허용, 진행 중 작업 있으면 안내 |
