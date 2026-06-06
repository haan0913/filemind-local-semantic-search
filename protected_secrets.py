"""Protected local-only credential lane helpers.

The protected lane is deliberately small and deterministic:

- normal FileMind search may surface path/name metadata, but snippets are
  redacted before display, API return, or local LLM context assembly;
- credential lookup is local-only and reveal requires an explicit local flag;
- NotebookLM/source-pack candidates are rejected if the path or content looks
  secret-like.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from typing import Iterable


REDACTION_TOKEN = "[REDACTED_SECRET]"
PROTECTED_SNIPPET = (
    "[PROTECTED_SECRET: redacted; use protected local lookup for metadata]"
)

SECRET_NAME_TERMS: tuple[str, ...] = (
    "secret",
    "secrets",
    "credential",
    "credentials",
    "token",
    "tokens",
    "apikey",
    "api_key",
    "password",
    "passwd",
    "pwd",
    "private",
    "key",
    "keys",
)

SECRET_FILENAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "tokens.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

SECRET_EXTENSIONS: set[str] = {
    ".env",
    ".key",
    ".pem",
    ".p12",
    ".pfx",
    ".kdbx",
    ".age",
    ".gpg",
}

VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
)

ASSIGNMENT_PATTERN = re.compile(
    r"(?im)^([ \t]*(?:export[ \t]+)?"
    r"[A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|PWD|CREDENTIAL|AUTH)"
    r"[A-Za-z0-9_]*[ \t]*[:=][ \t]*)(.+)$"
)

HUMAN_SECRET_LABEL_PATTERN = re.compile(
    r"(?im)^([ \t]*(?:[-*]\s*)?"
    r"(?:bearer\s+token|access\s+token|refresh\s+token|client\s+secret|"
    r"api\s+key|private\s+key|password|secret)"
    r"[ \t]*[:=][ \t]*)(.+)$"
)

DEFAULT_SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    "Lib",
}


class ProtectedSecretAccessError(PermissionError):
    """Raised when a caller asks to reveal secrets without explicit local consent."""


class NotebookLMSecretSourceError(ValueError):
    """Raised when a source-pack candidate is unsafe for NotebookLM upload."""


@dataclass(frozen=True)
class SecretLookupResult:
    """Metadata-only protected-lane credential lookup result."""

    path: str
    name: str
    service_hint: str
    redacted_snippet: str = ""
    revealed_text: str = ""

    @property
    def revealed(self) -> bool:
        return bool(self.revealed_text)


def _normalize_path_text(path: str | Path) -> str:
    return str(path).replace("\\", "/").strip()


def _tokens_for_path(path: str | Path) -> set[str]:
    normalized = _normalize_path_text(path).lower()
    return {part for part in re.split(r"[^a-z0-9_]+", normalized) if part}


def is_secret_like_path(path: str | Path) -> bool:
    """Return True when a path should be routed to the protected secrets lane."""

    normalized = _normalize_path_text(path).lower()
    name = Path(normalized).name
    suffix = Path(name).suffix
    if name in SECRET_FILENAMES:
        return True
    if name.startswith(".env."):
        return True
    if suffix in SECRET_EXTENSIONS:
        return True
    return bool(_tokens_for_path(normalized) & set(SECRET_NAME_TERMS))


def redact_secret_text(text: str) -> str:
    """Redact common credential values from text while preserving useful keys."""

    if not text:
        return text

    redacted = ASSIGNMENT_PATTERN.sub(r"\1" + REDACTION_TOKEN, text)
    redacted = HUMAN_SECRET_LABEL_PATTERN.sub(r"\1" + REDACTION_TOKEN, redacted)
    for pattern in VALUE_PATTERNS:
        if pattern.pattern.startswith("://"):
            redacted = pattern.sub("://" + REDACTION_TOKEN + "@", redacted)
        else:
            redacted = pattern.sub(REDACTION_TOKEN, redacted)
    return redacted


def contains_secret_value(text: str) -> bool:
    """Return True if text contains values that would be redacted."""

    if not text:
        return False
    return redact_secret_text(text) != text


def normal_search_snippet(path: str | Path, text: str, *, max_chars: int = 200) -> str:
    """Return a snippet safe for normal search/API/LLM output."""

    if is_secret_like_path(path):
        return PROTECTED_SNIPPET
    return redact_secret_text(text)[:max_chars]


def assert_notebooklm_source_allowed(path: str | Path, text: str = "") -> None:
    """Raise if a candidate source must not be uploaded to NotebookLM."""

    if is_secret_like_path(path):
        raise NotebookLMSecretSourceError(
            f"Secret-looking path is not NotebookLM-safe: {path}"
        )
    if contains_secret_value(text):
        raise NotebookLMSecretSourceError(
            "Secret-looking content is not NotebookLM-safe."
        )


def _safe_read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding, errors="replace")
        except OSError:
            return ""
        except UnicodeError:
            continue
    return ""


def _iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in DEFAULT_SKIP_DIRS]
        current = Path(dirpath)
        for filename in filenames:
            yield current / filename


def _service_hint(path: Path) -> str:
    for part in reversed(path.parts[:-1]):
        clean = part.strip(".").lower()
        if clean and clean not in {"config", "credentials", "secrets", "tokens"}:
            return clean
    return path.stem.strip(".").lower() or path.name.lower()


def lookup_protected_secrets(
    roots: Iterable[str | Path],
    query: str = "",
    *,
    reveal: bool = False,
    explicit_local_disclosure: bool = False,
    max_results: int = 50,
) -> list[SecretLookupResult]:
    """Find secret-like files locally without disclosing values by default."""

    if reveal and not explicit_local_disclosure:
        raise ProtectedSecretAccessError(
            "Secret reveal requires explicit_local_disclosure=True in a local session."
        )

    query_lower = query.lower().strip()
    results: list[SecretLookupResult] = []
    for root_value in roots:
        for path in _iter_files(Path(root_value).expanduser()):
            if not is_secret_like_path(path):
                continue
            path_text = _normalize_path_text(path)
            try:
                file_size = path.stat().st_size
            except OSError:
                file_size = 0
            text = (
                _safe_read_text(path) if path.is_file() and file_size <= 500_000 else ""
            )
            redacted = redact_secret_text(text)
            searchable = f"{path_text}\n{redacted}".lower()
            if query_lower and query_lower not in searchable:
                continue
            results.append(
                SecretLookupResult(
                    path=path_text,
                    name=path.name,
                    service_hint=_service_hint(path),
                    redacted_snippet=redacted[:500],
                    revealed_text=text if reveal else "",
                )
            )
            if len(results) >= max_results:
                return results
    return results
