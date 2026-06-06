"""
Planning Module — Loads plan.json, validates state, enforces workflow.

This module is the bridge between the JSON orchestration document and the agent's
actions. It:
1. Loads plan.json at session start
2. Validates dependencies and risks before work begins
3. Provides the agent with the next valid task to work on
4. Applies approved state changes atomically
5. Saves updated plan.json at session end

Usage:
    from planning import PlanningSession
    ps = PlanningSession()
    ps.validate()           # Returns (ok, issues) tuple
    next_task = ps.next_task()  # Returns next TODO task or None
    ps.complete_task("T-001")   # Mark task as DONE
    ps.save()                    # Atomic write to disk
"""

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / "docs"
PLAN_FILE = DOCS_DIR / "plan.json"
PLAN_BACKUP = DOCS_DIR / "plan.json.bak"


class PlanningSession:
    """Manages the project planning state for an agent session."""

    def __init__(self, plan_path: Optional[Path] = None):
        self.plan_path = plan_path or PLAN_FILE
        self.plan: dict[str, Any] | None = None
        self._loaded_at = time.time()

    def load(self) -> bool:
        """Load plan.json from disk. Returns True if successful."""
        if not self.plan_path.exists():
            logger.error(f"Plan file not found: {self.plan_path}")
            return False

        try:
            with open(self.plan_path, "r", encoding="utf-8") as f:
                loaded_plan = json.load(f)
            if not isinstance(loaded_plan, dict):
                raise ValueError("plan.json root must be an object")
            self.plan = loaded_plan
            logger.info(
                f"Plan loaded: {self.plan.get('project', 'Unknown')} "
                f"v{self.plan.get('version', '?')}"
            )
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load plan: {e}")
            return False

    def validate(self) -> tuple[bool, list[str]]:
        """Validate current state before allowing work.

        Returns:
            (is_valid, issues) — list of blocking issues
        """
        if self.plan is None:
            return False, ["Plan not loaded — call load() first"]

        issues = []
        tasks = {t["id"]: t for t in self.plan.get("tasks", [])}

        # Check 1: Active rebuild
        state = self.plan.get("state", {})
        if state.get("active_rebuild"):
            issues.append(
                f"Active rebuild in progress: {state.get('rebuild_type', 'unknown')} "
                f"({state.get('rebuild_progress_pct', '?')}%). "
                f"Do NOT make structural changes until rebuild completes."
            )

        # Check 2: Dependencies for IN_PROGRESS tasks
        for task in self.plan.get("tasks", []):
            if task.get("status") == "IN_PROGRESS":
                for dep_id in task.get("dependencies", []):
                    dep = tasks.get(dep_id)
                    if dep and dep.get("status") != "DONE":
                        issues.append(
                            f"Task {task['id']} is IN_PROGRESS but dependency "
                            f"{dep_id} is {dep.get('status', 'UNKNOWN')}"
                        )

        # Check 3: Active critical risks
        for risk in self.plan.get("risks", []):
            if risk.get("active") and risk.get("severity") == "CRITICAL":
                issues.append(f"Active CRITICAL risk: {risk['id']} — {risk['description']}")

        return len(issues) == 0, issues

    def next_task(self, priority_order: Optional[list[str]] = None) -> Optional[dict]:
        """Get the next valid task to work on.

        Respects dependencies — won't return a task whose dependencies aren't DONE.
        Prioritizes by priority_order list (default: CRITICAL, HIGH, MEDIUM, LOW).

        Returns:
            Task dict or None if no valid tasks.
        """
        if self.plan is None:
            return None

        priority_order = priority_order or ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        tasks = self.plan.get("tasks", [])
        task_map = {t["id"]: t for t in tasks}

        # Get all TODO tasks
        todo_tasks = [t for t in tasks if t.get("status") == "TODO"]

        # Filter to tasks whose dependencies are all DONE
        ready = []
        for t in todo_tasks:
            deps = t.get("dependencies", [])
            if all(task_map.get(d, {}).get("status") == "DONE" for d in deps):
                ready.append(t)

        if not ready:
            return None

        # Sort by priority
        ready.sort(key=lambda x: priority_order.index(x.get("priority", "LOW")) if x.get("priority") in priority_order else 99)

        return ready[0]

    def complete_task(self, task_id: str, notes: str = "") -> bool:
        """Mark a task as DONE. Returns True if successful."""
        if self.plan is None:
            return False

        for task in self.plan.get("tasks", []):
            if task["id"] == task_id:
                task["status"] = "DONE"
                task["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S-04:00")
                if notes:
                    task["notes"] = notes
                logger.info(f"Task completed: {task_id}")
                return True

        logger.warning(f"Task not found: {task_id}")
        return False

    def start_task(self, task_id: str) -> bool:
        """Mark a task as IN_PROGRESS. Returns True if successful."""
        if self.plan is None:
            return False

        for task in self.plan.get("tasks", []):
            if task["id"] == task_id:
                task["status"] = "IN_PROGRESS"
                logger.info(f"Task started: {task_id}")
                return True

        logger.warning(f"Task not found: {task_id}")
        return False

    def add_reminder(
        self, text: str, trigger: str = "manual", steps: list[str] | None = None
    ) -> str:
        """Add a reminder. Returns the reminder ID."""
        if self.plan is None:
            raise RuntimeError("Plan must be loaded before adding reminders")
        reminders_obj = self.plan.setdefault("reminders", [])
        if not isinstance(reminders_obj, list):
            reminders_obj = []
            self.plan["reminders"] = reminders_obj
        reminders: list[dict[str, Any]] = reminders_obj
        rid = f"R-{len(reminders) + 1:03d}"
        reminder: dict[str, Any] = {"id": rid, "text": text, "trigger": trigger}
        if steps:
            reminder["steps"] = steps
        reminders.append(reminder)
        return rid

    def remove_reminder(self, reminder_id: str) -> bool:
        """Remove a reminder by ID."""
        if self.plan is None:
            return False
        reminders_obj = self.plan.get("reminders", [])
        reminders: list[dict[str, Any]] = (
            reminders_obj if isinstance(reminders_obj, list) else []
        )
        before = len(reminders)
        self.plan["reminders"] = [r for r in reminders if r["id"] != reminder_id]
        return len(self.plan["reminders"]) < before

    def save(self) -> bool:
        """Atomically save plan.json with backup. Returns True if successful."""
        if self.plan is None:
            return False

        self.plan["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S-04:00")

        try:
            # Backup current file
            if self.plan_path.exists():
                shutil.copy2(str(self.plan_path), str(PLAN_BACKUP))

            # Atomic write: write to temp, then rename
            tmp_path = self.plan_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.plan, f, indent=2, ensure_ascii=False)

            tmp_path.replace(self.plan_path)
            logger.info(f"Plan saved: {self.plan_path}")
            return True

        except OSError as e:
            logger.error(f"Failed to save plan: {e}")
            return False

    def summary(self) -> str:
        """Generate a one-line status summary."""
        if self.plan is None:
            return "Plan not loaded"

        tasks = self.plan.get("tasks", [])
        done = sum(1 for t in tasks if t.get("status") == "DONE")
        progress = sum(1 for t in tasks if t.get("status") == "IN_PROGRESS")
        todo = sum(1 for t in tasks if t.get("status") == "TODO")
        phase = self.plan.get("state", {}).get("phase", "Unknown")

        return f"Phase: {phase} | {done} done, {progress} in progress, {todo} remaining ({len(tasks)} total)"
