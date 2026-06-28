# Console Dashboard & Metrics

Claude Gateway features robust observability tools to track your API costs and savings.

---

## 1. Web Console Dashboard

Access the HTML dashboard at `http://127.0.0.1:8000/dashboard` in your browser.

### Key Console Features
- **Savings Cards**: Monitor total USD saved, avoided tokens, overall hit rate, and active caches in real-time.
- **Repository List**: Inspect tracked repositories, branch names, token avoidance, and exact/semantic sizes per repository namespace.
- **Recent Activities**: Review the latest exact and semantic cache logs, including files referenced and total token weights.
- **Invalidation Workspace**: Manually invalidate caches for a specific repository or flush references to a single changed file.
- **Savings Charts**: View a visual bar chart of cost savings accumulated per repository.

---

## 2. Prometheus Exporter

A Prometheus endpoint is exposed at `/metrics` to monitor the proxy within standard monitoring stacks (e.g. Grafana).

### Exposed Metrics

| Metric Name | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `gateway_requests_total` | Counter | `repo`, `model`, `event_type`, `cache_type` | Total requests proxied through the gateway. |
| `gateway_tokens_total` | Counter | `repo`, `model`, `token_type`, `status` | Total input/output tokens processed. |
| `gateway_cost_usd_total` | Counter | `repo`, `model`, `status` | Total cost in USD saved or spent. |

#### Label Values
- **`event_type`**: `hit` \| `miss`
- **`cache_type`**: `exact` \| `semantic` \| `none`
- **`token_type`**: `input` \| `output`
- **`status`**: `saved` (cache hit) \| `spent` (cache miss)
