import time
import threading
import logging
import subprocess
from gateway.config import settings
from gateway.storage import sqlite
from gateway.storage.redis import redis_client
from gateway.storage.qdrant import qdrant_cache
from gateway.git.repository import get_changed_files, get_git_info

logger = logging.getLogger("claude-gateway.git.watcher")

class GitWatcher:
    def __init__(self):
        self.last_commits = {}  # repo_name -> commit_hash
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.thread.start()
        logger.info("Git Watcher background thread started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            logger.info("Git Watcher background thread stopped.")

    def run_loop(self):
        # Wait a bit before first check to let the server startup
        time.sleep(5)
        
        while self.running:
            try:
                self.check_repositories()
            except Exception as e:
                logger.error(f"Error in Git Watcher loop: {e}")
                
            # Sleep for the configured interval
            interval = settings.GIT_WATCHER_INTERVAL
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

    def check_repositories(self):
        repos = sqlite.get_registered_repos()
        for r in repos:
            repo_name = r["repo"]
            repo_root = r["root"]
            
            # 1. Fetch current git info
            git_info = get_git_info(repo_root)
            current_commit = git_info["commit"]
            last_commit = self.last_commits.get(repo_name)
            
            changed_files = set()
            
            # 2. Check for working tree changes (staged, unstaged, untracked modifications)
            working_tree_changes = get_changed_files(repo_root)
            if working_tree_changes:
                logger.debug(f"Detected working tree changes in {repo_name}: {working_tree_changes}")
                changed_files.update(working_tree_changes)
                
            # 3. Check for new commit / branch switch
            if last_commit and current_commit != "unknown" and current_commit != last_commit:
                logger.info(f"Repository {repo_name} commit changed from {last_commit} to {current_commit}")
                # Get files changed between the old commit and new commit
                commit_changes = self.get_files_changed_between_commits(repo_root, last_commit, current_commit)
                if commit_changes:
                    logger.info(f"Files changed between commits: {commit_changes}")
                    changed_files.update(commit_changes)
                    
            # Update cache of last commit hash
            if current_commit != "unknown":
                self.last_commits[repo_name] = current_commit
                
            # 4. Trigger invalidations if any files changed
            if changed_files:
                changed_list = list(changed_files)
                logger.info(f"Invalidating cache entries referencing changed files in {repo_name}: {changed_list}")
                
                # Invalidate exact caches
                redis_client.invalidate_by_files(repo_name, changed_list)
                sqlite.invalidate_exact_by_files(repo_name, changed_list)
                
                # Invalidate semantic caches
                qdrant_cache.invalidate_by_files(repo_name, changed_list)
                sqlite.invalidate_semantic_by_files(repo_name, changed_list)

    def get_files_changed_between_commits(self, repo_root: str, old_commit: str, new_commit: str) -> list:
        try:
            # git diff --name-only old_commit new_commit
            res = subprocess.run(
                ["git", "diff", "--name-only", old_commit, new_commit],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception as e:
            logger.debug(f"Failed to get diff between {old_commit} and {new_commit}: {e}")
        return []

# Singleton Git Watcher
git_watcher = GitWatcher()
