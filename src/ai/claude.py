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


def _build_user_prompt(projects: list[dict], user_text: str, bot_info: str = "") -> str:
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
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
                today_done = [d for d in done if d.get("date") == today_str]
                week_done = [d for d in done if d.get("date") and week_ago <= d["date"] < today_str]
                if today_done:
                    lines.append(f"오늘 완료 ({today_str}):")
                    for d in today_done:
                        lines.append(f"  - {d['text']}")
                if week_done:
                    lines.append("최근 7일 내 완료:")
                    for d in week_done:
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


async def generate_briefing(projects: list[dict], user_text: str = "", bot_info: str = "") -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_briefing(projects)

    user_prompt = _build_user_prompt(projects, user_text, bot_info)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
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
