"""
Plan Report Generator — Converts plan.json to human-readable Markdown.

Reads the master JSON orchestration file and generates a formatted report
for human review. This is a one-way derivation — the markdown is read-only.

Usage:
    python generate_report.py                     # Default location
    python generate_report.py /path/to/plan.json  # Custom path
"""

import json
import sys
from datetime import datetime
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"


def generate_report(plan_path: Path, output_path: Path):
    """Generate a human-readable markdown report from plan.json."""
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    lines = []

    # ── Header ──
    lines.append(f"# FileMind Project Plan Report")
    lines.append(f"")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Project Phase:** {plan['state']['phase']}")
    lines.append(f"**Last Updated:** {plan.get('updated_at', 'Unknown')}")
    lines.append(f"")

    # ── Active Reminders ──
    reminders = plan.get("reminders", [])
    if reminders:
        lines.append("## ⏰ Active Reminders")
        lines.append("")
        for r in reminders:
            trigger = r.get("trigger", "manual")
            lines.append(f"- **{r['id']}**: {r['text']} (trigger: `{trigger}`)")
        lines.append("")

    # ── Risks (CRITICAL first) ──
    risks = plan.get("risks", [])
    active_risks = [r for r in risks if r.get("active", True)]
    if active_risks:
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        active_risks.sort(key=lambda r: severity_order.get(r.get("severity", "LOW"), 99))

        lines.append("## ⚠️ Active Risks")
        lines.append("")
        for r in active_risks:
            sev = r.get("severity", "UNKNOWN")
            emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
            lines.append(f"- {emoji} **[{sev}] {r['id']}**: {r['description']}")
            lines.append(f"  - *Mitigation:* {r.get('mitigation', 'None')}")
        lines.append("")

    # ── Tasks by Status ──
    tasks = plan.get("tasks", [])

    in_progress = [t for t in tasks if t.get("status") == "IN_PROGRESS"]
    todo = [t for t in tasks if t.get("status") == "TODO"]
    done = [t for t in tasks if t.get("status") == "DONE"]

    # Sort by priority
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    if in_progress:
        lines.append("## 🔄 In Progress")
        lines.append("")
        for t in sorted(in_progress, key=lambda x: priority_order.get(x.get("priority", "LOW"), 99)):
            lines.append(f"- [{t.get('priority', '').upper()}] **{t['id']}**: {t['description']}")
            if t.get("notes"):
                lines.append(f"  - {t['notes']}")
        lines.append("")

    if todo:
        lines.append("## 📋 TODO (by priority)")
        lines.append("")
        for t in sorted(todo, key=lambda x: priority_order.get(x.get("priority", "LOW"), 99)):
            deps = t.get("dependencies", [])
            dep_str = f" (blocked by: {', '.join(deps)})" if deps else ""
            lines.append(f"- [{t.get('priority', '').upper()}] **{t['id']}**: {t['description']}{dep_str}")
            if t.get("notes"):
                lines.append(f"  - {t['notes']}")
        lines.append("")

    if done:
        lines.append("## ✅ Completed")
        lines.append("")
        for t in sorted(done, key=lambda x: x.get("completed_at", "")):
            lines.append(f"- [{t.get('priority', '').upper()}] **{t['id']}**: {t['description']}")
        lines.append("")

    # ── Key Decisions ──
    decisions = plan.get("decisions", [])
    if decisions:
        lines.append("## 📌 Key Decisions")
        lines.append("")
        for d in decisions:
            lines.append(f"- **{d['id']}**: {d['text']}")
            lines.append(f"  - *Rationale:* {d.get('rationale', 'N/A')}")
        lines.append("")

    # ── Summary ──
    total = len(tasks)
    done_count = len(done)
    progress_count = len(in_progress)
    todo_count = len(todo)

    lines.append("---")
    lines.append(f"**Summary:** {done_count}/{total} done, {progress_count} in progress, {todo_count} remaining")
    lines.append(f"*This report is auto-generated from `plan.json`. Do not edit directly.*")

    # Write report
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


if __name__ == "__main__":
    if len(sys.argv) > 1:
        plan_path = Path(sys.argv[1])
    else:
        plan_path = DOCS_DIR / "plan.json"

    output_path = plan_path.parent / "plan_report.md"
    result = generate_report(plan_path, output_path)
    print(f"Report generated: {result}")
