import os
import re
import time
import asyncio
import configparser
from pathlib import Path
from github import Github, GithubException

_cache: dict[str, tuple[dict, float]] = {}
CACHE_TTL = 300  # 5분


def _parse_remote_url(config_path: Path) -> tuple[str, str] | None:
    """
    .git/config 에서 remote origin URL을 읽어 (owner, repo) 튜플을 반환합니다.
    지원 형식:
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    """
    try:
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")
        url = parser.get('remote "origin"', "url", fallback=None)
        if not url:
            return None

        # HTTPS (토큰 포함 URL 지원: https://token@github.com/...)
        m = re.match(r"https://(?:[^@]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1), m.group(2)

        # SSH
        m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None


async def _fetch_repo_data(gh: Github, owner: str, repo: str, username: str) -> dict:
    cache_key = f"{owner}/{repo}"
    now = time.time()
    if cache_key in _cache:
        data, ts = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data

    def _sync_fetch():
        try:
            repository = gh.get_repo(f"{owner}/{repo}")
            issues = [
                {"number": i.number, "title": i.title, "url": i.html_url}
                for i in repository.get_issues(state="open", assignee=username)
                if i.pull_request is None
            ]
            prs = [
                {"number": p.number, "title": p.title, "url": p.html_url}
                for p in repository.get_pulls(state="open")
                if p.user.login == username
            ]
            return {"issues": issues, "prs": prs, "error": None}
        except GithubException as e:
            return {"issues": [], "prs": [], "error": str(e)}

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _sync_fetch)
    _cache[cache_key] = (data, now)
    return data


async def collect_github(project_data: list[dict]) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    username = os.environ.get("GITHUB_USERNAME", "")
    if not token:
        return project_data

    gh = Github(token)

    tasks = []
    indices = []

    for i, project in enumerate(project_data):
        git_config = Path(project["project_path"]) / ".git" / "config"
        if not git_config.exists():
            continue
        parsed = _parse_remote_url(git_config)
        if not parsed:
            continue
        owner, repo = parsed
        tasks.append(_fetch_repo_data(gh, owner, repo, username))
        indices.append(i)

    if not tasks:
        return project_data

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, result in zip(indices, results):
        if isinstance(result, Exception):
            project_data[idx]["issues"] = []
            project_data[idx]["prs"] = []
            project_data[idx]["github_error"] = str(result)
        elif result.get("error"):
            project_data[idx]["issues"] = []
            project_data[idx]["prs"] = []
            project_data[idx]["github_error"] = result["error"]
        else:
            project_data[idx]["issues"] = result["issues"]
            project_data[idx]["prs"] = result["prs"]

    return project_data
