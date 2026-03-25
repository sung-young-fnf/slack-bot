import os
import re
import asyncio
from pathlib import Path
from slack_bolt import App

from collectors.md_collector import collect_md
from collectors.github_collector import collect_github
from ai.claude import generate_briefing
from formatter.block_kit import build_briefing_blocks

CLAUDE_MD_PATH = Path(__file__).parent.parent.parent / "CLAUDE.md"


def _read_bot_info() -> str:
    try:
        return CLAUDE_MD_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def register_handlers(app: App):
    @app.event("app_mention")
    def handle_mention(event, say, client):
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()

        # 텍스트 없이 멘션만 한 경우
        if not text:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="안녕하세요! 무엇을 도와드릴까요?😊"
            )
            return

        # 즉시 로딩 메시지 응답
        loading_resp = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="답변을 준비하고 있습니다..."
        )
        loading_ts = loading_resp["ts"]

        # 브리핑 요청 여부 판단
        BRIEFING_KEYWORDS = ("브리핑", "할일", "업무", "진행상황")
        is_briefing = any(kw in text for kw in BRIEFING_KEYWORDS)

        # 스킬/기능 질문 여부 판단
        SKILL_KEYWORDS = ("스킬", "스킬셋", "기능", "소개")
        bot_info = _read_bot_info() if any(kw in text for kw in SKILL_KEYWORDS) else ""

        # 특정 프로젝트 지정 여부 파싱
        project_match = re.search(r"(\S+)\s*브리핑", text)
        target_project = None
        if project_match:
            candidate = project_match.group(1)
            if candidate not in ("오늘", "전체"):
                target_project = candidate

        async def _run():
            desktop_path = os.environ.get("DESKTOP_PATH", "")
            projects = await collect_md(desktop_path, target_project)
            projects = await collect_github(projects)
            briefing_text = await generate_briefing(projects, text, bot_info)
            return projects, briefing_text

        try:
            loop = asyncio.new_event_loop()
            projects, briefing_text = loop.run_until_complete(_run())
            loop.close()

            blocks = build_briefing_blocks(briefing_text, projects, is_briefing)

            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=briefing_text[:100] if not is_briefing else "오늘의 개발 브리핑",
                blocks=blocks,
            )
        except Exception as e:
            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=f"브리핑 생성 중 오류가 발생했습니다: {e}",
            )
