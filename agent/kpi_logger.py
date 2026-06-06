r"""
FileMind Agent KPI Logger — Lightweight performance tracking.

Logs latency, throughput, and resource usage per agent task.
Output: C:\AI_STATION\filemind\logs\kpi.jsonl

Usage:
    from agent.kpi_logger import kpi
    kpi.tick_start()
    result = agent.run(task)
    kpi.tick_end(result)
"""

import os
import json
import time
import psutil
from pathlib import Path
from collections import deque
from datetime import datetime

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "kpi.jsonl"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class AgentKPI:
    """Track agent performance metrics across tasks."""

    def __init__(self, window_size: int = 100):
        self.latencies = deque(maxlen=window_size)
        self.token_counts = deque(maxlen=window_size)
        self.task_names = deque(maxlen=window_size)
        self.successes = deque(maxlen=window_size)
        self.start_time = None

    def tick_start(self, task_name: str = "unknown"):
        """Call before running a task."""
        self.start_time = time.time()
        self._task_name = task_name

    def tick_end(self, output: str = "", success: bool = True):
        """Call after task completes."""
        if self.start_time is None:
            return
        elapsed = time.time() - self.start_time
        output_len = len(output) if output else 0

        self.latencies.append(elapsed)
        self.token_counts.append(output_len)
        self.task_names.append(self._task_name)
        self.successes.append(success)
        self.start_time = None

        # Log to JSONL
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task": self._task_name,
            "latency_sec": round(elapsed, 2),
            "output_chars": output_len,
            "chars_per_sec": round(output_len / elapsed, 0) if elapsed > 0 else 0,
            "success": success,
            "ram_usage_gb": round(psutil.virtual_memory().used / 1024**3, 2),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
        }

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Don't crash the agent if logging fails

    def report(self) -> dict:
        """Get current performance summary."""
        n = len(self.latencies)
        if n == 0:
            return {"tasks_run": 0}

        successes = sum(self.successes)
        return {
            "tasks_run": n,
            "success_rate": round(successes / n * 100, 1),
            "avg_latency_sec": round(sum(self.latencies) / n, 2),
            "min_latency_sec": round(min(self.latencies), 2),
            "max_latency_sec": round(max(self.latencies), 2),
            "avg_output_chars": round(sum(self.token_counts) / n, 0),
            "avg_chars_per_sec": round(
                sum(c / l if l > 0 else 0 for c, l in zip(self.token_counts, self.latencies)) / n, 0
            ),
            "ram_usage_gb": round(psutil.virtual_memory().used / 1024**3, 2),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
        }


# Global singleton
kpi = AgentKPI()
