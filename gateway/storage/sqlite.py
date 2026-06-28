import json
import sqlite3
import math
from datetime import datetime
from gateway.config import settings

def get_db_connection():
    conn = sqlite3.connect(settings.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create exact cache table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exact_cache (
        key TEXT PRIMARY KEY,
        response TEXT NOT NULL,
        tokens_input INTEGER NOT NULL,
        tokens_output INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        repo TEXT NOT NULL,
        branch TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        file_hashes TEXT NOT NULL  -- JSON dict of {filepath: sha256}
    )
    """)
    
    # Create semantic cache table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS semantic_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo TEXT NOT NULL,
        branch TEXT NOT NULL,
        commit_hash TEXT NOT NULL,
        prompt TEXT NOT NULL,
        normalized_prompt TEXT NOT NULL,
        response TEXT NOT NULL,
        tokens_input INTEGER NOT NULL,
        tokens_output INTEGER NOT NULL,
        embedding TEXT NOT NULL,      -- JSON array of floats
        created_at TEXT NOT NULL,
        file_hashes TEXT NOT NULL     -- JSON dict of {filepath: sha256}
    )
    """)
    
    # Create metrics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        repo TEXT NOT NULL,
        model TEXT NOT NULL,
        event_type TEXT NOT NULL,     -- 'hit' or 'miss'
        cache_type TEXT NOT NULL,     -- 'exact', 'semantic', or 'none'
        tokens_input INTEGER NOT NULL,
        tokens_output INTEGER NOT NULL,
        cost REAL NOT NULL            -- cost in USD
    )
    """)
    
    # Create repo registry table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repo_registry (
        repo TEXT PRIMARY KEY,
        root TEXT NOT NULL,
        last_seen TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

# Cosine similarity helper
def cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude_v1 = math.sqrt(sum(x * x for x in v1))
    magnitude_v2 = math.sqrt(sum(x * x for x in v2))
    if magnitude_v1 == 0 or magnitude_v2 == 0:
        return 0.0
    return dot_product / (magnitude_v1 * magnitude_v2)

# Exact Cache Operations
def get_exact(key: str) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exact_cache WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "key": row["key"],
            "response": row["response"],
            "tokens_input": row["tokens_input"],
            "tokens_output": row["tokens_output"],
            "created_at": row["created_at"],
            "repo": row["repo"],
            "branch": row["branch"],
            "commit_hash": row["commit_hash"],
            "file_hashes": json.loads(row["file_hashes"])
        }
    return None

def save_exact(key: str, repo: str, branch: str, commit_hash: str, response: str, tokens_input: int, tokens_output: int, file_hashes: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO exact_cache 
    (key, response, tokens_input, tokens_output, created_at, repo, branch, commit_hash, file_hashes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (key, response, tokens_input, tokens_output, now_str, repo, branch, commit_hash, json.dumps(file_hashes)))
    conn.commit()
    conn.close()

def delete_exact(key: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exact_cache WHERE key = ?", (key,))
    conn.commit()
    conn.close()

def invalidate_exact_by_files(repo: str, files: list):
    if not files:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, file_hashes FROM exact_cache WHERE repo = ?", (repo,))
    rows = cursor.fetchall()
    
    keys_to_delete = []
    for row in rows:
        file_hashes = json.loads(row["file_hashes"])
        for file in files:
            if file in file_hashes:
                keys_to_delete.append(row["key"])
                break
                
    for key in keys_to_delete:
        cursor.execute("DELETE FROM exact_cache WHERE key = ?", (key,))
        
    conn.commit()
    conn.close()

# Semantic Cache Operations
def get_semantic(repo: str, branch: str, embedding: list, threshold: float) -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    # Filter by repo to ensure cache boundary
    cursor.execute("SELECT * FROM semantic_cache WHERE repo = ?", (repo,))
    rows = cursor.fetchall()
    conn.close()
    
    best_match = None
    best_similarity = -1.0
    
    for row in rows:
        try:
            cached_embedding = json.loads(row["embedding"])
            sim = cosine_similarity(embedding, cached_embedding)
            if sim > best_similarity:
                best_similarity = sim
                best_match = row
        except Exception:
            continue
            
    if best_match and best_similarity >= threshold:
        return {
            "id": best_match["id"],
            "repo": best_match["repo"],
            "branch": best_match["branch"],
            "commit_hash": best_match["commit_hash"],
            "prompt": best_match["prompt"],
            "normalized_prompt": best_match["normalized_prompt"],
            "response": best_match["response"],
            "tokens_input": best_match["tokens_input"],
            "tokens_output": best_match["tokens_output"],
            "created_at": best_match["created_at"],
            "file_hashes": json.loads(best_match["file_hashes"]),
            "similarity": best_similarity
        }
    return None

def save_semantic(repo: str, branch: str, commit_hash: str, prompt: str, normalized_prompt: str, response: str, tokens_input: int, tokens_output: int, embedding: list, file_hashes: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO semantic_cache 
    (repo, branch, commit_hash, prompt, normalized_prompt, response, tokens_input, tokens_output, embedding, created_at, file_hashes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (repo, branch, commit_hash, prompt, normalized_prompt, response, tokens_input, tokens_output, json.dumps(embedding), now_str, json.dumps(file_hashes)))
    conn.commit()
    conn.close()

def delete_semantic(entry_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM semantic_cache WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

def invalidate_semantic_by_files(repo: str, files: list):
    if not files:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_hashes FROM semantic_cache WHERE repo = ?", (repo,))
    rows = cursor.fetchall()
    
    ids_to_delete = []
    for row in rows:
        file_hashes = json.loads(row["file_hashes"])
        for file in files:
            if file in file_hashes:
                ids_to_delete.append(row["id"])
                break
                
    for entry_id in ids_to_delete:
        cursor.execute("DELETE FROM semantic_cache WHERE id = ?", (entry_id,))
        
    conn.commit()
    conn.close()

# Invalidate all caches for a repository
def invalidate_all_for_repo(repo: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exact_cache WHERE repo = ?", (repo,))
    cursor.execute("DELETE FROM semantic_cache WHERE repo = ?", (repo,))
    conn.commit()
    conn.close()

# Metrics Operations
def save_metric(repo: str, model: str, event_type: str, cache_type: str, tokens_input: int, tokens_output: int, cost: float):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO metrics (timestamp, repo, model, event_type, cache_type, tokens_input, tokens_output, cost)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (now_str, repo, model, event_type, cache_type, tokens_input, tokens_output, cost))
    conn.commit()
    conn.close()

def get_summary_stats() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Calculate costs saved and spent
    # A 'hit' saves the tokens that would have been processed
    cursor.execute("""
    SELECT 
        SUM(CASE WHEN event_type = 'hit' THEN cost ELSE 0 END) as cost_saved,
        SUM(CASE WHEN event_type = 'miss' THEN cost ELSE 0 END) as cost_spent,
        SUM(CASE WHEN event_type = 'hit' THEN (tokens_input + tokens_output) ELSE 0 END) as tokens_avoided,
        SUM(CASE WHEN event_type = 'miss' THEN (tokens_input + tokens_output) ELSE 0 END) as tokens_spent,
        COUNT(CASE WHEN event_type = 'hit' THEN 1 END) as hits_count,
        COUNT(CASE WHEN event_type = 'miss' THEN 1 END) as misses_count
    FROM metrics
    """)
    row = cursor.fetchone()
    conn.close()
    
    cost_saved = row["cost_saved"] or 0.0
    cost_spent = row["cost_spent"] or 0.0
    tokens_avoided = row["tokens_avoided"] or 0
    tokens_spent = row["tokens_spent"] or 0
    hits = row["hits_count"] or 0
    misses = row["misses_count"] or 0
    
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0.0
    
    return {
        "cost_saved": round(cost_saved, 4),
        "cost_spent": round(cost_spent, 4),
        "tokens_avoided": tokens_avoided,
        "tokens_spent": tokens_spent,
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hit_rate, 1)
    }

def get_repo_stats() -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT 
        repo,
        COUNT(CASE WHEN event_type = 'hit' THEN 1 END) as hits,
        COUNT(CASE WHEN event_type = 'miss' THEN 1 END) as misses,
        SUM(CASE WHEN event_type = 'hit' THEN (tokens_input + tokens_output) ELSE 0 END) as tokens_avoided,
        SUM(CASE WHEN event_type = 'hit' THEN cost ELSE 0 END) as cost_saved
    FROM metrics
    GROUP BY repo
    """)
    rows = cursor.fetchall()
    
    # Get exact & semantic cache sizes per repository
    cursor.execute("SELECT repo, COUNT(*) as cache_size FROM exact_cache GROUP BY repo")
    exact_sizes = {r["repo"]: r["cache_size"] for r in cursor.fetchall()}
    
    cursor.execute("SELECT repo, COUNT(*) as cache_size FROM semantic_cache GROUP BY repo")
    semantic_sizes = {r["repo"]: r["cache_size"] for r in cursor.fetchall()}
    
    conn.close()
    
    result = []
    for row in rows:
        repo = row["repo"]
        total = row["hits"] + row["misses"]
        hit_rate = (row["hits"] / total * 100) if total > 0 else 0.0
        
        result.append({
            "repo": repo,
            "hits": row["hits"],
            "misses": row["misses"],
            "hit_rate": round(hit_rate, 1),
            "tokens_avoided": row["tokens_avoided"] or 0,
            "cost_saved": round(row["cost_saved"] or 0.0, 4),
            "exact_cache_size": exact_sizes.get(repo, 0),
            "semantic_cache_size": semantic_sizes.get(repo, 0)
        })
    return result

def get_all_cached_entries() -> dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT key, repo, branch, created_at, tokens_input + tokens_output as total_tokens, file_hashes FROM exact_cache ORDER BY created_at DESC LIMIT 50")
    exact = []
    for r in cursor.fetchall():
        exact.append({
            "key": r["key"],
            "repo": r["repo"],
            "branch": r["branch"],
            "created_at": r["created_at"],
            "total_tokens": r["total_tokens"],
            "files": list(json.loads(r["file_hashes"]).keys())
        })
        
    cursor.execute("SELECT id, repo, branch, prompt, created_at, tokens_input + tokens_output as total_tokens, file_hashes FROM semantic_cache ORDER BY created_at DESC LIMIT 50")
    semantic = []
    for r in cursor.fetchall():
        semantic.append({
            "id": r["id"],
            "repo": r["repo"],
            "branch": r["branch"],
            "prompt": r["prompt"],
            "created_at": r["created_at"],
            "total_tokens": r["total_tokens"],
            "files": list(json.loads(r["file_hashes"]).keys())
        })
        
    conn.close()
    return {"exact": exact, "semantic": semantic}

def register_repo(repo: str, root: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT OR REPLACE INTO repo_registry (repo, root, last_seen)
    VALUES (?, ?, ?)
    """, (repo, root, now_str))
    conn.commit()
    conn.close()

def get_registered_repos() -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM repo_registry")
    rows = cursor.fetchall()
    conn.close()
    return [{"repo": r["repo"], "root": r["root"], "last_seen": r["last_seen"]} for r in rows]

