"""Notion DB/Page에 업무 현황을 작성하는 모듈.

- ID는 메시지/스레드에서 동적으로 추출 (extract_notion_id)
- ID가 가리키는 게 DB면 새 row 생성, Page면 그 페이지에 내용 append
- markdown은 간단 파서로 Notion block 리스트로 변환
"""

import os
import re
import asyncio

try:
    from notion_client import Client
except ImportError:
    Client = None  # 봇 부팅은 가능 — notion_update 호출 시점에만 실패

from . import orbit_mcp


# 32자리 hex (대시 유무 모두) — Notion DB/Page ID
_NOTION_ID_RE = re.compile(
    r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})"
)


def extract_notion_id(text: str) -> str | None:
    """텍스트에서 첫 Notion ID(32 hex)를 추출. 대시는 제거해 반환.

    DB든 Page든 동일한 32자리 hex 형식이라 한 함수로 처리.
    """
    if not text:
        return None
    m = _NOTION_ID_RE.search(text)
    if not m:
        return None
    return m.group(1).replace("-", "")


# 하위 호환 alias
extract_db_id = extract_notion_id


def _rt(text: str) -> list[dict]:
    """Notion rich_text 단일 텍스트 helper. 2000자 컷."""
    return [{"type": "text", "text": {"content": text[:2000]}}]


def md_to_blocks(md: str) -> list[dict]:
    """간단 markdown → Notion 블록 리스트.

    지원: H2/H3, bullet/numbered list, 체크박스(to_do), 일반 단락.
    """
    blocks: list[dict] = []
    for raw in md.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": _rt(line[4:].strip())},
            })
            continue
        if line.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": _rt(line[3:].strip())},
            })
            continue
        m = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.+)$", line)
        if m:
            checked = m.group(1).lower() == "x"
            blocks.append({
                "object": "block", "type": "to_do",
                "to_do": {"rich_text": _rt(m.group(2).strip()), "checked": checked},
            })
            continue
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _rt(m.group(1).strip())},
            })
            continue
        m = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if m:
            blocks.append({
                "object": "block", "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _rt(m.group(1).strip())},
            })
            continue
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rt(line.strip())},
        })
    return blocks[:100]  # Notion create 시 children 최대 100


def _find_title_prop(properties: dict) -> str | None:
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    return None


def _create_db_row(notion: "Client", db_id: str, title: str, blocks: list[dict]) -> tuple[str, str | None]:
    """DB에 새 row(page) 생성."""
    try:
        db = notion.databases.retrieve(database_id=db_id)
    except Exception as e:
        return ("", f"__not_db__:{e}")  # 호출자가 page 모드로 fallback 가능하도록 신호

    title_prop = _find_title_prop(db.get("properties", {}))
    if not title_prop:
        return ("", "대상 DB에 title 프로퍼티가 없어요.")

    try:
        new_page = notion.pages.create(
            parent={"database_id": db_id},
            properties={title_prop: {"title": _rt(title)}},
            children=blocks,
        )
        return (new_page.get("url", ""), None)
    except Exception as e:
        return ("", f"DB row 생성 실패: {e}")


def _append_to_page(notion: "Client", page_id: str, title: str, blocks: list[dict]) -> tuple[str, str | None]:
    """기존 Page에 제목(heading_2) + 본문 블록 append."""
    try:
        page = notion.pages.retrieve(page_id=page_id)
    except Exception as e:
        return ("", f"Notion ID로 DB/Page 둘 다 못 찾았어요: {e}")

    heading = {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": _rt(title)},
    }
    try:
        # children append는 한 번에 최대 100개
        notion.blocks.children.append(
            block_id=page_id,
            children=([heading] + blocks)[:100],
        )
        return (page.get("url", ""), None)
    except Exception as e:
        return ("", f"페이지에 내용 추가 실패: {e}")


def write_to_target(notion_id: str, title: str, markdown: str) -> tuple[str, str | None]:
    """Notion ID가 DB면 새 row 생성, Page면 본문에 append.

    경로 우선순위:
      1) ORBIT_MCP_URL이 설정돼 있으면 Orbit MCP 경유 (봇 토큰 불필요)
      2) NOTION_TOKEN이 설정돼 있으면 직접 Notion API
      3) 둘 다 없으면 에러

    Returns (url, error_message). 성공 시 error_message=None.
    """
    blocks = md_to_blocks(markdown)

    # 1) Orbit MCP 경로
    if orbit_mcp.is_available():
        try:
            return asyncio.run(_write_via_orbit(notion_id, title, blocks))
        except Exception as e:
            return ("", f"Orbit MCP 호출 실패: {e}")

    # 2) 직접 Notion API 경로
    if Client is None:
        return ("", "notion-client 라이브러리가 설치돼 있지 않아요.")
    if not os.environ.get("NOTION_TOKEN"):
        return ("", "ORBIT_MCP_URL과 NOTION_TOKEN 둘 다 설정 안 됨. 하나는 필요해요.")

    notion = Client(auth=os.environ["NOTION_TOKEN"])

    # DB 우선 시도, 실패하면 Page로 fallback
    url, err = _create_db_row(notion, notion_id, title, blocks)
    if err is None:
        return (url, None)
    if not err.startswith("__not_db__"):
        return (url, err)
    return _append_to_page(notion, notion_id, title, blocks)


def _is_notion_error(resp: dict | None) -> str | None:
    """Notion API 응답이 에러면 사람 읽기 좋은 메시지, 정상이면 None."""
    if not isinstance(resp, dict):
        return None
    if resp.get("object") == "error":
        code = resp.get("code", "unknown")
        msg = resp.get("message", "")
        return f"{code}: {msg}"
    return None


async def _write_via_orbit(notion_id: str, title: str, blocks: list[dict]) -> tuple[str, str | None]:
    """Orbit MCP 경유: DB면 row 생성, Page면 append. 자동 감지."""
    # DB 시도
    try:
        db = await orbit_mcp.retrieve_database(notion_id)
    except Exception:
        db = None
    db_err = _is_notion_error(db)

    if db and not db_err and "properties" in db:
        title_prop = _find_title_prop(db.get("properties", {}))
        if not title_prop:
            return ("", "대상 DB에 title 프로퍼티가 없어요.")
        try:
            result = await orbit_mcp.create_database_item(
                notion_id,
                properties={title_prop: {"title": _rt(title)}},
                children=blocks[:100],
            )
            r_err = _is_notion_error(result)
            if r_err:
                return ("", f"Orbit DB row 생성 거부됨 — {r_err}")
            url = result.get("url", "")
            if not url:
                return ("", f"Orbit DB row 응답에 URL 없음 (raw: {str(result)[:200]})")
            return (url, None)
        except Exception as e:
            return ("", f"Orbit MCP DB row 생성 실패: {e}")

    # Page로 fallback
    try:
        page = await orbit_mcp.retrieve_page(notion_id)
    except Exception as e:
        return ("", f"Orbit MCP로 Page 조회 실패: {e}")
    p_err = _is_notion_error(page)
    if p_err:
        # DB도 Page도 모두 에러 — integration이 이 페이지에 공유 안 됐을 가능성 큼
        return ("", f"대상 페이지를 못 찾거나 권한 부족 — {p_err}. "
                   f"Notion에서 해당 페이지 ⋯ → 연결(Connections) → Orbit 추가했는지 확인해주세요.")

    heading = {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": _rt(title)},
    }
    try:
        append_result = await orbit_mcp.append_block_children(
            notion_id, children=([heading] + blocks)[:100],
        )
        a_err = _is_notion_error(append_result)
        if a_err:
            return ("", f"Orbit 페이지 append 거부됨 — {a_err}")
        return (page.get("url", ""), None)
    except Exception as e:
        return ("", f"Orbit MCP 페이지 append 실패: {e}")


# 하위 호환: 기존 코드가 add_status_row를 import해도 동작
def add_status_row(db_id: str, title: str, markdown: str) -> tuple[str, str | None]:
    """[Deprecated] write_to_target 사용 권장. DB/Page 자동 감지."""
    return write_to_target(db_id, title, markdown)
