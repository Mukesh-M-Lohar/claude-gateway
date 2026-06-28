# ruff: noqa: E402
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Set env vars for testing before importing gateway modules
os.environ["EXACT_CACHE_BACKEND"] = "sqlite"
os.environ["SEMANTIC_CACHE_BACKEND"] = "sqlite"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = "mock-key"

from fastapi.testclient import TestClient

from gateway.api.server import app
from gateway.cache.invalidation import calculate_sha256, extract_filenames, normalize_prompt
from gateway.config import settings
from gateway.storage import sqlite


class TestClaudeGateway(unittest.TestCase):
    def setUp(self):
        # Use a temporary SQLite database for testing
        self.db_fd, self.db_path = tempfile.mkstemp()
        settings.SQLITE_DB_PATH = self.db_path
        sqlite.init_db()

        self.client = TestClient(app)

    def tearDown(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_prompt_normalization(self):
        self.assertEqual(normalize_prompt("Please explain strategy.py"), "explain strategy.py")
        self.assertEqual(normalize_prompt("Could you please review risk.py  "), "review risk.py")
        self.assertEqual(normalize_prompt("hey claude, what is in main.go?"), "what is in main.go?")
        self.assertEqual(normalize_prompt("  Hello, claude! Tell me about risk.py"), "tell me about risk.py")

    def test_file_extraction_and_hashing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a mock file
            test_file = Path(tmpdir) / "strategy.py"
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("def run_strategy(): pass\n")

            # Test filename extraction
            prompt = "Please explain strategy.py and risk.py"
            files = extract_filenames(prompt, tmpdir)
            self.assertEqual(files, ["strategy.py"])  # risk.py doesn't exist, so excluded

            # Test hash calculation
            expected_hash = calculate_sha256(str(test_file))
            self.assertTrue(expected_hash)

            # Test on-read validation
            file_hashes = {"strategy.py": expected_hash}
            self.assertTrue(sqlite.get_db_connection())

            # Check valid entry
            from gateway.cache.invalidation import is_cache_entry_valid

            self.assertTrue(is_cache_entry_valid(tmpdir, file_hashes))

            # Modify file and verify it becomes invalid
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("def run_strategy(): print('changed')\n")
            self.assertFalse(is_cache_entry_valid(tmpdir, file_hashes))

    @patch("httpx.AsyncClient.send", new_callable=AsyncMock)
    def test_cache_hit_and_miss_non_streaming(self, mock_send):
        # Mock response from Anthropic Messages API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_json_data = {
            "id": "msg_anthropic_123",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "This is a mocked response from Claude."}],
            "usage": {"input_tokens": 10, "output_tokens": 15},
        }
        mock_response.json.return_value = mock_json_data
        mock_response.content = json.dumps(mock_json_data).encode("utf-8")
        mock_send.return_value = mock_response

        # Make a post request (should be a cache miss)
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Explain my code structure."}],
            "stream": False,
        }

        headers = {
            "x-api-key": "test-key",
            "x-working-dir": os.getcwd(),  # Bypass psutil lookup for predictability
        }

        # 1. First Call: Misses cache and calls Mock API
        response = self.client.post("/v1/messages", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["content"][0]["text"], "This is a mocked response from Claude.")
        self.assertEqual(mock_send.call_count, 1)

        # 2. Second Call: Hits cache (Exact Cache)
        # Reset mock to ensure we don't call it again
        mock_send.reset_mock()
        response_cache = self.client.post("/v1/messages", json=payload, headers=headers)
        self.assertEqual(response_cache.status_code, 200)
        data_cache = response_cache.json()
        self.assertEqual(data_cache["content"][0]["text"], "This is a mocked response from Claude.")
        self.assertEqual(mock_send.call_count, 0)  # No API calls made!

        # Check stats
        stats_resp = self.client.get("/api/stats")
        self.assertEqual(stats_resp.status_code, 200)
        stats = stats_resp.json()
        self.assertEqual(stats["summary"]["hits"], 1)
        self.assertEqual(stats["summary"]["misses"], 1)

    @patch("httpx.AsyncClient.send", new_callable=AsyncMock)
    def test_cache_hit_and_miss_streaming(self, mock_send):
        # Mock streaming response
        # Anthropic streams yield lines of SSE events
        sse_events = [
            'data: {"type": "message_start", "message": {"id": "msg_str", "usage": {"input_tokens": 8}}}',
            'data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}',
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello "}}',
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "world!"}}',
            'data: {"type": "content_block_stop", "index": 0}',
            'data: {"type": "message_delta", "usage": {"output_tokens": 12}}',
            'data: {"type": "message_stop"}',
        ]

        async def mock_aiter_lines():
            for event in sse_events:
                yield event
                await asyncio.sleep(0.001)

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Mocking the streaming methods of httpx
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.aclose = AsyncMock()
        mock_send.return_value = mock_response

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Say hello world please."}],
            "stream": True,
        }

        headers = {"x-api-key": "test-key", "x-working-dir": os.getcwd()}

        # 1. First stream call (miss)
        response = self.client.post("/v1/messages", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        # Parse stream output
        stream_content = response.text
        self.assertIn("Hello ", stream_content)
        self.assertIn("world!", stream_content)
        self.assertEqual(mock_send.call_count, 1)

        # 2. Second stream call (hit)
        mock_send.reset_mock()
        response_hit = self.client.post("/v1/messages", json=payload, headers=headers)
        self.assertEqual(response_hit.status_code, 200)

        stream_hit_content = response_hit.text
        self.assertIn("Hello world!", stream_hit_content)
        self.assertEqual(mock_send.call_count, 0)  # Exact Cache Hit!


if __name__ == "__main__":
    unittest.main()
