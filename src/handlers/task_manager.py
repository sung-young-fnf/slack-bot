import os
import re
from datetime import date
from pathlib import Path

from ai.claude import parse_task_with_ai
from executor.git_manager import (
    has_git, create_branch, commit_and_push, create_pr, cleanup_branch, restore_branch,
)


TASKS_FILENAME = "TASKS.md"

# 할일 추가 키워드
ADD_KEYWORDS = ("할일 추가", "태스크 추가", "할일 등록", "todo 추가")
# 완료 처리 키워드
DONE_KEYWORDS = ("완료 처리", "완료해줘", "체크해줘", "done 처리")

UNCHECKED_RE = re.compile(r"^([-*]\s+)\[ \]\s+(.+)$", re.MULTILINE)


def _find_project_path(desktop_path: str, project_name: str) -> Path | None:
    """프로젝트명으로 프로젝트 디렉토리 경로를 찾는다."""
    base = Path(desktop_path)
    if not base.exists():
        return None

    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name.lower() == project_name.lower():
            return project_dir

    return None


def _list_projects(desktop_path: str) -> list[str]:
    """TASKS.md가 있는 프로젝트 목록을 반환한다."""
    base = Path(desktop_path)
    if not base.exists():
        return []
    return [
        d.name for d in sorted(base.iterdir())
        if d.is_dir() and (d / TASKS_FILENAME).exists()
    ]


def is_task_management(text: str) -> bool:
    """할일 관리 요청인지 판단한다."""
    return any(kw in text for kw in ADD_KEYWORDS + DONE_KEYWORDS)


def is_add_request(text: str) -> bool:
    return any(kw in text for kw in ADD_KEYWORDS)


def is_done_request(text: str) -> bool:
    return any(kw in text for kw in DONE_KEYWORDS)


def _extract_project_name(text: str, available_projects: list[str]) -> str | None:
    """텍스트에서 프로젝트명을 추출한다."""
    text_lower = text.lower()
    for project in available_projects:
        if project.lower() in text_lower:
            return project
    return None


def _extract_items(text: str) -> list[str]:
    """텍스트에서 할일 항목들을 추출한다. 따옴표 또는 쉼표 구분."""
    # 따옴표로 감싼 항목 추출: "항목1", "항목2"
    quoted = re.findall(r'["""](.+?)["""]', text)
    if quoted:
        return [item.strip() for item in quoted if item.strip()]

    # 키워드 이후 텍스트에서 추출
    for kw in ADD_KEYWORDS + DONE_KEYWORDS:
        if kw in text:
            after = text.split(kw, 1)[1].strip()
            # "—" 또는 "-" 이후 텍스트
            after = re.sub(r"^[\s—\-]+", "", after).strip()
            if after:
                # 쉼표로 구분된 항목
                if "," in after:
                    return [item.strip() for item in after.split(",") if item.strip()]
                return [after]

    return []


def _modify_tasks_file_add(tasks_file: Path, items: list[str]) -> None:
    """TASKS.md에 할일 항목을 추가한다."""
    if not tasks_file.exists():
        tasks_file.write_text(f"# TASKS\n\n", encoding="utf-8")

    content = tasks_file.read_text(encoding="utf-8")
    if content and not content.endswith("\n"):
        content += "\n"

    new_lines = [f"- [ ] {item}" for item in items]
    content += "\n".join(new_lines) + "\n"
    tasks_file.write_text(content, encoding="utf-8")


def _modify_tasks_file_done(tasks_file: Path, items: list[str], done_date: str | None = None) -> dict:
    """TASKS.md에서 할일 항목을 완료 처리한다."""
    content = tasks_file.read_text(encoding="utf-8")
    today_str = done_date or date.today().strftime("%Y-%m-%d")

    completed = []
    not_found = []

    for item in items:
        item_lower = item.lower().strip()
        found = False

        for match in UNCHECKED_RE.finditer(content):
            prefix = match.group(1)
            task_text = match.group(2).strip()
            if item_lower in task_text.lower():
                old_line = match.group(0)
                new_line = f"{prefix}[x] {task_text} ({today_str})"
                content = content.replace(old_line, new_line, 1)
                completed.append(task_text)
                found = True
                break

        if not found:
            not_found.append(item)

    tasks_file.write_text(content, encoding="utf-8")
    return {"completed": completed, "not_found": not_found}


def _execute_with_git(action: str, project_path: str, project_name: str, items: list[str], done_date: str | None = None) -> str:
    """git 브랜치/커밋/PR을 통해 TASKS.md를 변경한다."""
    tasks_file = Path(project_path) / TASKS_FILENAME

    if not tasks_file.exists() and action == "done":
        return f"'{project_name}'에 TASKS.md가 없어요."

    # 브랜치명 생성
    today_str = date.today().strftime("%Y%m%d")
    action_label = "add-task" if action == "add" else "done-task"
    branch_name = f"task/{action_label}-{today_str}"

    # 브랜치 생성
    ok, msg = create_branch(project_path, branch_name)
    if not ok:
        return f"브랜치 생성 실패: {msg}"

    try:
        # TASKS.md 수정
        if action == "add":
            _modify_tasks_file_add(tasks_file, items)
            items_text = "\n".join(f"  - [ ] {item}" for item in items)
            commit_msg = f"Task: 할일 추가 — {', '.join(items)}"
        else:
            result = _modify_tasks_file_done(tasks_file, items, done_date)
            completed = result["completed"]
            not_found = result["not_found"]
            if not completed:
                restore_branch(project_path, branch_name)
                not_found_text = "\n".join(f"  - ❓ \"{item}\"" for item in not_found)
                return f"일치하는 할일을 찾지 못했어요.\n{not_found_text}"
            commit_msg = f"Task: 완료 처리 — {', '.join(completed)}"

        # 커밋 + 푸시
        ok, msg = commit_and_push(project_path, branch_name, commit_msg, [TASKS_FILENAME])
        if not ok:
            restore_branch(project_path, branch_name)
            return f"커밋/푸시 실패: {msg}"

        # PR 생성
        pr_title = commit_msg
        pr_body = f"## Summary\n- 프로젝트: {project_name}\n- 작업: {'할일 추가' if action == 'add' else '완료 처리'}\n- 항목: {', '.join(items)}\n\n🤖 Slack Bot 자동 생성"
        ok, pr_url = create_pr(project_path, branch_name, pr_title, pr_body)

        # 기본 브랜치로 복귀
        cleanup_branch(project_path, branch_name)

        if not ok:
            return f"커밋/푸시는 완료했지만 PR 생성에 실패했어요: {pr_url}\n브랜치: {branch_name}"

        # 성공 응답
        if action == "add":
            items_text = "\n".join(f"  - [ ] {item}" for item in items)
            return f"📝 할일 추가 PR 생성 완료!\n━━━━━━━━━━━━━━━━━━\n📁 프로젝트: {project_name}\n추가된 항목:\n{items_text}\n🔗 PR: {pr_url}\n━━━━━━━━━━━━━━━━━━"
        else:
            lines = []
            display_date = done_date or date.today().strftime("%Y-%m-%d")
            for item in completed:
                lines.append(f"  - [x] {item} ({display_date})")
            for item in not_found:
                lines.append(f"  - ❓ \"{item}\" — 일치하는 할일을 찾지 못했어요")
            items_text = "\n".join(lines)
            return f"✅ 완료 처리 PR 생성 완료!\n━━━━━━━━━━━━━━━━━━\n📁 프로젝트: {project_name}\n{items_text}\n🔗 PR: {pr_url}\n━━━━━━━━━━━━━━━━━━"

    except Exception as e:
        restore_branch(project_path, branch_name)
        return f"작업 중 오류가 발생했어요: {e}"


def _execute_local(action: str, project_path: str, project_name: str, items: list[str], done_date: str | None = None) -> str:
    """git이 없는 프로젝트는 로컬에서 직접 수정한다."""
    tasks_file = Path(project_path) / TASKS_FILENAME

    if action == "add":
        _modify_tasks_file_add(tasks_file, items)
        items_text = "\n".join(f"  - [ ] {item}" for item in items)
        return f"📝 할일 추가 완료!\n━━━━━━━━━━━━━━━━━━\n📁 프로젝트: {project_name}\n추가된 항목:\n{items_text}\n━━━━━━━━━━━━━━━━━━\n⚠️ Git 미연동 — 로컬 파일만 수정됨"

    else:
        if not tasks_file.exists():
            return f"'{project_name}'에 TASKS.md가 없어요."
        result = _modify_tasks_file_done(tasks_file, items, done_date)
        lines = []
        display_date = done_date or date.today().strftime("%Y-%m-%d")
        for item in result["completed"]:
            lines.append(f"  - [x] {item} ({display_date})")
        for item in result["not_found"]:
            lines.append(f"  - ❓ \"{item}\" — 일치하는 할일을 찾지 못했어요")
        items_text = "\n".join(lines)
        return f"✅ 완료 처리!\n━━━━━━━━━━━━━━━━━━\n📁 프로젝트: {project_name}\n{items_text}\n━━━━━━━━━━━━━━━━━━\n⚠️ Git 미연동 — 로컬 파일만 수정됨"


def handle_task_management(text: str, desktop_path: str, history: list[dict] | None = None) -> str:
    """할일 관리 요청을 처리하고 응답 텍스트를 반환한다.
    1차: AI 판단 (자연어 이해, 대화 맥락 포함)
    2차: 키워드 매칭 (AI 실패 시 fallback)
    """
    available_projects = _list_projects(desktop_path)

    if not available_projects:
        return "TASKS.md가 있는 프로젝트가 없어요."

    action = None
    project_name = None
    items = []
    done_date = None

    # --- 1차: AI 판단 (메인, 대화 맥락 포함) ---
    ai_result = parse_task_with_ai(text, available_projects, history)
    if ai_result:
        action = ai_result.get("action")
        project_name = ai_result.get("project")
        items = ai_result.get("items", [])
        done_date = ai_result.get("date")

    # --- 2차: 키워드 매칭 (AI 결과가 부족한 부분 보완) ---
    if not action:
        action = "add" if is_add_request(text) else "done" if is_done_request(text) else None
    if not project_name:
        project_name = _extract_project_name(text, available_projects)
    if not items:
        items = _extract_items(text)

    if not project_name:
        project_list = "\n".join(f"  - {p}" for p in available_projects)
        return f"어떤 프로젝트인지 알려주세요.\n\n현재 프로젝트 목록:\n{project_list}"

    if not items:
        return "추가하거나 완료할 항목을 알려주세요.\n\n예시:\n  - `slack_bot에 API 에러 핸들링 할일 추가해줘`\n  - `slack_bot에서 로깅 추가 완료 처리해줘`"

    if not action:
        return "요청을 이해하지 못했어요. \"할일 추가\" 또는 \"완료 처리\"로 말씀해주세요."

    # 프로젝트 경로 찾기
    project_path = _find_project_path(desktop_path, project_name)
    if not project_path:
        return f"프로젝트 '{project_name}'을 찾을 수 없어요."

    # git 연동 여부에 따라 분기
    if has_git(str(project_path)):
        return _execute_with_git(action, str(project_path), project_name, items, done_date)
    else:
        return _execute_local(action, str(project_path), project_name, items, done_date)
