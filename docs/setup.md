# Installation & Configuration

Learn how to get started with Claude Gateway on your local machine.

---

## 1. Quick Start

### Prerequisites
- Python 3.12+ (standard `py` launcher on Windows)
- Git (in your PATH)

### Install Dependencies
Run the installation command in your terminal:
```bash
py -m pip install -r requirements.txt
```

### Start the Gateway
```bash
py main.py
```
The server starts locally on `http://127.0.0.1:8000`. 
Access the console dashboard at `http://127.0.0.1:8000/dashboard`.

---

## 2. Shell Configuration

To route Claude Code requests through the gateway, set the `ANTHROPIC_BASE_URL` environment variable in your active terminal:

=== "Windows (PowerShell)"
    ```powershell
    $env:ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
    claude
    ```

=== "macOS / Linux / WSL"
    ```bash
    export ANTHROPIC_BASE_URL="http://127.0.0.1:8000"
    claude
    ```

---

## 3. Environment Variables (`.env`)

Configure the application behavior by creating a `.env` file at the root:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `HOST` | `127.0.0.1` | Host address uvicorn binds to. |
| `PORT` | `8000` | Port uvicorn listens on. |
| `ANTHROPIC_API_KEY` | `""` | Fallback Anthropic API key. |
| `OPENAI_API_KEY` | `""` | Required if `EMBEDDING_PROVIDER` is set to `openai`. |
| `GEMINI_API_KEY` | `""` | Required if `EMBEDDING_PROVIDER` is set to `gemini`. |
| `EXACT_CACHE_BACKEND` | `sqlite` | Select `"sqlite"` or `"redis"`. |
| `SEMANTIC_CACHE_BACKEND` | `sqlite` | Select `"sqlite"` or `"qdrant"`. |
| `EMBEDDING_PROVIDER` | `mock` | Select `"openai"`, `"gemini"`, or `"mock"`. |
| `SIMILARITY_THRESHOLD` | `0.95` | Similarity threshold for semantic cache hits (0.0 - 1.0). |
| `GIT_WATCHER_INTERVAL` | `30` | Rate in seconds to poll repository changes. |
