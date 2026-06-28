# Caching & Invalidation Architecture

Claude Gateway employs a multi-tiered cache with Git-aware validation to deliver safe, rapid responses.

---

## 1. Prompt Normalization

Before searching the caches, the gateway normalizes prompts to increase the likelihood of cache hits:
1.  **Politeness Stripping**: Leading greetings (e.g. `"Hello Claude"`, `"Hey, hi!"`) and query fillers (e.g. `"please explain"`, `"could you check"`) are stripped using regex pattern matches.
2.  **Case Insensitivity**: Prompts are lowercased.
3.  **Whitespace Compacting**: Multiple sequential whitespaces and newlines are collapsed into a single space.

---

## 2. Exact Cache (SHA-256)

For any normalized prompt:
- A unique SHA-256 key is computed by concatenating the repository name, branch, model, and normalized prompt text.
- If the exact key is found in the database (SQLite or Redis), the cached response text is re-streamed to the client instantly.

---

## 3. Semantic Cache (Vector Similarity)

If the exact cache misses:
- The prompt is converted into a vector embedding.
- A search is run against the vector backend (Qdrant or local SQLite linear scan).
- If the closest match has a cosine similarity above the threshold (default `0.95`), it triggers a semantic hit!

---

## 4. File-Hash Dependency Checks

Caching LLM responses is typically risky because the codebase evolves. Claude Gateway solves this by tracking prompt file dependencies:

1.  **File Extraction**: During a request, the gateway parses the prompt for filenames. If the file exists in the active workspace, its SHA-256 hash is recorded.
2.  **Lazy Validation**: On every cache read (exact or semantic), the gateway checks the current SHA-256 hashes of all referenced files. If any hash does not match the cached signature, the entry is immediately deleted and treated as a cache miss.
3.  **Active Watcher**: A background thread polls repositories every 30 seconds. If `git status` reports changed files or a branch checkout is detected, the watcher proactively deletes any cached prompts referencing those files.
