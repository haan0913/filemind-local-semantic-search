"""
Dependency Checker — Validates all optional feature dependencies at startup.

Maps every optional feature to its required Python packages and provides:
1. Dependency status report
2. Auto-disable with warning when feature is enabled but dependency missing
3. Clear install commands for missing dependencies

Usage:
    python check_deps.py                    # CLI report
    from check_deps import DependencyChecker
    dc = DependencyChecker()
    dc.validate()                            # Raises warning on missing
    dc.validate_feature("reranking")         # Returns True/False
"""

import importlib
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FeatureDependency:
    """A feature and its required packages."""
    name: str
    description: str
    config_flag: str          # e.g. "ENABLE_RERANKING"
    packages: list[str]       # e.g. ["FlagEmbedding", "sentence_transformers"]
    install_cmd: str          # e.g. "pip install FlagEmbedding"
    critical: bool = False    # If True, warn loudly; if False, silently skip


@dataclass
class DepCheckResult:
    """Result of a dependency check."""
    feature: str
    available: bool
    missing_packages: list[str] = field(default_factory=list)
    error_message: str = ""


# ── Feature Registry ────────────────────────────────────────────────────────

FEATURE_REGISTRY: list[FeatureDependency] = [
    FeatureDependency(
        name="reranking",
        description="Cross-encoder reranking of search results",
        config_flag="ENABLE_RERANKING",
        packages=["sentence_transformers"],  # CrossEncoder via sentence-transformers
        install_cmd="pip install sentence-transformers (already installed)",
        critical=False,
    ),
    FeatureDependency(
        name="smart_chunking",
        description="File-type-aware chunking (AST, header-based, structure-aware)",
        config_flag="USE_SMART_CHUNKING",
        packages=["ast", "json", "tomllib"],  # All stdlib
        install_cmd="Built into Python — no install needed",
        critical=False,
    ),
    FeatureDependency(
        name="yaml_chunking",
        description="YAML structure-aware chunking",
        config_flag="USE_SMART_CHUNKING",
        packages=["yaml"],  # PyYAML
        install_cmd="pip install pyyaml",
        critical=False,
    ),
    FeatureDependency(
        name="pdf_extraction",
        description="PDF multi-stage extraction with layout analysis",
        config_flag="USE_SMART_CHUNKING",
        packages=["pymupdf"],
        install_cmd="pip install pymupdf",
        critical=False,
    ),
    FeatureDependency(
        name="hyde_expansion",
        description="HyDE query expansion via Ollama llama3",
        config_flag="HYDE_ENABLED",
        packages=["requests"],
        install_cmd="pip install requests (already installed)",
        critical=False,
    ),
    FeatureDependency(
        name="classification",
        description="Ollama LLM file classification",
        config_flag="CLASSIFICATION_MODEL",
        packages=["requests"],
        install_cmd="Ollama must be running (no Python dependency)",
        critical=False,
    ),
]


class DependencyChecker:
    """Validates that optional features have their required dependencies."""

    def __init__(self, registry: Optional[list[FeatureDependency]] = None):
        self.registry = registry or FEATURE_REGISTRY
        self._results: dict[str, DepCheckResult] = {}

    def check_all(self) -> dict[str, DepCheckResult]:
        """Check all features. Returns results dict."""
        for feature in self.registry:
            result = self._check_feature(feature)
            self._results[feature.name] = result
        return self._results

    def check_feature(self, feature_name: str) -> bool:
        """Check if a single feature's dependencies are available.

        Returns True if all dependencies are installed, False otherwise.
        """
        feature = next((f for f in self.registry if f.name == feature_name), None)
        if feature is None:
            logger.warning(f"Unknown feature: {feature_name}")
            return False
        result = self._check_feature(feature)
        return result.available

    def _check_feature(self, feature: FeatureDependency) -> DepCheckResult:
        """Check a single feature's dependencies."""
        missing = []
        for pkg in feature.packages:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)

        return DepCheckResult(
            feature=feature.name,
            available=len(missing) == 0,
            missing_packages=missing,
        )

    def auto_disable_missing(self, config) -> list[str]:
        """Check all features and auto-disable those with missing deps.

        Sets the corresponding config flag to False and logs warnings.
        Returns list of features that were auto-disabled.
        """
        disabled = []
        for feature in self.registry:
            result = self._check_feature(feature)
            self._results[feature.name] = result
            if not result.available and result.missing_packages:
                flag = feature.config_flag
                try:
                    setattr(config, flag, False)
                except AttributeError:
                    pass
                logger.warning(
                    f"Feature '{feature.name}' DISABLED — missing "
                    f"dependencies: {', '.join(result.missing_packages)}. "
                    f"Install: {feature.install_cmd}"
                )
                disabled.append(feature.name)
        return disabled

    def report(self) -> str:
        """Generate a human-readable dependency report."""
        results = self.check_all()
        lines = ["\nFileMind Dependency Status", "=" * 50]

        for name, result in results.items():
            status = "OK" if result.available else "MISSING"
            emoji = "✅" if result.available else "❌"
            lines.append(f"\n[{emoji}] {name}: {status}")

            if result.missing_packages:
                feature = next(f for f in self.registry if f.name == name)
                lines.append(f"    Missing: {', '.join(result.missing_packages)}")
                lines.append(f"    Install: {feature.install_cmd}")

        lines.append("\n" + "=" * 50)
        return "\n".join(lines)


def validate_all(config) -> list[str]:
    """Convenience: check all features and auto-disable missing ones.

    Call this at startup in run.py, nightly.py, etc.
    Returns list of features that were auto-disabled.
    """
    checker = DependencyChecker()
    return checker.auto_disable_missing(config)


if __name__ == "__main__":
    checker = DependencyChecker()
    print(checker.report())
