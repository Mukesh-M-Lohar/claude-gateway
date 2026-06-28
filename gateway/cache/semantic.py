import logging

from gateway.config import settings
from gateway.embeddings.openai import get_embedding
from gateway.storage import sqlite
from gateway.storage.qdrant import qdrant_cache

logger = logging.getLogger("claude-gateway.cache.semantic")


async def get_semantic_cache(repo: str, branch: str, normalized_prompt: str, repo_root: str) -> dict | None:
    # 1. Generate prompt embedding
    try:
        embedding = await get_embedding(normalized_prompt)
    except Exception as e:
        logger.error(f"Failed to generate embedding for semantic search: {e}")
        return None

    # 2. Query selected vector backend
    threshold = settings.SIMILARITY_THRESHOLD
    if settings.SEMANTIC_CACHE_BACKEND == "qdrant" and qdrant_cache.is_connected():
        entry = qdrant_cache.get(repo, branch, embedding, threshold)
    else:
        entry = sqlite.get_semantic(repo, branch, embedding, threshold)

    if not entry:
        return None

    # 3. Validate files referenced in the cache entry
    from gateway.cache.invalidation import is_cache_entry_valid

    if is_cache_entry_valid(repo_root, entry.get("file_hashes", {})):
        logger.info(f"Semantic cache HIT (similarity: {entry.get('similarity', 1.0):.4f})")
        return entry
    else:
        # Invalidated! Delete from storage
        logger.info(f"Semantic cache INVALIDATED on read: {entry.get('id')} (files changed)")
        if settings.SEMANTIC_CACHE_BACKEND == "qdrant" and qdrant_cache.is_connected():
            qdrant_cache.delete(entry["id"])
        else:
            sqlite.delete_semantic(entry["id"])
        return None


async def set_semantic_cache(
    repo: str,
    branch: str,
    commit_hash: str,
    prompt: str,
    normalized_prompt: str,
    response: str,
    tokens_input: int,
    tokens_output: int,
    file_hashes: dict,
):
    # 1. Generate prompt embedding
    try:
        embedding = await get_embedding(normalized_prompt)
    except Exception as e:
        logger.error(f"Failed to generate embedding for storage: {e}")
        return

    # 2. Save in vector store
    logger.info("Caching semantic entry")
    if settings.SEMANTIC_CACHE_BACKEND == "qdrant" and qdrant_cache.is_connected():
        qdrant_cache.save(
            repo,
            branch,
            commit_hash,
            prompt,
            normalized_prompt,
            response,
            tokens_input,
            tokens_output,
            embedding,
            file_hashes,
        )
    else:
        sqlite.save_semantic(
            repo,
            branch,
            commit_hash,
            prompt,
            normalized_prompt,
            response,
            tokens_input,
            tokens_output,
            embedding,
            file_hashes,
        )
