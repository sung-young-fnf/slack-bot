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


TASK_PARSE_PROMPT = """사용자의 Slack 메시지를 분석하여 할일 관리 요청인지 판단하세요.

[오늘 날짜]
{today}

[판단 기준 — 매우 중요]
사용자가 TASKS.md에 항목을 추가하거나 완료 처리하려는 의도가 있으면 반드시 "add" 또는 "done"으로 판단하세요.
아래와 같은 표현은 모두 할일 관리 요청입니다:
- "add": "할일 추가", "넣어줘", "작성해줘", "추가해줘", "등록해줘", "올려줘", "task.md에 작성", "할일에 넣어", "pr 올려줘" (할일을 추가하고 PR을 만들라는 의미)
- "done": "끝났어", "다 했어", "완료로", "완료 처리", "완료해줘", "체크해줘"
- "none": 위 의도가 전혀 없는 요청 (브리핑, 질문, 일상 대화 등)

의심스러우면 "add" 또는 "done"으로 판단하세요. "none"은 확실할 때만 사용하세요.

[프로젝트 목록]
{projects}

[항목 추출 규칙 — 매우 중요]
- items에는 실제 할일 내용만 넣으세요. "해줘", "추가", "등록", "올려줘" 같은 명령어는 절대 항목에 포함하지 마세요.
- 사용자가 말하는 작업/업무 내용을 정확히 추출하세요.
- 예시:
  - "slack_bot에 통합 연결 이슈 라고 할일 추가해줘" → action: "add", items: ["통합 연결 이슈"]
  - "slack_bot 프로젝트에 할일 task.md에다가 git pr 자동화 테스트 작성 해줘" → action: "add", items: ["git pr 자동화 테스트 작성"]
  - "에러 핸들링이랑 로깅 추가 해줘" → action: "add", items: ["에러 핸들링", "로깅 추가"]
  - "그냥 테스트용이라 바로 추가 해서 pr 올려줘" → action: "add" (이전 대화에서 항목 추출)
  - "피드백 루프 기획 완료 처리해줘" → action: "done", items: ["피드백 루프 기획"]
  - "오늘 할일 브리핑해줘" → action: "none" (이건 브리핑 요청)

[응답 형식 — 반드시 JSON만 반환]
{{"action": "add" | "done" | "none", "project": "프로젝트명 또는 null", "items": ["항목1", "항목2"], "date": "YYYY-MM-DD 또는 null"}}

- project: 메시지에서 프로젝트를 특정할 수 없으면 null
- items: 추출된 할일 항목 목록. 없으면 빈 배열. 명령어("해줘", "추가", "등록")는 절대 포함하지 말 것.
- date: 사용자가 명시한 날짜가 있으면 YYYY-MM-DD 형식으로 변환. 없으면 null. (예: "3월 31자" → "2026-03-31")
"""


def parse_task_with_ai(text: str, available_projects: list[str], history: list[dict] | None = None) -> dict | None:
    """Claude AI로 할일 관리 요청을 분석한다. 실패 시 None 반환."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    projects_str = ", ".join(available_projects) if available_projects else "없음"
    today_str = date.today().strftime("%Y-%m-%d")
    system = TASK_PARSE_PROMPT.format(projects=projects_str, today=today_str)

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
        result = json.loads(message.content[0].text)
        if result.get("action") == "none":
            return None
        return result
    except Exception:
        return None


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
