import hashlib
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("claude-gateway.cache.invalidation")

# Filler words and phrases to strip from the beginning of prompts
FILLER_PATTERNS = [
    r"^please\s+",
    r"^could\s+you\s+please\s+",
    r"^can\s+you\s+please\s+",
    r"^would\s+you\s+please\s+",
    r"^could\s+you\s+",
    r"^can\s+you\s+",
    r"^would\s+you\s+",
    r"^hey\s+claude[!,\.]*\s*",
    r"^claude[!,\.]*\s*",
    r"^hi[!,\.]*\s+claude[!,\.]*\s*",
    r"^hello[!,\.]*\s+claude[!,\.]*\s*",
    r"^hi[!,\.]*\s+",
    r"^hello[!,\.]*\s+",
    r"^hey[!,\.]*\s+",
]


def normalize_prompt(prompt: str) -> str:
    if not prompt:
        return ""

    # Trim whitespace
    text = prompt.strip()

    # Lowercase
    text = text.lower()

    # Remove leading filler words/greetings
    for pattern in FILLER_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Trim again after substitution
    text = text.strip()

    # Replace multiple spaces/newlines with a single space
    text = re.sub(r"\s+", " ", text)

    return text


def extract_filenames(prompt: str, repo_root: str) -> list:
    if not prompt or not repo_root or not os.path.exists(repo_root):
        return []

    # Regex to find potential file paths (e.g. strategy.py, src/utils.js, config/settings.json)
    # Allows alphanumeric characters, dots, slashes, dashes, underscores, and file extensions
    pattern = r"\b([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)\b"
    candidates = re.findall(pattern, prompt)

    found_files = []

    for cand in candidates:
        # Clean candidates of wrapping characters that might be part of markdown/punctuation
        cand_clean = cand.strip(".,;:?!'\"`*()[]{}")
        if not cand_clean:
            continue

        # Check if file exists under the repository root
        full_path = Path(repo_root) / cand_clean
        if full_path.is_file():
            # Store the relative path to repo root to remain namespace-independent
            try:
                rel_path = os.path.relpath(full_path, repo_root).replace("\\", "/")
                if rel_path not in found_files:
                    found_files.append(rel_path)
            except Exception:
                pass

    return found_files


def calculate_sha256(filepath: str) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.debug(f"Failed to hash file {filepath}: {e}")
        return ""


def get_file_hashes(repo_root: str, files: list) -> dict:
    hashes = {}
    if not repo_root or not os.path.exists(repo_root):
        return hashes

    for file in files:
        full_path = Path(repo_root) / file
        if full_path.is_file():
            file_hash = calculate_sha256(str(full_path))
            if file_hash:
                hashes[file] = file_hash
    return hashes


def is_cache_entry_valid(repo_root: str, file_hashes: dict) -> bool:
    if not file_hashes:
        return True  # No files to validate

    if not repo_root or not os.path.exists(repo_root):
        return False  # Repo is gone

    for file, expected_hash in file_hashes.items():
        full_path = Path(repo_root) / file
        if not full_path.is_file():
            logger.info(f"Cache invalidated: file {file} no longer exists.")
            return False

        current_hash = calculate_sha256(str(full_path))
        if current_hash != expected_hash:
            logger.info(f"Cache invalidated: file {file} has changed.")
            return False

    return True
