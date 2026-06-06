"""
MemMachine Sync — Optional integration with MemMachine memory system.

Pushes file summaries to MemMachine for conversational context.
Queries MemMachine for file-related context when searching.
This is an OPTIONAL layer — FileMind works fully without it.
"""

import json
import logging
from typing import Optional

import requests

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)


class MemMachineSync:
    """Optional MemMachine integration for file summaries."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.memmachine_api_url).rstrip("/")
        self.org_id = config.memmachine_org_id
        self.project_id = config.memmachine_project_id
        self.enabled = config.memmachine_enabled

    def health_check(self) -> dict:
        """Check MemMachine status."""
        try:
            r = requests.get(f"{self.base_url}/api/v2/health", timeout=5)
            if r.status_code == 200:
                return {"status": "ok", "response": r.json()}
            return {"status": "error", "code": r.status_code}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    def _ensure_project(self) -> bool:
        """Ensure the FileMind project exists in MemMachine."""
        try:
            r = requests.post(
                f"{self.base_url}/api/v2/projects/get",
                json={"org_id": self.org_id, "project_id": self.project_id},
                timeout=10,
            )
            if r.status_code == 200:
                return True

            # Create project
            r = requests.post(
                f"{self.base_url}/api/v2/projects",
                json={
                    "org_id": self.org_id,
                    "project_id": self.project_id,
                    "description": "FileMind file index summaries",
                },
                timeout=10,
            )
            return r.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"MemMachine project check failed: {e}")
            return False

    def push_summary(self, file_path: str, content_summary: str,
                     category: str, confidence: float) -> bool:
        """
        Push a file summary to MemMachine as a memory.

        Args:
            file_path: Relative file path
            content_summary: Extracted content summary
            category: File category
            confidence: Classification confidence

        Returns:
            True if pushed successfully
        """
        if not self.enabled:
            return False

        if not self._ensure_project():
            return False

        message = {
            "role": "user",
            "content": (
                f"FILE SUMMARY: {file_path}\n"
                f"CATEGORY: {category} (confidence: {confidence:.2f})\n"
                f"CONTENT:\n{content_summary[:2000]}"
            ),
        }

        try:
            r = requests.post(
                f"{self.base_url}/api/v2/memories",
                json={
                    "session": {
                        "org_id": self.org_id,
                        "project_id": self.project_id,
                    },
                    "messages": [message],
                },
                timeout=30,
            )
            return r.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"MemMachine push failed for {file_path}: {e}")
            return False

    def push_batch(self, files: list[dict]) -> int:
        """
        Push multiple file summaries to MemMachine.

        Args:
            files: List of dicts with path, content_summary, category, confidence

        Returns:
            Number successfully pushed
        """
        if not self.enabled:
            return 0

        if not self._ensure_project():
            return 0

        success = 0
        batch_size = 5  # Conservative to avoid timeout

        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            messages = []
            for f in batch:
                messages.append({
                    "role": "user",
                    "content": (
                        f"FILE: {f['path']}\n"
                        f"CATEGORY: {f.get('category', 'unknown')}\n"
                        f"CONTENT:\n{f.get('content_summary', '')[:2000]}"
                    ),
                })

            try:
                r = requests.post(
                    f"{self.base_url}/api/v2/memories",
                    json={
                        "session": {
                            "org_id": self.org_id,
                            "project_id": self.project_id,
                        },
                        "messages": messages,
                    },
                    timeout=120,
                )
                if r.status_code in (200, 201):
                    success += len(messages)
            except Exception as e:
                logger.warning(f"Batch push failed: {e}")

        logger.info(f"Pushed {success}/{len(files)} summaries to MemMachine")
        return success

    def query(self, query: str, limit: int = 5) -> list[dict]:
        """
        Query MemMachine for file-related context.

        Args:
            query: Natural language query
            limit: Max results

        Returns:
            List of relevant memories
        """
        if not self.enabled:
            return []

        try:
            r = requests.get(
                f"{self.base_url}/api/v2/memories/search",
                params={"q": query, "limit": limit},
                timeout=30,
            )
            if r.status_code == 200:
                return r.json().get("memories", [])  # Adjust based on API response format
            return []
        except Exception as e:
            logger.warning(f"MemMachine query failed: {e}")
            return []


def sync_to_memmachine(file_records: list[dict]) -> int:
    """Convenience function: push summaries to MemMachine."""
    syncer = MemMachineSync()
    return syncer.push_batch(file_records)


def query_memmachine(query: str) -> list[dict]:
    """Convenience function: query MemMachine for context."""
    syncer = MemMachineSync()
    return syncer.query(query)
