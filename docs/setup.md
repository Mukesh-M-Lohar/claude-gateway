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
| `OPENAI_API_KEY` | `""` | Optional. Required if `EMBEDDING_PROVIDER=openai` (unless using local endpoints). |
| `GEMINI_API_KEY` | `""` | Optional. Required if `EMBEDDING_PROVIDER=gemini`. |
| `EXACT_CACHE_BACKEND` | `sqlite` | Select `"sqlite"` or `"redis"`. |
| `SEMANTIC_CACHE_BACKEND` | `sqlite` | Select `"sqlite"` or `"qdrant"`. |
| `EMBEDDING_PROVIDER` | `mock` | Select `"openai"`, `"gemini"`, or `"mock"`. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Custom endpoint for OpenAI-compatible local services (e.g. Ollama, LM Studio). |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | The model name to request from your OpenAI-compatible provider. |
| `EMBEDDING_DIMENSION` | `1536` | Dimensions of the embedding model (e.g., 768 for `nomic-embed-text`). |
| `GEMINI_EMBEDDING_MODEL` | `text-embedding-004` | Model name to use when `EMBEDDING_PROVIDER` is set to `gemini`. |
| `SIMILARITY_THRESHOLD` | `0.95` | Similarity threshold for semantic cache hits (0.0 - 1.0). |
| `GIT_WATCHER_INTERVAL` | `30` | Rate in seconds to poll repository changes. |

---

## 4. Using Lower-Cost Models

Claude Code defaults to using `claude-3-5-sonnet`. You can run Claude Code with a smaller, faster, and more cost-effective model like `claude-3-5-haiku` by passing the `--model` flag:

```bash
claude --model claude-3-5-haiku
```

Claude Gateway automatically detects the model specified by the client request, calculates the corresponding token pricing, and tracks it in your metrics dashboard.

---

## 5. Using Local LLMs for Embeddings

By default, the gateway uses a local bag-of-words `"mock"` provider to generate embeddings. If you want high-quality semantic caching without paying API fees to OpenAI or Google, you can route your embeddings to a local model running on your machine using **Ollama** or **LM Studio**.

### Example: Configuring Ollama
1. Run Ollama locally and pull an embedding model:
   ```bash
   ollama pull nomic-embed-text
   ```
2. Configure your `.env` file to use Ollama's OpenAI-compatible endpoint:
   ```ini
   EMBEDDING_PROVIDER=openai
   OPENAI_BASE_URL=http://localhost:11434/v1
   OPENAI_EMBEDDING_MODEL=nomic-embed-text
   EMBEDDING_DIMENSION=768
   ```

### Example: Configuring LM Studio
1. Open LM Studio, download/load an embedding model, and start the local server on port `1234`.
2. Configure your `.env`:
   ```ini
   EMBEDDING_PROVIDER=openai
   OPENAI_BASE_URL=http://localhost:1234/v1
   OPENAI_EMBEDDING_MODEL=your-loaded-embedding-model
   EMBEDDING_DIMENSION=your-model-dimension
   ```
