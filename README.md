# Claude Gateway

Claude Gateway is a high-performance local proxy daemon designed to accelerate **Claude Code** and reduce API costs. It intercepts Claude's messages requests, analyzes the repository context, and coordinates a dual-layer cache (Exact + Semantic) with automatic Git-aware invalidation.

---

## Features

- **Exact Cache (Redis / SQLite)**: Instantly resolves identical prompt requests within milliseconds.
- **Semantic Cache (Qdrant / SQLite)**: Uses text embeddings (OpenAI, Gemini, or a zero-cost local mock) to match similar prompts with a configurable threshold (default `0.95`).
- **Git Context Detection**: Dynamically tracks client requests using `psutil` to extract the caller's working directory, namespace, active branch, and current commit.
- **On-Read File Invalidation**: Automatically extracts file names from prompts, hashes their contents, and invalidates cached entries if the referenced files are modified.
- **Background Watcher**: Polls repositories for working tree updates and checkout events, keeping caches clean.
- **Metrics Dashboard**: A stunning glassmorphic UI console displaying USD cost savings, token metrics, and cache sizes, alongside Prometheus `/metrics` endpoints.

---

## 1. Quick Start (Local Setup)

### Prerequisites
- Python 3.12+ (standard `py` launcher on Windows)
- Git (in your PATH)

### Install Dependencies
Navigate to the directory and run:
```bash
py -m pip install -r requirements.txt
```

### Configure Settings
Create a `.env` file at the root of the project (see the `.env` Configuration section below).

### Start the Gateway
```bash
py main.py
```
The server starts on `http://127.0.0.1:8000`. You can access the UI dashboard at `http://127.0.0.1:8000/dashboard`.

### Point Claude Code at the Gateway
Set the `ANTHROPIC_BASE_URL` environment variable before running `claude`:
- **Windows (PowerShell)**:
  ```powershell
  $env:ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
  claude
  ```
- **macOS / Linux / WSL**:
  ```bash
  export ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
  claude
  ```

---

## 2. `.env` Configuration

Create a file named `.env` in the project root to override settings.

### Sample `.env` File
```ini
# Server Settings
HOST=127.0.0.1
PORT=8000

# API Keys
# Your Anthropic Key (can also be passed directly in the client CLI header)
ANTHROPIC_API_KEY=sk-ant-xxx...
# Required if EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-proj-xxx...
# Required if EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...

# Caching Backends ("sqlite" or "redis" / "qdrant")
EXACT_CACHE_BACKEND=sqlite
SEMANTIC_CACHE_BACKEND=sqlite

# Embedding Provider ("openai", "gemini", or "mock" for zero-cost)
EMBEDDING_PROVIDER=mock

# Threshold for Semantic cache similarity matches
SIMILARITY_THRESHOLD=0.95

# Active poll interval for Git repository changes (in seconds)
GIT_WATCHER_INTERVAL=30
```

### Configuration Variables Reference
| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `127.0.0.1` | The host uvicorn binds to. |
| `PORT` | `8000` | The port the gateway listens on. |
| `ANTHROPIC_API_KEY` | `""` | Fallback Anthropic API key. |
| `OPENAI_API_KEY` | `""` | OpenAI API key for embeddings. |
| `GEMINI_API_KEY` | `""` | Google AI key for Gemini embeddings. |
| `EXACT_CACHE_BACKEND` | `sqlite` | Cache engine for exact match (`sqlite` or `redis`). |
| `SEMANTIC_CACHE_BACKEND` | `sqlite` | Cache engine for semantic match (`sqlite` or `qdrant`). |
| `EMBEDDING_PROVIDER` | `mock` | Embedding method (`openai`, `gemini`, or `mock` which runs a deterministic local bag-of-words vector). |
| `SQLITE_DB_PATH` | `<base>/gateway.db` | Target path for the SQLite database. |
| `SIMILARITY_THRESHOLD` | `0.95` | Cosine similarity cutoff for semantic hits. |
| `GIT_WATCHER_INTERVAL` | `30` | Polling rate in seconds to check Git repositories for changes. |

---

## 3. Running Containerized (Docker Setup)

The project includes a `Dockerfile` and `docker-compose.yml` to run the gateway alongside Redis and Qdrant in a multi-container network.

### Docker Quickstart
```bash
docker compose up -d --build
```
This launches:
- **FastAPI Gateway** on port `8000`
- **Redis** on port `6379`
- **Qdrant** on port `6333`

---

## 4. Docker Systems Architecture Limitations & Workarounds

> [!WARNING]
> **Docker Process / Port Namespace Isolation**
> By default, Docker runs in an isolated network and PID namespace. This means the gateway running **inside** the container cannot use `psutil` to inspect connections originating on the **host** machine, preventing automatic CWD (working directory) detection.

### Linux Workaround
On Linux hosts, you can bypass namespace isolation entirely by configuring Docker Compose to share host process and network namespaces. Add these fields to the `gateway` service definition in `docker-compose.yml`:
```yaml
network_mode: "host"
pid: "host"
```

### Cross-Platform Workaround (Windows / macOS / WSL)
If running on Windows or Mac, share namespaces is not natively supported. To make the Docker container repository-aware, pass the current working directory explicitly in the HTTP request headers using Claude Code's custom header injection.

Set up an alias in your shell configurations (`~/.bashrc`, `~/.zshrc`, or PowerShell Profile) to capture the current directory before starting Claude:

- **Bash / Zsh Alias**:
  ```bash
  function claude-proxy() {
    export ANTHROPIC_BASE_URL="http://localhost:8000"
    export ANTHROPIC_CUSTOM_HEADERS="X-Working-Dir: $(pwd)"
    claude "$@"
  }
  ```
- **PowerShell Function**:
  ```powershell
  function claude-proxy {
      $env:ANTHROPIC_BASE_URL="http://localhost:8000"
      $env:ANTHROPIC_CUSTOM_HEADERS="X-Working-Dir: $(Get-Location)"
      claude $args
  }
  ```

With this alias, running `claude-proxy` will automatically transmit your CWD to the containerized daemon, allowing it to perform exact cache mappings, fetch Git metadata, and run file hash checks correctly.
