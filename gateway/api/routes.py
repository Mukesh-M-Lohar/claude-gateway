from pathlib import Path
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

from gateway.config import settings
from gateway.providers.anthropic import proxy_messages
from gateway.metrics.prometheus import get_prometheus_metrics_payload
from gateway.storage import sqlite
from gateway.storage.redis import redis_client
from gateway.storage.qdrant import qdrant_cache

router = APIRouter()

# Resolve templates folder relative to this file
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

class InvalidateRequest(BaseModel):
    repo: str
    file: Optional[str] = None

@router.post("/v1/messages")
async def messages(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    return await proxy_messages(body, request)

@router.get("/metrics")
async def metrics():
    payload, content_type = get_prometheus_metrics_payload()
    return Response(content=payload, media_type=content_type)

@router.get("/")
@router.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@router.get("/api/stats")
async def get_stats():
    try:
        summary = sqlite.get_summary_stats()
        repos = sqlite.get_repo_stats()
        recent = sqlite.get_all_cached_entries()
        return {
            "summary": summary,
            "repos": repos,
            "recent": recent
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/invalidate")
async def invalidate_cache(payload: InvalidateRequest):
    repo = payload.repo
    file_path = payload.file
    
    if not repo:
        raise HTTPException(status_code=400, detail="Repository name is required.")
        
    try:
        if file_path:
            # Normalize file path (strip leading slashes, convert backslashes)
            file_path = file_path.strip().replace("\\", "/").lstrip("/")
            
            # Invalidate specific file across backends
            sqlite.invalidate_exact_by_files(repo, [file_path])
            sqlite.invalidate_semantic_by_files(repo, [file_path])
            redis_client.invalidate_by_files(repo, [file_path])
            qdrant_cache.invalidate_by_files(repo, [file_path])
            
            return {"detail": f"Successfully invalidated cache entries for file: '{file_path}' in repo: '{repo}'."}
        else:
            # Flush entire repository
            sqlite.invalidate_all_for_repo(repo)
            redis_client.invalidate_all_for_repo(repo)
            qdrant_cache.invalidate_all_for_repo(repo)
            
            return {"detail": f"Successfully flushed all cache entries for repository: '{repo}'."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}")
