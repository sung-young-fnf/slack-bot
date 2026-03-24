import os
import anthropic

SYSTEM_PROMPT = """당신은 개발자의 일일 업무 브리핑을 도와주는 어시스턴트입니다.
주어진 프로젝트별 할일 목록과 GitHub 이슈/PR 정보를 바탕으로
오늘 집중해야 할 작업을 한국어로 간결하게 브리핑해주세요.

출력 형식:
1. 오늘의 우선순위 Top 3 (전체 프로젝트 통합)
2. 프로젝트별 할일 요약
3. 처리가 필요한 GitHub 이슈/PR
4. 한 줄 코멘트"""


def _build_user_prompt(projects: list[dict]) -> str:
    lines = []
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


async def generate_briefing(projects: list[dict]) -> str:
    if not projects:
        return "수집된 프로젝트 데이터가 없습니다."

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_briefing(projects)

    user_prompt = _build_user_prompt(projects)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
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
