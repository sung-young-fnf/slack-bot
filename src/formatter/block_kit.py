def build_briefing_blocks(briefing_text: str, projects: list[dict], is_briefing: bool = True) -> list[dict]:
    blocks = []

    # Header
    header_text = "오늘의 개발 브리핑" if is_briefing else "AI Agent"
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": header_text, "emoji": True}
    })
    blocks.append({"type": "divider"})

    # AI 응답 텍스트
    for chunk in _split_text(briefing_text, 3000):
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": chunk}
        })

    if is_briefing and projects:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*프로젝트 현황*"}
        })

        for p in projects:
            todo_count = len(p.get("todos", []))
            done_count = len(p.get("done", []))
            issues = p.get("issues", [])
            prs = p.get("prs", [])

            summary_lines = [f"*{p['project']}*  할일 {todo_count}건 | 완료 {done_count}건"]

            if issues:
                issue_links = ", ".join(
                    f"<{i['url']}|#{i['number']} {i['title']}>" for i in issues[:3]
                )
                summary_lines.append(f"Issues: {issue_links}")

            if prs:
                pr_links = ", ".join(
                    f"<{pr['url']}|#{pr['number']} {pr['title']}>" for pr in prs[:3]
                )
                summary_lines.append(f"PRs: {pr_links}")

            if p.get("github_error"):
                summary_lines.append("GitHub 정보를 가져올 수 없습니다.")

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(summary_lines)}
            })

    return blocks


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
