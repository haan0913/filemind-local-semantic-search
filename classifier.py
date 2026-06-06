"""
File Classifier — Ollama-backed file classification with index-based batching.

FileMind chooses which model name to call, but Ollama decides whether that
model runs on CPU, GPU, or a split CPU/GPU placement based on available
memory.
"""

import json
import logging
import re
import time

import requests

try:
    from .config import config
except ImportError:
    from config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = "You are a file classifier. You ONLY output valid JSON arrays. No explanation, no markdown."

BATCH_PROMPT = """Classify each file. Return ONLY a JSON array in the SAME ORDER as the input.

{file_lines}

Categories: {categories}

Required JSON format (one object per file, ordered by [i]):
[{{"i": 1, "category": "one_of_the_categories", "confidence": 0.9}}, ...]"""


class RuleBasedClassifier:
    """Mandatory first-pass rule based fallback."""

    EXT_CATEGORY_MAP = {
        ".py": "code",
        ".js": "code",
        ".ts": "code",
        ".rs": "code",
        ".go": "code",
        ".cpp": "code",
        ".sh": "code",
        ".ps1": "code",
        ".sql": "code",
        ".md": "documentation",
        ".rst": "documentation",
        ".docx": "documentation",
        ".pdf": "documentation",
        ".txt": "documentation",
        ".json": "config",
        ".yaml": "config",
        ".toml": "config",
        ".ini": "config",
        ".cfg": "config",
        ".env": "config",
        ".csv": "data",
        ".xlsx": "data",
        ".jpg": "media",
        ".png": "media",
        ".mp4": "media",
        ".gif": "media",
        ".zip": "archive",
        ".tar": "archive",
        ".gz": "archive",
    }

    DIR_HEURISTICS = {
        ("filemind", "owl-agent", "memmachine", "hub/agents"): "ai_project",
        ("finance", "invoice", "budget", "tax"): "finance",
        ("personal", "diary", "journal"): "personal",
    }

    @classmethod
    def classify(cls, path: str, ext: str) -> tuple[str, float]:
        path_lower = path.replace("\\", "/").lower()
        if ext in cls.EXT_CATEGORY_MAP:
            return cls.EXT_CATEGORY_MAP[ext], 0.90

        for dir_parts, category in cls.DIR_HEURISTICS.items():
            for part in dir_parts:
                if f"/{part}/" in f"/{path_lower}" or path_lower.startswith(f"{part}/"):
                    return category, 0.75

        return "unknown", 0.0


class Classifier:
    """Ollama-backed file classifier using the configured classification model."""

    def __init__(self):
        self.ollama_url = f"{config.ollama_api_url}/api/chat"
        self.categories = config.categories
        self.batch_size = config.classification_batch_size
        self.confidence_threshold = config.classification_confidence_threshold
        self.primary_model = config.classification_model
        self.fallback_model = "llama3"

    def classify(self, files: list[dict]) -> list[dict]:
        """Classify files in batches. Returns list with path, category, confidence."""
        if not files:
            return []

        final_results = []
        to_llm = []

        # Pass 1: Rule-Based
        for f in files:
            path = f.get("path", "")
            ext = f.get("ext", "")
            rule_cat, rule_conf = RuleBasedClassifier.classify(path, ext)

            if (
                rule_cat != "unknown"
                and rule_conf >= config.classification_confidence_fallback_threshold
            ):
                final_results.append(
                    {"path": path, "category": rule_cat, "confidence": rule_conf}
                )
            else:
                to_llm.append((f, rule_cat, rule_conf))

        if not to_llm:
            return final_results

        if not getattr(config, "classification_llm_enabled", True):
            logger.info(
                "LLM classification disabled; using rule-based/unknown categories for %s file(s).",
                len(to_llm),
            )
            for f, rule_cat, rule_conf in to_llm:
                path = f["path"]
                if config.rule_based_fallback and rule_cat != "unknown":
                    final_results.append(
                        {"path": path, "category": rule_cat, "confidence": rule_conf}
                    )
                else:
                    final_results.append(
                        {"path": path, "category": "unknown", "confidence": 0.0}
                    )
            return final_results

        # Pass 2: LLM Batching
        llm_files = [item[0] for item in to_llm]
        llm_results_map = {}

        for i in range(0, len(llm_files), self.batch_size):
            batch = llm_files[i : i + self.batch_size]
            try:
                batch_results = self._classify_batch(batch)
                for res in batch_results:
                    llm_results_map[res["path"]] = res
            except Exception as e:
                logger.error(f"Batch {i // self.batch_size + 1} failed: {e}")

        # Merge LLM results with fallback
        for f, rule_cat, rule_conf in to_llm:
            path = f["path"]
            llm_res = llm_results_map.get(path)

            if llm_res and llm_res["category"] != "unknown":
                final_results.append(llm_res)
            else:
                if config.rule_based_fallback and rule_cat != "unknown":
                    final_results.append(
                        {"path": path, "category": rule_cat, "confidence": rule_conf}
                    )
                    logger.warning(
                        f"Ollama failed for {path}, falling back to rule-based {rule_cat}"
                    )
                else:
                    final_results.append(
                        {"path": path, "category": "unknown", "confidence": 0.0}
                    )

        return final_results

    def _classify_batch(self, files: list[dict]) -> list[dict]:
        """Classify one batch using index-based matching."""
        # Build numbered file list for prompt
        file_lines = []
        for idx, f in enumerate(files, start=1):
            path = f.get("path", "unknown")
            ext = f.get("ext", "")
            parent = (
                path.rsplit("/", 1)[0]
                if "/" in path
                else path.rsplit("\\", 1)[0]
                if "\\" in path
                else ""
            )
            parent_name = (
                parent.rsplit("/", 1)[-1]
                if "/" in parent
                else parent.rsplit("\\", 1)[-1]
            )
            snippet = (f.get("content_summary", "") or "").strip()[:100]
            line = f"[{idx}] {path} | ext:{ext} | dir:{parent_name}"
            if snippet:
                line += f" | preview:{snippet[:80]}"
            file_lines.append(line)

        cats = ", ".join(self.categories)
        prompt = BATCH_PROMPT.format(
            file_lines="\n".join(file_lines),
            categories=cats,
        )

        # Try primary model
        raw = None
        try:
            raw = self._ollama_call(self.primary_model, prompt)
            return self._parse_indexed_response(raw, files)
        except Exception as e:
            logger.warning(f"Primary model {self.primary_model} failed: {e}")

        # Fallback model
        try:
            raw = self._ollama_call(self.fallback_model, prompt)
            return self._parse_indexed_response(raw, files)
        except Exception as e:
            logger.error(f"Fallback {self.fallback_model} also failed: {e}")
            if raw:
                logger.error(f"Last raw output (first 300): {raw[:300]}")

        return [
            {"path": f["path"], "category": "unknown", "confidence": 0.0} for f in files
        ]

    def _ollama_call(self, model: str, prompt: str) -> str:
        """Ollama API call with model-appropriate format.

        gemma3:4b requires JSON schema for reliable output.
        gemma4-e4b-json works with format:'json' (string).
        """
        # Build JSON schema for gemma3 and similar models
        format_spec = "json"  # Default: string format
        if "gemma3" in model.lower():
            # gemma3 needs explicit JSON schema for reliable output
            format_spec = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "i": {"type": "integer"},
                                "category": {"type": "string", "enum": self.categories},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                            },
                            "required": ["i", "category", "confidence"],
                        },
                    }
                },
                "required": ["items"],
            }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": format_spec,
            "options": {"temperature": 0.1, "num_predict": 8192},
        }
        for attempt in range(3):
            try:
                response = requests.post(self.ollama_url, json=payload, timeout=60)
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "")
            except Exception as e:
                logger.warning(f"Ollama call failed (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(3)
        raise Exception("Ollama call failed after 3 attempts")

    def _parse_indexed_response(self, text: str, files: list[dict]) -> list[dict]:
        """Parse index-keyed JSON array from LLM. Match by 'i' field, not path."""
        # Strip markdown fences if any
        text = re.sub(r"```\w*\s*|\s*```", "", text).strip()

        valid_categories = set(c.lower() for c in self.categories)
        index_map: dict[int, dict] = {}  # i -> {category, confidence}

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try extracting JSON array from text
            m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    logger.warning(f"JSON parse failed: {text[:300]}")
                    return [
                        {"path": f["path"], "category": "unknown", "confidence": 0.0}
                        for f in files
                    ]
            else:
                logger.warning(f"No JSON array found: {text[:300]}")
                return [
                    {"path": f["path"], "category": "unknown", "confidence": 0.0}
                    for f in files
                ]

        # Handle gemma3 schema wrapping: {"items": [...]}
        if isinstance(data, dict):
            for key in ("items", "files", "results", "classifications"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                # Single object case
                data = [data]

        for item in data:
            if not isinstance(item, dict):
                continue
            idx = item.get("i") or item.get("index") or item.get("id")
            if idx is None:
                continue
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                continue

            raw_cat = (
                str(item.get("category") or item.get("type") or "").lower().strip()
            )
            category = raw_cat if raw_cat in valid_categories else "unknown"

            try:
                confidence = float(item.get("confidence", 0.85))
            except (TypeError, ValueError):
                confidence = 0.85

            if confidence < self.confidence_threshold:
                category = "unknown"

            index_map[idx] = {"category": category, "confidence": confidence}

        results = []
        for idx, f in enumerate(files, start=1):
            match = index_map.get(idx)
            if match:
                results.append({"path": f["path"], **match})
            else:
                results.append(
                    {"path": f["path"], "category": "unknown", "confidence": 0.0}
                )

        classified = sum(1 for r in results if r["category"] != "unknown")
        logger.info(f"Batch: {classified}/{len(files)} classified successfully")
        return results


def classify_files(files: list[dict]) -> list[dict]:
    classifier = Classifier()
    return classifier.classify(files)
