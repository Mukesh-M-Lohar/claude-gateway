import logging

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest

logger = logging.getLogger("claude-gateway.metrics.prometheus")

# Create a custom registry to avoid pollution of default python metrics
registry = CollectorRegistry()

# Counters
REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total requests proxied through the Claude Gateway",
    labelnames=[
        "repo",
        "model",
        "event_type",
        "cache_type",
    ],  # event_type='hit'/'miss', cache_type='exact'/'semantic'/'none'
    registry=registry,
)

TOKENS_TOTAL = Counter(
    "gateway_tokens_total",
    "Total tokens processed (avoided or spent)",
    labelnames=["repo", "model", "token_type", "status"],  # token_type='input'/'output', status='saved'/'spent'
    registry=registry,
)

COST_TOTAL = Counter(
    "gateway_cost_usd_total",
    "Total cost in USD (saved or spent)",
    labelnames=["repo", "model", "status"],  # status='saved'/'spent'
    registry=registry,
)


def record_request_metrics(
    repo: str, model: str, event_type: str, cache_type: str, tokens_input: int, tokens_output: int, cost: float
):
    try:
        # Record request
        REQUESTS_TOTAL.labels(repo=repo, model=model, event_type=event_type, cache_type=cache_type).inc()

        # Determine status (saved if hit, spent if miss)
        status = "saved" if event_type == "hit" else "spent"

        # Record tokens
        TOKENS_TOTAL.labels(repo=repo, model=model, token_type="input", status=status).inc(tokens_input)

        TOKENS_TOTAL.labels(repo=repo, model=model, token_type="output", status=status).inc(tokens_output)

        # Record cost
        COST_TOTAL.labels(repo=repo, model=model, status=status).inc(cost)
    except Exception as e:
        logger.error(f"Failed to record Prometheus metrics: {e}")


def get_prometheus_metrics_payload() -> tuple:
    # Returns (payload, content_type)
    return generate_latest(registry), CONTENT_TYPE_LATEST
