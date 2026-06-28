# Enterprise Scaling (100+ Developers)

While the default setup runs as a local standalone daemon, Claude Gateway is designed to scale into a centralized enterprise proxy service serving large development teams (100+ developers). 

This guide details the architecture and requirements for a scaled deployment.

---

## 1. Centralized Shared Cache Topology

Instead of developers running independent caches, the proxy can be deployed centrally (e.g. in Kubernetes or an internal cloud subnet) with a shared caching layer:

```
  Dev 1 (CLI) ──┐
  Dev 2 (CLI) ──┼─► Central Load Balancer (AWS ALB / Nginx)
  Dev 3 (CLI) ──┘           │
                            ▼
                  [ Horizontal Gateway Pods ]
                            │
         ┌──────────────────┴──────────────────┐
         ▼                                     ▼
   Shared Redis Cluster                 Shared Qdrant Cluster
   (Shared Exact Caches)                (Shared Semantic Index)
```

### Shared Caching Benefits
- **Exponential Savings**: If Developer A asks a question about a common corporate framework file or shared utility library, Developer B gets an **instant cache hit**.
- **Unified Knowledge Cache**: Standard coding explanations, workspace setup steps, and architectural summaries are cached team-wide, preventing redundant API costs.

---

## 2. API Context Handling at Scale

Centralized gateways cannot use `psutil` local socket lookup to detect a developer's local CWD on their host machine. 

### Workaround: Custom Header Injection
To make the centralized proxy repository-aware, distribute a shell wrapper alias or Git hook that automatically captures Git context and passes it as HTTP request headers:

```bash
# Developer Shell Alias / Function
function claude-central() {
  # Get local repository details
  local repo_name=$(basename $(git rev-parse --show-toplevel 2>/dev/null) 2>/dev/null || echo "global")
  local branch_name=$(git branch --show-current 2>/dev/null || echo "main")
  local commit_hash=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
  local working_dir=$(pwd)

  # Configure CLI to point to central proxy and inject git variables
  export ANTHROPIC_BASE_URL="https://claude-gateway.corp.internal"
  export ANTHROPIC_CUSTOM_HEADERS="X-Git-Repo: $repo_name\nX-Git-Branch: $branch_name\nX-Git-Commit: $commit_hash\nX-Working-Dir: $working_dir"
  
  claude "$@"
}
```

The gateway extracts these `X-Git-*` headers to isolate cache namespaces per repository and evaluate file hashes.

---

## 3. Webhook-Based Invalidation

Running active repository watchers (polling directories via git commands) is not feasible when files reside on 100+ different developer machines.

### Centralized Webhook Integration
To maintain cache freshness at scale:
1.  **Repository Push Events**: Configure your central Git platform (GitHub Enterprise, GitLab, or Bitbucket) to trigger webhooks to the Claude Gateway on every push/merge to code repositories.
2.  **Parser**: The gateway's webhook endpoint parses the push event to extract:
    - Repository name
    - Branch name
    - List of added, modified, or deleted files
3.  **Active Flush**: The gateway runs a background worker to evict any cached entries linked to the modified files in the shared Redis and Qdrant clusters.

---

## 4. High Availability & Authentication

For team-scale stability, security, and logging:

### stateless proxy pods
The FastAPI gateway pods are completely stateless, delegating all operations to Redis and Qdrant. They can be scaled horizontally behind an ingress controller based on CPU/traffic spikes.

### rate limiting & cost controls
- **Auth Proxy Integration**: Authenticate developer CLI requests using Single Sign-On (SSO) or API keys.
- **Cost Allocation**: Log metrics to a central database (e.g. Postgres) tracking savings and spent costs per developer, allowing managers to allocate API budgets.
- **Usage Caps**: Implement rate limiters in FastAPI middleware to prevent abuse or infinite loop API requests.
