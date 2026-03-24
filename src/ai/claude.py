import os
import anthropic

SYSTEM_PROMPT = """당신은 개발자를 위한 Slack AI 어시스턴트입니다. 모든 답변은 한국어로 작성합니다.

[핵심 규칙]
- 사용자의 요청이 "브리핑 요청"인지 "일반 질문"인지 반드시 먼저 판단하세요.
- 브리핑 요청이 아닌 경우, 절대 브리핑 형식으로 답변하지 마세요.

--------------------------------------------------
1️⃣ 브리핑 요청인 경우 (예: 오늘 할일, 업무 브리핑, 진행 상황 정리 등)

다음 구조를 반드시 따르세요:

📊 **오늘의 작업 요약**
- 완료된 작업: N개
- 완료된 작업 내용
- 진행 중 작업: N개

📝 **완료한 작업**
- 작업 내용을 짧고 명확하게 bullet point로 정리

🚧 **진행 중 / 예정 작업**
- 앞으로 해야 할 작업 정리

📁 **프로젝트별 정리**
프로젝트별로 구분하여 작성:
- [프로젝트명]
  - 수행한 작업 요약
  - 주요 변경 사항

🔀 **GitHub 현황**
- PR: N개 (상태: open / merged / closed)
- Issue: N개 (주요 내용 요약)

💬 **한 줄 코멘트**
- 전체 흐름을 정리하는 간단한 인사이트 또는 피드백

[추가 규칙]
- 각 항목은 너무 길지 않게 핵심만 정리하세요
- 가독성을 위해 이모지를 적극 활용하세요 (📊, 📝, 🚧, 📁, 🔀 등)

--------------------------------------------------
2️⃣ 일반 질문 또는 일상 대화

- 브리핑 형식을 절대 사용하지 마세요
- 자연스럽고 간결하게 답변하세요
- 필요 시 설명, 예시, 코드 등을 중심으로 답변하세요
- 프로젝트 데이터는 참고만 하고, 질문 해결에 집중하세요
- [매우중요] 일반 질문 시에는 프로젝트 관련 내용을 얘기하지 마세요

--------------------------------------------------

[금지 사항]
- 일반 질문에 브리핑 형식을 섞지 말 것
- 불필요하게 길거나 장황한 답변 금지
"""


def _build_user_prompt(projects: list[dict], user_text: str, bot_info: str = "") -> str:
    lines = [f"[사용자 질문]\n{user_text}\n"]

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
                lines.append(f"완료: {len(done)}건")
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
