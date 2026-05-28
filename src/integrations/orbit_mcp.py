"""Orbit notion-mcp 경유로 Notion API 호출하는 모듈.

봇이 Notion 토큰을 직접 가지지 않고, 사용자의 Orbit subscription URL만 알면
Orbit이 보관·갱신하는 OAuth 토큰을 통해 Notion 페이지/DB에 작성 가능.

ORBIT_MCP_URL 환경변수: Streamable HTTP 엔드포인트
  예) https://orbit-mcp-api.fnf.co.kr/api/projects/<pid>/subscriptions/<sid>/mcp
"""

import os
import json
from typing import Any

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # mcp 미설치 시 봇 부팅은 가능
    ClientSession = None
    streamablehttp_client = None


def is_available() -> bool:
    return bool(os.environ.get("ORBIT_MCP_URL")) and ClientSession is not None


def _dashify(notion_id: str) -> str:
    """32-char ID에 dash 추가: 8-4-4-4-12. 이미 대시 있으면 그대로."""
    nid = notion_id.replace("-", "")
    if len(nid) != 32:
        return notion_id
    return f"{nid[:8]}-{nid[8:12]}-{nid[12:16]}-{nid[16:20]}-{nid[20:]}"


def _parse_result(result) -> dict:
    """MCP call_tool 결과 → dict. content[0].text가 JSON 문자열인 게 일반적."""
    content = getattr(result, "content", None)
    if not content:
        return {}
    first = content[0]
    text = getattr(first, "text", None)
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


async def _call(tool_name: str, arguments: dict[str, Any]) -> dict:
    """Orbit MCP 한 번 호출 — 매번 새 connection (간단성 우선).

    ORBIT_MCP_TOKEN이 있으면 Authorization: Bearer 헤더로 인증.
    (Orbit 페이지의 "API Key 인증 (SSO 미지원 클라이언트용)"에서 발급)
    """
    url = os.environ.get("ORBIT_MCP_URL")
    if not url or streamablehttp_client is None:
        raise RuntimeError("Orbit MCP 미설정 (ORBIT_MCP_URL 비어있거나 mcp 라이브러리 없음)")

    headers: dict[str, str] = {}
    token = os.environ.get("ORBIT_MCP_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with streamablehttp_client(url, headers=headers or None) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return _parse_result(result)


# ───────── Notion 도구 래퍼 ─────────

async def retrieve_database(database_id: str) -> dict:
    return await _call("notion_retrieve_database", {"database_id": _dashify(database_id)})


async def retrieve_page(page_id: str) -> dict:
    return await _call("notion_retrieve_page", {"page_id": _dashify(page_id)})


async def create_database_item(database_id: str, properties: dict, children: list[dict]) -> dict:
    return await _call("notion_create_database_item", {
        "parent": {"database_id": _dashify(database_id)},
        "properties": properties,
        "children": children,
    })


async def append_block_children(block_id: str, children: list[dict]) -> dict:
    return await _call("notion_append_block_children", {
        "block_id": _dashify(block_id),
        "children": children,
    })
