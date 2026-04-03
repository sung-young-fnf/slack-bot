import subprocess
import os
from pathlib import Path


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _run_git(project_path: str, *args: str) -> tuple[bool, str]:
    """프로젝트 경로에서 git 명령을 실행한다."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def has_git(project_path: str) -> bool:
    """프로젝트에 .git이 있는지 확인한다."""
    return (Path(project_path) / ".git").exists()


def get_default_branch(project_path: str) -> str:
    """기본 브랜치명을 반환한다 (main 또는 master)."""
    ok, output = _run_git(project_path, "symbolic-ref", "refs/remotes/origin/HEAD", "--short")
    if ok:
        # "origin/main" → "main"
        return output.split("/")[-1]
    # fallback: main 브랜치가 있는지 확인
    ok, _ = _run_git(project_path, "rev-parse", "--verify", "main")
    return "main" if ok else "master"


def get_remote_url(project_path: str) -> str | None:
    """remote origin URL에서 owner/repo를 추출한다."""
    ok, output = _run_git(project_path, "config", "--get", "remote.origin.url")
    if not ok:
        return None

    # https://github.com/owner/repo.git → owner/repo
    # git@github.com:owner/repo.git → owner/repo
    url = output.strip().rstrip(".git")
    if "github.com" in url:
        if url.startswith("git@"):
            return url.split(":")[-1]
        else:
            parts = url.split("github.com/")
            if len(parts) == 2:
                return parts[1]
    return None


def create_branch(project_path: str, branch_name: str) -> tuple[bool, str]:
    """기본 브랜치에서 새 브랜치를 생성하고 체크아웃한다."""
    default_branch = get_default_branch(project_path)

    # 최신 상태로 업데이트
    _run_git(project_path, "fetch", "origin")
    _run_git(project_path, "checkout", default_branch)
    _run_git(project_path, "pull", "origin", default_branch)

    # 새 브랜치 생성
    ok, output = _run_git(project_path, "checkout", "-b", branch_name)
    if not ok:
        return False, f"브랜치 생성 실패: {output}"
    return True, branch_name


def commit_and_push(project_path: str, branch_name: str, commit_message: str, files: list[str]) -> tuple[bool, str]:
    """파일을 스테이징하고 커밋 후 푸시한다."""
    # 파일 스테이징
    for f in files:
        ok, output = _run_git(project_path, "add", f)
        if not ok:
            return False, f"파일 스테이징 실패 ({f}): {output}"

    # 커밋
    ok, output = _run_git(project_path, "commit", "-m", commit_message)
    if not ok:
        return False, f"커밋 실패: {output}"

    # 푸시
    ok, output = _run_git(project_path, "push", "-u", "origin", branch_name)
    if not ok:
        return False, f"푸시 실패: {output}"

    return True, "success"


def create_pr(project_path: str, branch_name: str, title: str, body: str) -> tuple[bool, str]:
    """PyGithub으로 PR을 생성한다. 성공 시 PR URL을 반환한다."""
    from github import Github

    repo_name = get_remote_url(project_path)
    if not repo_name:
        return False, "remote origin URL을 찾을 수 없어요."

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False, "GITHUB_TOKEN이 설정되어 있지 않아요."

    default_branch = get_default_branch(project_path)

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=default_branch,
        )
        return True, pr.html_url
    except Exception as e:
        return False, f"PR 생성 실패: {e}"


def cleanup_branch(project_path: str, branch_name: str) -> None:
    """작업 후 기본 브랜치로 복귀하고 작업 브랜치를 삭제한다."""
    default_branch = get_default_branch(project_path)
    _run_git(project_path, "checkout", default_branch)
    _run_git(project_path, "branch", "-D", branch_name)


def restore_branch(project_path: str, branch_name: str) -> None:
    """실패 시 변경사항을 되돌리고 기본 브랜치로 복귀한다."""
    _run_git(project_path, "checkout", ".")
    default_branch = get_default_branch(project_path)
    _run_git(project_path, "checkout", default_branch)
    _run_git(project_path, "branch", "-D", branch_name)
