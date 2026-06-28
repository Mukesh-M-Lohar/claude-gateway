import logging
from datetime import datetime
from gateway.config import settings

logger = logging.getLogger("claude-gateway.qdrant")

try:
    from qdrant_client import QdrantClient as RealQdrantClient
    from qdrant_client.http import models as qmodels
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("qdrant-client library not installed. Qdrant cache disabled.")

class QdrantCache:
    def __init__(self):
        self.client = None
        if QDRANT_AVAILABLE and settings.SEMANTIC_CACHE_BACKEND == "qdrant":
            try:
                self.client = RealQdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    timeout=2.0
                )
                self.ensure_collection()
                logger.info(f"Connected to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant: {e}. Falling back to SQLite.")
                self.client = None

    def is_connected(self) -> bool:
        return self.client is not None

    def ensure_collection(self):
        if not self.client:
            return
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            if settings.QDRANT_COLLECTION not in collection_names:
                self.client.create_collection(
                    collection_name=settings.QDRANT_COLLECTION,
                    vectors_config=qmodels.VectorParams(
                        size=settings.EMBEDDING_DIMENSION,
                        distance=qmodels.Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {settings.QDRANT_COLLECTION}")
        except Exception as e:
            logger.error(f"Error creating/checking Qdrant collection: {e}")
            self.client = None

    def get(self, repo: str, branch: str, embedding: list, threshold: float) -> dict:
        if not self.client:
            from gateway.storage import sqlite
            return sqlite.get_semantic(repo, branch, embedding, threshold)

        try:
            # Query Qdrant with filters for repo and branch
            # We filter by repo to keep repo awareness
            result = self.client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=embedding,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="repo",
                            match=qmodels.MatchValue(value=repo)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            
            if result and result[0].score >= threshold:
                hit = result[0]
                payload = hit.payload
                return {
                    "id": hit.id,
                    "repo": payload.get("repo"),
                    "branch": payload.get("branch"),
                    "commit_hash": payload.get("commit_hash"),
                    "prompt": payload.get("prompt"),
                    "normalized_prompt": payload.get("normalized_prompt"),
                    "response": payload.get("response"),
                    "tokens_input": payload.get("tokens_input", 0),
                    "tokens_output": payload.get("tokens_output", 0),
                    "created_at": payload.get("created_at"),
                    "file_hashes": payload.get("file_hashes", {}),
                    "similarity": hit.score
                }
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            from gateway.storage import sqlite
            return sqlite.get_semantic(repo, branch, embedding, threshold)
        return None

    def save(self, repo: str, branch: str, commit_hash: str, prompt: str, normalized_prompt: str, response: str, tokens_input: int, tokens_output: int, embedding: list, file_hashes: dict):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.save_semantic(repo, branch, commit_hash, prompt, normalized_prompt, response, tokens_input, tokens_output, embedding, file_hashes)
            return

        try:
            import uuid
            point_id = str(uuid.uuid4())
            payload = {
                "repo": repo,
                "branch": branch,
                "commit_hash": commit_hash,
                "prompt": prompt,
                "normalized_prompt": normalized_prompt,
                "response": response,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "created_at": datetime.utcnow().isoformat(),
                "file_hashes": file_hashes
            }
            
            self.client.upsert(
                collection_name=settings.QDRANT_COLLECTION,
                points=[
                    qmodels.PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
        except Exception as e:
            logger.error(f"Qdrant upsert error: {e}")
            from gateway.storage import sqlite
            sqlite.save_semantic(repo, branch, commit_hash, prompt, normalized_prompt, response, tokens_input, tokens_output, embedding, file_hashes)

    def delete(self, entry_id: str):
        if not self.client:
            from gateway.storage import sqlite
            # In sqlite, entry_id is integer
            try:
                sqlite.delete_semantic(int(entry_id))
            except ValueError:
                pass
            return
        try:
            self.client.delete(
                collection_name=settings.QDRANT_COLLECTION,
                points_selector=qmodels.PointIdsList(points=[entry_id])
            )
        except Exception as e:
            logger.error(f"Qdrant delete error: {e}")

    def invalidate_by_files(self, repo: str, files: list):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.invalidate_semantic_by_files(repo, files)
            return

        try:
            # We must fetch points for the repo first to check their payloads
            # Because filtering inside payload dictionaries is complex in Qdrant schemas
            # Scroll/search all points for this repo
            offset = None
            points_to_delete = []
            
            while True:
                res = self.client.scroll(
                    collection_name=settings.QDRANT_COLLECTION,
                    scroll_filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="repo",
                                match=qmodels.MatchValue(value=repo)
                            )
                        ]
                    ),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )
                
                points, next_offset = res
                for p in points:
                    file_hashes = p.payload.get("file_hashes", {})
                    for file in files:
                        if file in file_hashes:
                            points_to_delete.append(p.id)
                            break
                            
                offset = next_offset
                if not offset or len(points) == 0:
                    break
                    
            if points_to_delete:
                self.client.delete(
                    collection_name=settings.QDRANT_COLLECTION,
                    points_selector=qmodels.PointIdsList(points=points_to_delete)
                )
        except Exception as e:
            logger.error(f"Qdrant invalidate error: {e}")
            from gateway.storage import sqlite
            sqlite.invalidate_semantic_by_files(repo, files)

    def invalidate_all_for_repo(self, repo: str):
        if not self.client:
            from gateway.storage import sqlite
            sqlite.invalidate_all_for_repo(repo)
            return

        try:
            self.client.delete(
                collection_name=settings.QDRANT_COLLECTION,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="repo",
                                match=qmodels.MatchValue(value=repo)
                            )
                        ]
                    )
                )
            )
        except Exception as e:
            logger.error(f"Qdrant clear repo error: {e}")
            from gateway.storage import sqlite
            sqlite.invalidate_all_for_repo(repo)

# Singleton Qdrant Client
qdrant_cache = QdrantCache()
