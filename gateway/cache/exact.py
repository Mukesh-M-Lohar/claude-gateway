import hashlib
import logging
from gateway.config import settings
from gateway.storage.redis import redis_client
from gateway.storage import sqlite

logger = logging.getLogger("claude-gateway.cache.exact")

def compute_exact_key(repo: str, branch: str, model: str, normalized_prompt: str) -> str:
    # Key = sha256(repo + ":" + branch + ":" + model + ":" + normalized_prompt)
    combined = f"{repo}:{branch}:{model}:{normalized_prompt}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def get_exact_cache(repo: str, branch: str, model: str, normalized_prompt: str, repo_root: str) -> dict | None:
    key = compute_exact_key(repo, branch, model, normalized_prompt)
    
    # Retrieve from selected backend
    if settings.EXACT_CACHE_BACKEND == "redis" and redis_client.is_connected():
        entry = redis_client.get(key)
    else:
        entry = sqlite.get_exact(key)
        
    if not entry:
        return None
        
    # Check if file hashes are still valid
    from gateway.cache.invalidation import is_cache_entry_valid
    if is_cache_entry_valid(repo_root, entry.get("file_hashes", {})):
        logger.info(f"Exact cache HIT for key: {key}")
        return entry
    else:
        # Invalidated! Delete from storage
        logger.info(f"Exact cache INVALIDATED on read for key: {key} (files changed)")
        if settings.EXACT_CACHE_BACKEND == "redis" and redis_client.is_connected():
            redis_client.delete(key)
        else:
            sqlite.delete_exact(key)
        return None

def set_exact_cache(repo: str, branch: str, commit_hash: str, model: str, normalized_prompt: str, response: str, tokens_input: int, tokens_output: int, file_hashes: dict):
    key = compute_exact_key(repo, branch, model, normalized_prompt)
    logger.info(f"Caching exact entry for key: {key}")
    
    if settings.EXACT_CACHE_BACKEND == "redis" and redis_client.is_connected():
        redis_client.set(key, repo, branch, commit_hash, response, tokens_input, tokens_output, file_hashes)
    else:
        sqlite.save_exact(key, repo, branch, commit_hash, response, tokens_input, tokens_output, file_hashes)
