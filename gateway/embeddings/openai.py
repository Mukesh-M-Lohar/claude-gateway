import hashlib
import logging

import httpx

from gateway.config import settings

logger = logging.getLogger("claude-gateway.embeddings")


def generate_mock_embedding(text: str, dimension: int = 1536) -> list:
    # A deterministic, normalized Bag-of-Words vector for testing similarity
    # Split text into lowercase alphanumeric words
    words = [w.strip() for w in text.lower().split() if w.strip()]

    vector = [0.0] * dimension
    if not words:
        # Return a normalized unit vector of zeros (with first dimension as 1.0)
        vector[0] = 1.0
        return vector

    for word in words:
        # Hash the word to find a deterministic index
        h = hashlib.md5(word.encode("utf-8")).hexdigest()
        idx = int(h, 16) % dimension
        vector[idx] += 1.0

    # Normalize the vector to unit length
    magnitude = sum(x * x for x in vector) ** 0.5
    if magnitude > 0:
        vector = [x / magnitude for x in vector]
    else:
        vector[0] = 1.0

    return vector


async def get_embedding(text: str) -> list:
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "openai":
        is_custom_endpoint = settings.OPENAI_BASE_URL.rstrip("/") != "https://api.openai.com/v1"
        if not settings.OPENAI_API_KEY and not is_custom_endpoint:
            logger.error("OPENAI_API_KEY is not set. Falling back to Mock Embeddings.")
            return generate_mock_embedding(text, settings.EMBEDDING_DIMENSION)

        try:
            url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/embeddings"
            headers = {"Content-Type": "application/json"}
            if settings.OPENAI_API_KEY:
                headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url, headers=headers, json={"model": settings.OPENAI_EMBEDDING_MODEL, "input": text}, timeout=5.0
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"OpenAI/Local Embeddings API call failed to URL {url}: {e}. Falling back to Mock.")
            return generate_mock_embedding(text, settings.EMBEDDING_DIMENSION)

    elif provider == "gemini":
        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not set. Falling back to Mock Embeddings.")
            # Gemini models/text-embedding-004 defaults to 768 dimensions
            return generate_mock_embedding(text, 768)

        try:
            model_name = settings.GEMINI_EMBEDDING_MODEL
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={settings.GEMINI_API_KEY}"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"model": f"models/{model_name}", "content": {"parts": [{"text": text}]}},
                    timeout=5.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["embedding"]["values"]
        except Exception as e:
            logger.error(f"Gemini Embeddings API call failed to URL {url}: {e}. Falling back to Mock.")
            return generate_mock_embedding(text, 768)

    else:
        # Default mock provider
        return generate_mock_embedding(text, settings.EMBEDDING_DIMENSION)
