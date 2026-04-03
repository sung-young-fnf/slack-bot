import os
import re
import asyncio
from pathlib import Path
from slack_bolt import App

from collectors.md_collector import collect_md
from collectors.github_collector import collect_github
from ai.claude import generate_briefing, parse_task_with_ai
from formatter.block_kit import build_briefing_blocks
from storage.conversation_store import save_message, get_thread_history, maybe_cleanup
from handlers.task_manager import is_task_management, handle_task_management, _list_projects

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

        # 할일 관리 요청 (TASKS.md 추가/완료) — 승인 없이 즉시 실행
        # 1차: 키워드 매칭, 2차: AI 판단
        desktop_path = os.environ.get("DESKTOP_PATH", "")
        is_task_req = is_task_management(text)
        if not is_task_req:
            available_projects = _list_projects(desktop_path)
            ai_result = parse_task_with_ai(text, available_projects)
            if ai_result:
                is_task_req = True

        if is_task_req:
            result_text = handle_task_management(text, desktop_path)
            save_message(channel, thread_ts, "user", text)
            save_message(channel, thread_ts, "assistant", result_text)
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=result_text,
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

        # 봇 소개/기능 질문 여부 판단 (스킬셋 제외 - SKILLSET_INFO는 시스템 프롬프트에 내장됨)
        BOT_INFO_KEYWORDS = ("기능", "소개")
        bot_info = _read_bot_info() if any(kw in text for kw in BOT_INFO_KEYWORDS) else ""

        # 사용자 메시지 저장 & 대화내역 조회
        save_message(channel, thread_ts, "user", text)
        history = get_thread_history(channel, thread_ts)
        # 현재 메시지는 history 마지막에 포함되어 있으므로 제외 (generate_briefing에서 별도 추가)
        history = history[:-1] if history else []

        async def _run():
            desktop_path = os.environ.get("DESKTOP_PATH", "")
            projects = await collect_md(desktop_path)
            projects = await collect_github(projects)
            briefing_text = await generate_briefing(projects, text, bot_info, history)
            return projects, briefing_text

        try:
            loop = asyncio.new_event_loop()
            projects, briefing_text = loop.run_until_complete(_run())
            loop.close()

            # 봇 응답 저장
            save_message(channel, thread_ts, "assistant", briefing_text)
            maybe_cleanup()

            blocks = build_briefing_blocks(briefing_text, projects, is_briefing)

            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=briefing_text[:100] if not is_briefing else "오늘의 업무 브리핑",
                blocks=blocks,
            )
        except Exception as e:
            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=f"브리핑 생성 중 오류가 발생했습니다: {e}",
            )
