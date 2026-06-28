# Claude Gateway

Claude Gateway is a high-performance local proxy daemon designed to accelerate **Claude Code** and reduce API costs. It sits between Claude Code and the Anthropic API, intercepting requests to serve cached responses using a dual-layer exact and semantic cache.

---

## Key Features

*   **Exact Cache (Redis / SQLite)**: Instantly resolves identical prompt requests within milliseconds.
*   **Semantic Cache (Qdrant / SQLite)**: Matches similar prompts with a configurable cosine similarity threshold (default `0.95`).
*   **Git Context Detection**: Dynamically tracks client requests using `psutil` to extract the caller's working directory, namespace, active branch, and current commit.
*   **On-Read File Invalidation**: Automatically extracts file names from prompts, hashes their contents, and invalidates cached entries if the referenced files are modified.
*   **Background Watcher**: Polls repositories for working tree updates and checkout events, keeping caches clean.
*   **Metrics Dashboard**: A stunning glassmorphic UI console displaying USD cost savings, token metrics, and cache sizes, alongside Prometheus `/metrics` endpoints.

---

## Architectural Flow

```
   Claude Code (CLI)
         │
         ▼ (ANTHROPIC_BASE_URL)
   Claude Gateway (FastAPI)
         │
         ├─► Normalizes prompt (greets/fillers removed)
         │
         ├─► Computes Exact SHA-256 Key
         │     └─► Hits Redis/SQLite? ──► [YES] ──► Streams response back (0ms)
         │
         ├─► Generates Text Embedding
         │     └─► Hits Qdrant/SQLite? ──► [YES] ──► Streams response back (5ms)
         │
         └─► Cache MISS
               └─► Intercepts Anthropic stream ──► Caches content ──► Streams back
```
