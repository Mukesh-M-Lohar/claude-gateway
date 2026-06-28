# Architecture Details

Claude Gateway acts as a high-performance HTTP proxy between the **Claude Code** CLI client and the **Anthropic Messages API**.

---

## System Architecture

The following block diagram illustrates the subsystems, databases, background workers, and external connections within the Claude Gateway:

```mermaid
graph TD
    classDef main fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef db fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef external fill:#f59e0b,stroke:#d97706,stroke-width:2px,color:#fff;
    classDef worker fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff;

    Client["Claude Code CLI (Client)"]:::main
    Gateway["Claude Gateway (FastAPI Proxy)"]:::main

    subgraph LocalCache ["Cache Layers"]
        Exact["Exact Match Cache<br/>(Redis / SQLite)"]:::db
        Semantic["Semantic Vector Cache<br/>(Qdrant / SQLite)"]:::db
    end

    subgraph GitContext ["Workspace & Git Context"]
        GitWatcher["Git Repository Watcher<br/>(Polls branch / file changes)"]:::worker
        Invalidation["Cache Invalidation Engine<br/>(SHA-256 File Hash Check)"]:::worker
    end

    subgraph Storage ["Persistent Storage"]
        MetricsDB["SQLite Metrics DB<br/>(Stats, Costs, History)"]:::db
    end

    Anthropic["Anthropic Messages API"]:::external
    LocalLLM["Local Embedding Provider<br/>(Ollama / LM Studio / Gemini / OpenAI)"]:::external

    %% Data Flows
    Client -->|1. POST /v1/messages| Gateway
    Gateway -->|2. Check PID CWD / Git info| GitContext
    Gateway -->|3. Compute normalized hash & check| Exact

    Exact -->|Hit & Valid| Client
    Exact -->|Miss / Stale| Semantic

    Semantic -->|4. Get embeddings| LocalLLM
    Semantic -->|Hit & Valid| Client

    Semantic -->|Miss| Anthropic
    Anthropic -->|5. Stream response chunks| Gateway
    Gateway -->|6. Stream response & Cache| Client

    %% Cache Updates & Invalidation
    Gateway -.->|Update cache entries & file hashes| LocalCache
    Gateway -.->|Write token & cost metrics| MetricsDB
    GitWatcher -->|Invalidates stale keys| LocalCache
    Invalidation -->|Verify file hashes on-read| LocalCache
```

---

## Request Lifecycle

The diagram below details how a request is processed from client entry to streaming completion:

```mermaid
sequenceDiagram
    autonumber
    actor Developer as Claude Code (CLI)
    participant Gateway as Claude Gateway (FastAPI)
    participant DB as SQLite / Redis
    participant Vector as SQLite / Qdrant
    participant LLM as Anthropic API

    Developer->>Gateway: POST /v1/messages
    Note over Gateway: 1. Detect CWD/PID via psutil<br/>2. Extract & Normalize prompt<br/>3. Resolve referenced file hashes

    Gateway->>DB: Check Exact Cache (SHA-256 Key)
    alt Exact Cache Hit & File Hashes Valid
        DB-->>Gateway: Return cached response text
        Gateway-->>Developer: Replay cached text stream (SSE)
    else Exact Cache Miss / Stale
        Gateway->>Vector: Generate embedding & Search (Threshold 0.95)
        alt Semantic Cache Hit & File Hashes Valid
            Vector-->>Gateway: Return semantic response text
            Gateway-->>Developer: Replay cached text stream (SSE)
        else Semantic Cache Miss
            Gateway->>LLM: Forward POST /v1/messages
            loop Real-time Stream
                LLM-->>Gateway: SSE Token Chunks
                Gateway-->>Developer: Forward SSE tokens instantly
                Note over Gateway: Accumulate tokens in buffer
            end
            Note over Gateway: Stream Completed
            Gateway->>DB: Store Exact Cache & file hashes
            Gateway->>Vector: Store Semantic Cache vector & payload
            Gateway->>DB: Log miss cost/token usage metrics
        end
    end
```

---

## Architectural Subsystems

### 1. Context Resolution (`gateway/git/context.py` & `repository.py`)
- **Local PID Tracking**: Inspects system connections to link the client's TCP socket port to the process ID (PID) on the host machine.
- **Directory Path Lookup**: Inspects the PID's execution environment to extract the current working directory (CWD), walking up the tree to locate the `.git` folder.
- **Repository Identifiers**: Pulls the active branch, commit hash, and working tree modification status directly from git files (very fast) or fallback CLI commands.

### 2. Cache Invalidation Control (`gateway/cache/invalidation.py`)
- **Regex Normalization**: Strips polite phrases and compacts spacing so minor syntax variations hit the cache.
- **Workspace Verification**: Scans prompt text for filenames, checks if they exist in the repository, and hashes them using SHA-256.
- **Lazy Check**: Validates that files are in their cached state on read before returning a hit. Stale caches are immediately evicted.
- **Background Watcher**: Polls repository directories. If a branch changes or `git status` reveals a file modification, any cached prompt linked to that file is immediately deleted.

### 3. Exporter & Metrics (`gateway/metrics/prometheus.py` & `storage/sqlite.py`)
- Log entries are written to a lightweight SQLite database recording tokens avoiding/spent and calculated cost values.
- Exposes standard `/metrics` endpoints for scrape-based Grafana dashboard configurations.
- Serves an embedded responsive single-page analytics dashboard for developers.
