import os
from datetime import date, timedelta
import anthropic

SKILLSET_INFO = """
AI/LLM 개발 분야는 RAG 시스템과 LLM 프롬프트 엔지니어링을 중심으로 기초적인 AI 서비스 개발이 가능한 초급 수준입니다.
백엔드 쪽은 FastAPI를 활용한 간단한 API 구현이 가능한 수준입니다.
프론트엔드는 React를 이용한 기초적인 화면 구성과 백엔드 API 연동 정도가 가능합니다.
인프라는 Docker와 AWS를 활용해본 정도로, 간단한 배포 환경 구성이 가능한 수준입니다.

기술 스택
AI/ML: Python, PyTorch
백엔드: FastAPI, Redis, PostgreSQL, MySQL
프론트엔드: React
클라우드/인프라: AWS(EC2, S3), Firebase, Docker
"""

SYSTEM_PROMPT = f"""당신은 개발자를 위한 Slack AI 어시스턴트입니다. 모든 답변은 한국어로 작성합니다.

[말투]
- 모든 답변에서 "~해요", "~예요", "~있어요" 체를 일관되게 사용하세요.
- "~합니다", "~습니다" 같은 격식체와 "~해", "~야" 같은 반말은 사용하지 마세요.

[핵심 규칙]
- 사용자의 요청 유형(브리핑 / 스킬셋 질문 / 일반 질문)을 먼저 판단하세요.

--------------------------------------------------
1️⃣ 브리핑 요청인 경우 (예: 오늘 할일, 업무 브리핑, 진행 상황 정리 등)

- 제공된 프로젝트 데이터를 바탕으로 자유롭게 구성하세요.
- 형식은 고정하지 않고, 데이터 내용과 맥락에 맞게 AI가 판단하여 구성하세요.
- 핵심 정보(완료 항목, 진행 중 항목, GitHub 현황 등)를 자연스럽게 담되, 불필요한 항목은 생략해도 됩니다.
- 각 항목은 너무 길지 않게 핵심만 정리하세요.

--------------------------------------------------
2️⃣ 스킬셋 / 기능 질문인 경우

[매우중요] 아래 SKILLSET_INFO에 명시된 내용만 말하세요. 프로젝트 데이터, TASKS.md, 현재 대화에서 보이는 도구/기술(PM2, 작업 스케줄러, Slack SDK 등)은 절대 스킬로 언급하지 마세요.
스킬, 스킬셋을 물어보면 castle의 스킬셋이라고 설명하세요 

{SKILLSET_INFO}

--------------------------------------------------
3️⃣ 일반 질문 또는 일상 대화

- 브리핑 형식을 절대 사용하지 마세요.
- [매우중요] 일반 질문 시에는 프로젝트 관련 내용을 얘기하지 마세요.

--------------------------------------------------

[금지 사항]
- 일반 질문에 브리핑 형식을 섞지 말 것
- 불필요하게 길거나 장황한 답변 금지
"""


import json


CLASSIFY_PROMPT = """당신은 Slack 봇의 요청 분류기입니다. 사용자 메시지의 의도를 정확히 판단하세요.

[오늘 날짜]
{today}

[요청 유형 — 이 순서대로 판단하세요]

1. "task_add" — 사용자가 TASKS.md에 새 할일 항목을 추가하길 원함
   핵심: "task.md", "할일", "태스크"와 함께 "추가", "작성", "넣어", "등록", "올려" 등의 동작이 있으면 task_add
   예시:
   - "slack_bot에 task.md에 할일을 작성해줘 할일 제목은 git pr자동화 테스트로"
   - "할일 추가해줘 — API 에러 핸들링"
   - "slack_bot에 통합 연결 이슈 할일 추가해줘"
   - "task.md에다가 git pr 자동화 테스트 작성 해줘"
   - "이거 할일에 넣어줘"
   - "바로 추가 해서 pr 올려줘"

2. "task_done" — 사용자가 TASKS.md의 기존 할일을 완료 처리하길 원함
   예시: "끝났어", "다 했어", "완료로 처리해줘", "완료해줘", "체크해줘"

3. "briefing" — 업무 현황, 할일 브리핑, 진행상황 요약 요청
   핵심: 현재 상태를 "보여줘/알려줘/정리해줘"이고, 새로 추가하거나 변경하는 게 아닌 경우
   예시: "오늘 할일 브리핑", "업무 정리해줘", "진행상황 알려줘", "할일 뭐 있어?"

4. "general" — 위 어디에도 해당하지 않는 일반 질문/대화
   예시: "파이썬에서 데코레이터가 뭐야?", "스킬셋 알려줘", "기능 소개해줘"

[중요] "task.md에 작성", "할일 작성", "할일 추가", "할일 등록" 등의 표현이 있으면 반드시 "task_add"입니다. "general"이 아닙니다.

[프로젝트 목록]
{projects}

[항목 추출 규칙 — task_add / task_done인 경우]
- items에는 실제 할일 내용만 넣으세요.
- "해줘", "추가", "등록", "올려줘", "작성해줘" 같은 명령어는 항목에 포함하지 마세요.
- "할일 제목은 XXX로" → items: ["XXX"]
- "XXX이랑 YYY 추가해줘" → items: ["XXX", "YYY"]

[응답 형식 — 반드시 JSON만 반환. 설명 없이 JSON만.]
{{"type": "task_add" | "task_done" | "briefing" | "general", "project": "프로젝트명 또는 null", "items": ["항목1"], "date": "YYYY-MM-DD 또는 null"}}
"""


def classify_request(text: str, available_projects: list[str], history: list[dict] | None = None) -> dict:
    """Claude AI로 요청 유형을 분류한다. 실패 시 기본값 반환."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"type": "general", "project": None, "items": [], "date": None}

    projects_str = ", ".join(available_projects) if available_projects else "없음"
    today_str = date.today().strftime("%Y-%m-%d")
    system = CLASSIFY_PROMPT.format(projects=projects_str, today=today_str)

    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": text})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=system,
            messages=messages,
        )
        raw = message.content[0].text.strip()
        # ```json ... ``` 코드블록 제거
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3].strip()
        return json.loads(raw)
    except Exception:
        return {"type": "general", "project": None, "items": [], "date": None}


def _build_user_prompt(projects: list[dict], user_text: str, bot_info: str = "") -> str:
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    this_monday = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    last_monday = (today - timedelta(days=today.weekday() + 7)).strftime("%Y-%m-%d")
    lines = [f"[오늘 날짜]\n{today_str}\n", f"[사용자 질문]\n{user_text}\n"]

    if bot_info:
        lines.append(f"[봇 정보 - 스킬/기능 질문 시 참고]\n{bot_info}\n")

    if projects:
        lines.append("[프로젝트 데이터]")
        for p in projects:
            lines.append(f"[프로젝트: {p['project']}]")
            todos = p.get("todos", [])
            done = p.get("done", [])
            issues = p.get("issues", [])
            prs = p.get("prs", [])

            if todos:
                lines.append("할일:")
                for t in todos:
                    lines.append(f"  - {t}")
            if done:
                this_week_done = [d for d in done if d.get("date") and d["date"] >= this_monday]
                last_week_done = [d for d in done if d.get("date") and last_monday <= d["date"] < this_monday]
                if this_week_done:
                    lines.append("이번주 완료:")
                    for d in this_week_done:
                        lines.append(f"  - {d['text']} ({d['date']})")
                if last_week_done:
                    lines.append("지난주 완료:")
                    for d in last_week_done:
                        lines.append(f"  - {d['text']} ({d['date']})")
            if issues:
                lines.append("GitHub Issues:")
                for issue in issues:
                    lines.append(f"  - #{issue['number']} {issue['title']} ({issue['url']})")
            if prs:
                lines.append("GitHub PRs:")
                for pr in prs:
                    lines.append(f"  - #{pr['number']} {pr['title']} ({pr['url']})")
            if p.get("github_error"):
                lines.append(f"  (GitHub 정보를 가져올 수 없습니다: {p['github_error']})")
            lines.append("")

    return "\n".join(lines)


async def generate_briefing(
    projects: list[dict], user_text: str = "", bot_info: str = "", history: list[dict] | None = None
) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_briefing(projects)

    user_prompt = _build_user_prompt(projects, user_text, bot_info)

    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return message.content[0].text
    except Exception as e:
        return _fallback_briefing(projects, error=str(e))


def _fallback_briefing(projects: list[dict], error: str | None = None) -> str:
    lines = []
    if error:
        lines.append(f"(Claude API 오류: {error})\n")
    for p in projects:
        lines.append(f"[{p['project']}]")
        for t in p.get("todos", []):
            lines.append(f"  - [ ] {t}")
        lines.append("")
    return "\n".join(lines)
