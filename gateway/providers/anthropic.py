import json
import logging
import asyncio
import httpx
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, Response
from gateway.config import settings
from gateway.git.context import get_client_cwd
from gateway.git.repository import get_git_info
from gateway.cache.invalidation import normalize_prompt, extract_filenames, get_file_hashes
from gateway.cache.exact import get_exact_cache, set_exact_cache
from gateway.cache.semantic import get_semantic_cache, set_semantic_cache
from gateway.storage import sqlite
from gateway.metrics.prometheus import record_request_metrics

logger = logging.getLogger("claude-gateway.providers.anthropic")

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = settings.MODEL_PRICING.get(model, settings.MODEL_PRICING["default"])
    input_cost = (input_tokens / 1_000_000.0) * pricing["input"]
    output_cost = (output_tokens / 1_000_000.0) * pricing["output"]
    return input_cost + output_cost

def extract_prompt_text(req_body: dict) -> str:
    messages = req_body.get("messages", [])
    if not messages:
        return ""
        
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                text_blocks = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_blocks.append(block.get("text", ""))
                return " ".join(text_blocks)
    return ""

async def proxy_messages(req_body: dict, request: Request):
    model = req_body.get("model", "claude-3-5-sonnet")
    stream = req_body.get("stream", False)
    
    # 1. Resolve Git and Workspace Context
    cwd = get_client_cwd(request)
    repo_info = get_git_info(cwd)
    repo_name = repo_info["repo"]
    repo_root = repo_info["root"]
    sqlite.register_repo(repo_name, repo_root)
    
    # 2. Extract and Normalize Prompt
    prompt = extract_prompt_text(req_body)
    normalized_prompt = normalize_prompt(prompt)
    
    # Extract referenced files and calculate hashes
    files = extract_filenames(prompt, repo_root)
    file_hashes = get_file_hashes(repo_root, files)
    
    logger.info(f"Incoming request: repo={repo_name}, model={model}, files={files}")
    
    # 3. Check Exact Cache
    if normalized_prompt:
        exact_hit = get_exact_cache(repo_name, repo_info["branch"], model, normalized_prompt, repo_root)
        if exact_hit:
            # Exact cache hit!
            tokens_in = exact_hit["tokens_input"]
            tokens_out = exact_hit["tokens_output"]
            saved_cost = calculate_cost(model, tokens_in, tokens_out)
            
            # Save Metric
            sqlite.save_metric(repo_name, model, "hit", "exact", tokens_in, tokens_out, saved_cost)
            record_request_metrics(repo_name, model, "hit", "exact", tokens_in, tokens_out, saved_cost)
            
            if stream:
                return StreamingResponse(
                    cached_stream_generator(exact_hit["response"], model, tokens_in, tokens_out),
                    media_type="text/event-stream"
                )
            else:
                return Response(
                    content=json.dumps(create_response_json(exact_hit["response"], model, tokens_in, tokens_out)),
                    media_type="application/json"
                )

        # 4. Check Semantic Cache
        semantic_hit = await get_semantic_cache(repo_name, repo_info["branch"], normalized_prompt, repo_root)
        if semantic_hit:
            # Semantic cache hit!
            tokens_in = semantic_hit["tokens_input"]
            tokens_out = semantic_hit["tokens_output"]
            saved_cost = calculate_cost(model, tokens_in, tokens_out)
            
            # Save Metric
            sqlite.save_metric(repo_name, model, "hit", "semantic", tokens_in, tokens_out, saved_cost)
            record_request_metrics(repo_name, model, "hit", "semantic", tokens_in, tokens_out, saved_cost)
            
            if stream:
                return StreamingResponse(
                    cached_stream_generator(semantic_hit["response"], model, tokens_in, tokens_out),
                    media_type="text/event-stream"
                )
            else:
                return Response(
                    content=json.dumps(create_response_json(semantic_hit["response"], model, tokens_in, tokens_out)),
                    media_type="application/json"
                )

    # 5. Cache Miss: Forward to Anthropic API
    # Resolve API Key
    api_key = request.headers.get("x-api-key") or settings.ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Anthropic API key missing. Pass X-API-Key header or set ANTHROPIC_API_KEY env variable."
        )
        
    # Copy relevant headers
    headers = {
        "x-api-key": api_key,
        "content-type": "application/json",
    }
    for header in ["anthropic-version", "anthropic-beta"]:
        if header in request.headers:
            headers[header] = request.headers[header]
            
    logger.info("Cache miss. Forwarding request to Anthropic API...")
    
    async with httpx.AsyncClient() as client:
        # Prepare cleanup or forwarding
        if stream:
            # Handle streaming cache miss
            # Open connection
            req = client.build_request("POST", "https://api.anthropic.com/v1/messages", json=req_body, headers=headers)
            resp = await client.send(req, stream=True, timeout=60.0)
            
            if resp.status_code != 200:
                # Direct error response
                error_body = await resp.aread()
                return Response(content=error_body, status_code=resp.status_code, media_type="application/json")
                
            return StreamingResponse(
                stream_miss_generator(resp, repo_info, model, prompt, normalized_prompt, file_hashes),
                media_type="text/event-stream"
            )
        else:
            # Handle non-streaming cache miss
            try:
                resp = await client.post("https://api.anthropic.com/v1/messages", json=req_body, headers=headers, timeout=60.0)
                if resp.status_code != 200:
                    return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
                    
                resp_json = resp.json()
                response_text = ""
                for content_block in resp_json.get("content", []):
                    if content_block.get("type") == "text":
                        response_text += content_block.get("text", "")
                        
                usage = resp_json.get("usage", {})
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)
                cost = calculate_cost(model, tokens_in, tokens_out)
                
                # Save Metric
                sqlite.save_metric(repo_name, model, "miss", "none", tokens_in, tokens_out, cost)
                record_request_metrics(repo_name, model, "miss", "none", tokens_in, tokens_out, cost)
                
                # Cache results
                if response_text and normalized_prompt:
                    set_exact_cache(repo_name, repo_info["branch"], repo_info["commit"], model, normalized_prompt, response_text, tokens_in, tokens_out, file_hashes)
                    await set_semantic_cache(repo_name, repo_info["branch"], repo_info["commit"], prompt, normalized_prompt, response_text, tokens_in, tokens_out, file_hashes)
                    
                return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
            except Exception as e:
                logger.error(f"Error calling Anthropic API: {e}")
                raise HTTPException(status_code=500, detail=f"Internal proxy error calling Anthropic: {str(e)}")

# Generators for streaming

async def cached_stream_generator(response_text: str, model: str, tokens_in: int, tokens_out: int):
    # 1. message_start
    message_start = {
        "type": "message_start",
        "message": {
            "id": "msg_cached",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": tokens_in,
                "output_tokens": 0
            }
        }
    }
    yield f"data: {json.dumps(message_start)}\n\n"
    await asyncio.sleep(0.001)
    
    # 2. content_block_start
    content_block_start = {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""}
    }
    yield f"data: {json.dumps(content_block_start)}\n\n"
    await asyncio.sleep(0.001)
    
    # 3. content_block_deltas (simulate streaming in chunks)
    chunk_size = 40
    for i in range(0, len(response_text), chunk_size):
        chunk = response_text[i:i+chunk_size]
        delta = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": chunk}
        }
        yield f"data: {json.dumps(delta)}\n\n"
        await asyncio.sleep(0.001)
        
    # 4. content_block_stop
    content_block_stop = {
        "type": "content_block_stop",
        "index": 0
    }
    yield f"data: {json.dumps(content_block_stop)}\n\n"
    await asyncio.sleep(0.001)
    
    # 5. message_delta
    message_delta = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": tokens_out}
    }
    yield f"data: {json.dumps(message_delta)}\n\n"
    await asyncio.sleep(0.001)
    
    # 6. message_stop
    yield "data: {\"type\": \"message_stop\"}\n\n"

async def stream_miss_generator(resp: httpx.Response, repo_info: dict, model: str, prompt: str, normalized_prompt: str, file_hashes: dict):
    buffer = ""
    tokens_in = 0
    tokens_out = 0
    
    try:
        async for line in resp.aiter_lines():
            # Pass the SSE lines straight to the client
            yield f"{line}\n"
            
            # Parse line
            if line.startswith("data:"):
                try:
                    data_str = line[len("data:"):].strip()
                    if not data_str:
                        continue
                    event = json.loads(data_str)
                    event_type = event.get("type")
                    
                    if event_type == "message_start":
                        msg = event.get("message", {})
                        usage = msg.get("usage", {})
                        tokens_in = usage.get("input_tokens", 0)
                    elif event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            buffer += delta.get("text", "")
                    elif event_type == "message_delta":
                        usage = event.get("usage", {})
                        tokens_out = usage.get("output_tokens", 0)
                except Exception:
                    pass
    finally:
        try:
            await resp.aclose()
        except TypeError:
            resp.aclose()
        
    # Stream successfully ended, cache it!
    if buffer and normalized_prompt:
        if tokens_out == 0:
            tokens_out = len(buffer) // 4  # fallback estimation
            
        cost = calculate_cost(model, tokens_in, tokens_out)
        repo_name = repo_info["repo"]
        
        # Save metrics
        sqlite.save_metric(repo_name, model, "miss", "none", tokens_in, tokens_out, cost)
        record_request_metrics(repo_name, model, "miss", "none", tokens_in, tokens_out, cost)
        
        # Cache entries
        set_exact_cache(repo_name, repo_info["branch"], repo_info["commit"], model, normalized_prompt, buffer, tokens_in, tokens_out, file_hashes)
        await set_semantic_cache(repo_name, repo_info["branch"], repo_info["commit"], prompt, normalized_prompt, buffer, tokens_in, tokens_out, file_hashes)

def create_response_json(text: str, model: str, tokens_in: int, tokens_out: int) -> dict:
    return {
        "id": "msg_cached",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": text}
        ],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out
        }
    }
