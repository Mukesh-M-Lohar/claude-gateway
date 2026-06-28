import json
import logging
from datetime import datetime
from gateway.config import settings

logger = logging.getLogger("claude-gateway.redis")

# Try to import redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis library not installed. Redis cache disabled.")

class RedisClient:
    def __init__(self):
        self.client = None
        if REDIS_AVAILABLE and settings.EXACT_CACHE_BACKEND == "redis":
            try:
                self.client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                    decode_responses=True,
                    socket_connect_timeout=2
                )
                # Test connection
                self.client.ping()
                logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}. Falling back to SQLite.")
                self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    def get(self, key: str) -> dict:
        if not self.client:
            # Fallback to SQLite
            from gateway.storage import sqlite
            return sqlite.get_exact(key)
        
        try:
            val = self.client.get(f"exact:{key}")
            if val:
                return json.loads(val)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            from gateway.storage import sqlite
            return sqlite.get_exact(key)
        return None

    def set(self, key: str, repo: str, branch: str, commit_hash: str, response: str, tokens_input: int, tokens_output: int, file_hashes: dict):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.save_exact(key, repo, branch, commit_hash, response, tokens_input, tokens_output, file_hashes)
            return

        try:
            data = {
                "key": key,
                "response": response,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "created_at": datetime.utcnow().isoformat(),
                "repo": repo,
                "branch": branch,
                "commit_hash": commit_hash,
                "file_hashes": file_hashes
            }
            # Set without TTL as requested (Git watcher handles invalidation)
            self.client.set(f"exact:{key}", json.dumps(data))
            
            # Store in a set for repo tracking to easily invalidate by repo
            self.client.sadd(f"repo_keys:{repo}", key)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            from gateway.storage import sqlite
            sqlite.save_exact(key, repo, branch, commit_hash, response, tokens_input, tokens_output, file_hashes)

    def delete(self, key: str):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.delete_exact(key)
            return
        try:
            self.client.delete(f"exact:{key}")
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            from gateway.storage import sqlite
            sqlite.delete_exact(key)

    def invalidate_by_files(self, repo: str, files: list):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.invalidate_exact_by_files(repo, files)
            return

        try:
            # Get all keys for this repo
            repo_keys_set = f"repo_keys:{repo}"
            keys = self.client.smembers(repo_keys_set)
            
            if not keys:
                return
                
            keys_to_remove = []
            for key in keys:
                val = self.client.get(f"exact:{key}")
                if val:
                    data = json.loads(val)
                    file_hashes = data.get("file_hashes", {})
                    for file in files:
                        if file in file_hashes:
                            self.client.delete(f"exact:{key}")
                            keys_to_remove.append(key)
                            break
            
            if keys_to_remove:
                self.client.srem(repo_keys_set, *keys_to_remove)
        except Exception as e:
            logger.error(f"Redis invalidate error: {e}")
            from gateway.storage import sqlite
            sqlite.invalidate_exact_by_files(repo, files)

    def invalidate_all_for_repo(self, repo: str):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.invalidate_all_for_repo(repo)
            return

        try:
            repo_keys_set = f"repo_keys:{repo}"
            keys = self.client.smembers(repo_keys_set)
            for key in keys:
                self.client.delete(f"exact:{key}")
            self.client.delete(repo_keys_set)
        except Exception as e:
            logger.error(f"Redis clear repo error: {e}")
            from gateway.storage import sqlite
            sqlite.invalidate_all_for_repo(repo)

# Singleton Redis client
redis_client = RedisClient()
