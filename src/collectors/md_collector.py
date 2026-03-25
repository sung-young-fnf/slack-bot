import re
import asyncio
from pathlib import Path


TASKS_FILENAME = "TASKS.md"

UNCHECKED = re.compile(r"^[-*]\s+\[ \]\s+(.+)$", re.MULTILINE)
CHECKED = re.compile(r"^[-*]\s+\[x\]\s+(.+?)(?:\s+\((\d{4}-\d{2}-\d{2})\))?\s*$", re.MULTILINE | re.IGNORECASE)


def parse_md_file(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}

    todos = UNCHECKED.findall(content)
    done = [{"text": m[0], "date": m[1] if m[1] else None} for m in CHECKED.findall(content)]

    return {"todos": todos, "done": done}


async def collect_md(desktop_path: str, target_project: str | None = None) -> list[dict]:
    base = Path(desktop_path)
    if not base.exists():
        return []

    results = []

    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        if target_project and project_dir.name.lower() != target_project.lower():
            continue

        tasks_file = project_dir / TASKS_FILENAME
        if not tasks_file.exists():
            continue

        parsed = parse_md_file(tasks_file)
        todos = parsed.get("todos", [])
        done = parsed.get("done", [])

        if todos or done:
            results.append({
                "project": project_dir.name,
                "project_path": str(project_dir),
                "todos": todos,
                "done": done,
            })

    return results
