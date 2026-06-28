import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("claude-gateway.git.repository")


def find_git_root(start_path: str) -> str | None:
    if not start_path:
        return None
    try:
        current = Path(start_path).resolve()
        while True:
            # Check for a .git folder or file (in case of submodules/worktrees)
            git_path = current / ".git"
            if git_path.exists():
                return str(current)
            if current.parent == current:
                break
            current = current.parent
    except Exception as e:
        logger.error(f"Error traversing path to find git root: {e}")
    return None


def get_git_info(start_path: str) -> dict:
    default_info = {"repo": "global", "branch": "main", "commit": "unknown", "root": start_path or ""}

    if not start_path:
        return default_info

    try:
        root = find_git_root(start_path)
        if not root:
            # Not a git repo, use directory name as repo namespace
            path_obj = Path(start_path).resolve()
            default_info["repo"] = path_obj.name or "global"
            default_info["root"] = str(path_obj)
            return default_info

        repo_name = Path(root).name
        branch = "unknown"
        commit = "unknown"

        # 1. Try reading branch and commit via direct file reads (very fast)
        try:
            head_path = Path(root) / ".git" / "HEAD"
            if head_path.is_file():
                with open(head_path, "r", encoding="utf-8") as f:
                    head_content = f.read().strip()

                if head_content.startswith("ref:"):
                    ref_path = head_content.split(" ")[1]
                    # Extract branch name
                    if ref_path.startswith("refs/heads/"):
                        branch = ref_path[len("refs/heads/") :]
                    else:
                        branch = ref_path.split("/")[-1]

                    # Try reading commit from the ref file
                    ref_file = Path(root) / ".git" / ref_path
                    if ref_file.is_file():
                        with open(ref_file, "r", encoding="utf-8") as f:
                            commit = f.read().strip()
                else:
                    # Detached HEAD
                    commit = head_content
                    branch = "detached"
        except Exception as e:
            logger.debug(f"Direct git files read failed: {e}")

        # 2. Fall back to Git CLI commands if file parsing is incomplete
        if branch == "unknown" or commit == "unknown":
            try:
                # Get branch
                res_branch = subprocess.run(
                    ["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, timeout=2
                )
                if res_branch.returncode == 0:
                    branch = res_branch.stdout.strip() or "detached"

                # Get commit
                res_commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=2
                )
                if res_commit.returncode == 0:
                    commit = res_commit.stdout.strip()
            except Exception as e:
                logger.debug(f"Git CLI commands failed: {e}")

        return {"repo": repo_name, "branch": branch or "detached", "commit": commit or "unknown", "root": root}
    except Exception as e:
        logger.error(f"Error resolving git info for {start_path}: {e}")
        return default_info


def get_changed_files(repo_root: str) -> list:
    if not repo_root or not os.path.exists(repo_root):
        return []

    try:
        # Run git status --porcelain to see unstaged/staged/untracked changes
        res = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            files = []
            for line in res.stdout.splitlines():
                if len(line) > 3:
                    # Format: 'XY path/to/file'
                    # Where X, Y are status codes
                    file_path = line[3:].strip()
                    if " -> " in file_path:
                        # Rename format: 'old_path -> new_path'
                        file_path = file_path.split(" -> ")[-1].strip()
                    files.append(file_path)
            return files
    except Exception as e:
        logger.debug(f"Failed to get changed files via git status: {e}")
    return []
