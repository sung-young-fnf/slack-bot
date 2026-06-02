import os
import re
import asyncio
from pathlib import Path
from slack_bolt import App

from collectors.md_collector import collect_md
from collectors.github_collector import collect_github
from ai.claude import generate_briefing, classify_request, generate_notion_status
from formatter.block_kit import build_briefing_blocks
from storage.conversation_store import save_message, get_thread_history, maybe_cleanup, thread_has_assistant
from handlers.task_manager import handle_task_management, _list_projects
from integrations.notion_writer import extract_db_id, add_status_row

CLAUDE_MD_PATH = Path(__file__).parent.parent.parent / "CLAUDE.md"


def _read_bot_info() -> str:
    try:
        return CLAUDE_MD_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def register_handlers(app: App):
    def _process(event, client):
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

        # 대화내역 저장 & 조회
        save_message(channel, thread_ts, "user", text)
        history = get_thread_history(channel, thread_ts)
        history = history[:-1] if history else []

        # AI가 요청 유형을 판단
        desktop_path = os.environ.get("DESKTOP_PATH", "")
        available_projects = _list_projects(desktop_path)
        classification = classify_request(text, available_projects, history)
        req_type = classification.get("type", "general")

        # --- 할일 관리 (task_add / task_done) ---
        if req_type in ("task_add", "task_done"):
            result_text = handle_task_management(text, desktop_path, history, classification)
            save_message(channel, thread_ts, "assistant", result_text)
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=result_text,
            )
            return

        # --- Notion DB row 추가 (notion_update) ---
        if req_type == "notion_update":
            # DB ID는 현재 메시지 + 스레드 이력에서 검색 (관리자 알터가 동적으로 알려줌)
            search_text = text + "\n" + "\n".join(m.get("content", "") for m in history)
            db_id = extract_db_id(search_text)
            if not db_id:
                result_text = "Notion DB ID를 메시지·스레드에서 못 찾았어요. 32자리 ID나 Notion URL을 포함해 다시 요청해주세요."
            elif not (os.environ.get("ORBIT_MCP_URL") or os.environ.get("NOTION_TOKEN")):
                result_text = "Notion 인증이 설정 안 돼 있어요 (ORBIT_MCP_URL 또는 NOTION_TOKEN 필요). 관리자에게 설정 요청해주세요."
            else:
                client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"Notion DB에 정리 중... (DB: {db_id[:8]}...)",
                )
                # 데이터 수집 + Sonnet으로 4섹션 markdown 생성
                async def _build_notion_body():
                    projects = await collect_md(desktop_path)
                    projects = await collect_github(projects)
                    return await generate_notion_status(projects, history)

                try:
                    loop = asyncio.new_event_loop()
                    md_body = loop.run_until_complete(_build_notion_body())
                    loop.close()
                except Exception as e:
                    md_body = ""
                    err_during_build = str(e)
                else:
                    err_during_build = None

                if err_during_build:
                    result_text = f"본문 생성 중 오류: {err_during_build}"
                else:
                    row_title = os.environ.get("NOTION_ROW_TITLE", "castle.alter")
                    url, err = add_status_row(db_id, row_title, md_body)
                    if err:
                        result_text = (
                            f"Notion row 추가 실패: {err}\n"
                            "(DB에 integration이 연결돼 있는지 확인해주세요. DB → ⋯ → Connections → integration 추가)"
                        )
                    else:
                        result_text = f"Notion DB에 row 추가 완료 👉 {url}"

            save_message(channel, thread_ts, "assistant", result_text)
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=result_text,
            )
            return

        # --- 브리핑 / 일반 질문 ---
        loading_resp = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="답변을 준비하고 있습니다..."
        )
        loading_ts = loading_resp["ts"]

        is_briefing = req_type == "briefing"
        bot_info = _read_bot_info() if not is_briefing else ""

        async def _run():
            projects = await collect_md(desktop_path)
            projects = await collect_github(projects)
            briefing_text = await generate_briefing(projects, text, bot_info, history)
            return projects, briefing_text

        try:
            loop = asyncio.new_event_loop()
            projects, briefing_text = loop.run_until_complete(_run())
            loop.close()

            save_message(channel, thread_ts, "assistant", briefing_text)
            maybe_cleanup()

            blocks = build_briefing_blocks(briefing_text, projects, is_briefing)

            # Slack의 text 필드는 (a) notification preview (b) blocks 미지원 클라이언트의 fallback
                # (c) 다른 봇/에이전트가 API로 읽을 때 흔히 참조. 따라서 전체 본문을 그대로 넣어
                # 외부 reader가 truncation 없이 컨텍스트를 받도록 한다. Slack 한도 40,000자.
            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=briefing_text[:40000],
                blocks=blocks,
            )
        except Exception as e:
            client.chat_update(
                channel=channel,
                ts=loading_ts,
                text=f"브리핑 생성 중 오류가 발생했습니다: {e}",
            )

    @app.event("app_mention")
    def handle_mention(event, say, client):
        _process(event, client)

    @app.event("message")
    def handle_message(event, client):
        # 봇/시스템 메시지 무시
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text", "")
        # @멘션이 하나라도 있으면 처리하지 않음:
        #  - 봇 자신 멘션 → app_mention이 처리 (중복 방지)
        #  - 다른 사람/봇 멘션(@Kitty.Alter 등) → 그쪽에게 한 말이므로 끼어들지 않음
        # 멘션 없는 순수 후속 답글에만 응답한다.
        if re.search(r"<@[A-Z0-9]+>", text):
            return
        # 스레드 답글만 대상 (탑레벨 메시지는 응답 안 함)
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return
        # 봇이 한 번이라도 답한 스레드면, 작성자(owner/타인) 무관하게 항상 응답.
        # 전체 이력 기준이라 메시지가 많이 쌓여도 추적이 끊기지 않음.
        channel = event["channel"]
        if not thread_has_assistant(channel, thread_ts):
            return
        _process(event, client)
