"""
File Scanner — Directory walking with change detection.

Uses os.scandir for speed, mtime + MD5 hash for change detection.
Detects new, modified, moved, and deleted files.
"""

from collections import Counter, defaultdict
import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from .config import config
    from .catalog import Catalog
except ImportError:
    from config import config
    from catalog import Catalog

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a detected file change."""

    path: str  # Relative path
    full_path: str  # Absolute path
    change_type: str  # "new", "modified", "moved", "deleted"
    size: int = 0
    mtime: float = 0
    content_hash: str = ""
    ext: str = ""
    previous_path: str = ""
    previous_full_path: str = ""

    @property
    def tier(self) -> str:
        # Avoid importing at class level if possible, use global config object
        try:
            from .config import config as cfg
        except ImportError:
            from config import config as cfg
        if any(part in self.path.split("/") for part in cfg.system_dirs):
            return "system"
        if self.size <= cfg.tier1_max_size:
            return "user"
        if self.size <= cfg.tier2_max_size:
            return "large"
        return "system"  # Massive files fall back to system limiting


class FileScanner:
    """Directory scanner with change detection."""

    def __init__(self, config_obj=None):
        """
        Initialize scanner.

        Args:
            config_obj: Configuration object (uses global config if None)
        """
        self.cfg = config_obj or config
        self._duplicate_alias_skips = 0
        self._excluded_paths: set[str] = set()
        self._prunable_excluded_paths: set[str] = set()
        self._retained_excluded_paths: set[str] = set()
        self._prunable_excluded_reasons: dict[str, str] = {}

    @property
    def excluded_paths(self) -> set[str]:
        return set(self._excluded_paths)

    @property
    def prunable_excluded_paths(self) -> set[str]:
        return set(self._prunable_excluded_paths)

    @property
    def retained_excluded_paths(self) -> set[str]:
        return set(self._retained_excluded_paths)

    def _canonical_fs_path(self, path: str) -> str:
        """Normalize a path to its real filesystem target for de-duplication."""
        return os.path.normcase(os.path.realpath(path))

    def _index_extension(self, filename: str) -> str:
        """Return FileMind's index extension, including dotfile config names."""

        name = filename.lower()
        if name == ".env" or name.startswith(".env."):
            return ".env"
        return os.path.splitext(filename)[1].lower()

    def _make_index_path(self, filepath: str, root: Path) -> str:
        """Build a stable catalog key across multiple scan roots.

        Prefer paths relative to AI_STATION when the file lives inside the
        workspace. Otherwise fall back to USERPROFILE-relative paths so roots
        like `C:\\Users\\...\\.claude` become `.claude/settings.json` instead of
        unstable root-local names like `settings.json`.
        """
        absolute_path = Path(os.path.abspath(filepath))
        ai_station_root = Path(os.path.abspath(str(self.cfg.ai_station_root)))
        user_home = Path(os.path.abspath(str(self.cfg.user_home)))
        root_path = Path(os.path.abspath(str(root)))

        for base in (ai_station_root, user_home):
            try:
                return absolute_path.relative_to(base).as_posix()
            except ValueError:
                continue

        try:
            rel_root = root_path.relative_to(user_home).as_posix()
        except ValueError:
            rel_root = root_path.name or "external"

        try:
            rel_path = absolute_path.relative_to(root_path).as_posix()
        except ValueError:
            rel_path = absolute_path.name

        return f"{rel_root}/{rel_path}".strip("/")

    def _should_skip_dir(self, dirname: str) -> bool:
        """Check if directory should be skipped."""
        if dirname in self.cfg.skip_dirs:
            return True
        if dirname.endswith(".egg-info"):
            return True
        # Exact-name guard for historically noisy roots without swallowing
        # sibling runtimes like `.claude-code`.
        if dirname in {".claude", "backups"}:
            return True
        return False

    def _should_skip_subdir(self, dirname: str, parent_path: str) -> bool:
        """Check if subdirectory should be skipped, with high-value override."""
        # Build the full path for pattern matching
        full_dir = os.path.join(parent_path, dirname).replace("\\", "/")

        # Check against SKIP_SUBDIRS patterns — both exact name match and path-included match
        for skip_pattern in self.cfg.skip_subdirs:
            # Direct name match (e.g., ".venv", "__pycache__")
            if dirname == skip_pattern:
                return True
            # Path-included match (e.g., ".kimi/owl-agent/.git", "owl-agent/community_usecase")
            if skip_pattern in full_dir:
                return True

        # High-value include override: check if this dir matches a high-value pattern
        for pattern in self.cfg.high_value_include_patterns:
            pattern_parts = pattern.rstrip("/").split("/")
            if len(pattern_parts) >= 2:
                parent_pattern = "/".join(pattern_parts[:-1])
                child_name = pattern_parts[-1]
                if parent_pattern in full_dir and dirname == child_name:
                    return False  # High-value match — do NOT skip

        return False

    def _should_include_file(self, rel_path: str) -> bool:
        """Check if a file should be included based on high-value include patterns.

        For paths inside a high-value directory (e.g., .kimi/owl-agent/),
        only specific file patterns are allowed. For paths inside fully-included
        directories (e.g., .kimi/sessions/), all files are allowed.
        """
        # Hard exclusions — always skip these regardless of other rules
        for pattern in self.cfg.skip_file_patterns:
            if pattern in rel_path:
                return False
        if ".kimi/credentials/" in rel_path:
            return False
        if ".kimi/logs/" in rel_path:
            return False
        # Skip .kimi/.kimi mirror entirely
        if ".kimi/.kimi/" in rel_path or rel_path == ".kimi/.kimi":
            return False

        # Fully-included directories — everything inside is allowed
        full_include_dirs = {
            ".kimi/plans",
            ".kimi/sessions",
            ".kimi/scripts",
            ".kimi/claudedocs",
        }
        for inc_dir in full_include_dirs:
            if rel_path.startswith(inc_dir + "/") or rel_path == inc_dir:
                return True

        # Top-level .kimi files
        top_level_files = {"config.toml", "kimi_inventory.txt", "kimi.json"}
        if rel_path in top_level_files:
            return True

        # owl-agent: only allow explicitly listed patterns
        if "owl-agent/" in rel_path:
            # Exclude noise files/dirs regardless of extension
            noise_patterns = [
                ".git/",
                ".venv/",
                ".container/",
                ".github/",
                "licenses/",
                "community_usecase/",
                ".gitignore",
                ".pre-commit-config.yaml",
                "uv.lock",
                "pyproject.toml",
                "LICENSE",
                "LICENSE.txt",
                # Asset noise
                "assets/community_code.jpeg",
                "assets/owl-favicon.ico",
                "assets/owl-favicon.png",
                "assets/owl_architecture.png",
                # Env files
                ".env_template",
                ".env",
            ]
            for noise in noise_patterns:
                if noise in rel_path:
                    return False

            # Allowed files
            allowed_files = [
                "README.md",
                "README_zh.md",
                "README_ja.md",
                "CITATION.cff",
                "community_challenges.md",
            ]
            for allowed in allowed_files:
                if rel_path.endswith("/" + allowed) or rel_path == allowed:
                    return True

            # Allowed directories content (owl/ source, examples/)
            if "owl-agent/owl/" in rel_path:
                return True
            if "owl-agent/examples/" in rel_path:
                return True
            if "owl-agent/assets/" in rel_path:
                # Only specific assets
                allowed_assets = ["OWL_Technical_Report.pdf"]
                for a in allowed_assets:
                    if rel_path.endswith(a):
                        return True
                return False

            return False

        # Default: include if not explicitly excluded
        return True

    def _compute_hash(self, filepath: str) -> str:
        """Compute MD5 hash of first 64KB for change detection."""
        h = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                h.update(f.read(self.cfg.duplicate_hash_size))
            return h.hexdigest()
        except (OSError, PermissionError):
            return ""

    def _evaluate_existing_path_scope(
        self, full_path: str, size: int = 0
    ) -> tuple[bool, str]:
        """Return whether an on-disk file is still in FileMind's current scan scope."""
        full_abs = os.path.normcase(os.path.abspath(full_path))

        for root_dir in self.cfg.scan_roots:
            root_abs = os.path.normcase(os.path.abspath(root_dir))
            if full_abs != root_abs and not full_abs.startswith(root_abs + os.sep):
                continue

            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")
            if rel_path.startswith(".."):
                continue

            parts = [part for part in Path(rel_path).parts if part not in ("", ".")]
            if not parts:
                return False, "root_directory"

            parent_path = os.path.abspath(root_dir)
            for dirname in parts[:-1]:
                if self._should_skip_dir(dirname):
                    return False, f"skip_dir:{dirname}"
                if self._should_skip_subdir(dirname, parent_path):
                    return False, f"skip_subdir:{dirname}"
                parent_path = os.path.join(parent_path, dirname)

            filename = parts[-1]
            ext = self._index_extension(filename)
            if ext not in self.cfg.index_extensions:
                return False, f"extension:{ext or '<none>'}"
            if size and size > self.cfg.tier2_max_size:
                return False, "oversize"
            if not self._should_include_file(rel_path):
                return False, "file_rule"
            return True, "included"

        return False, "out_of_scope_root"

    def _should_prune_excluded_record(
        self, record: dict, scanned_real_paths: set[str]
    ) -> tuple[bool, str]:
        """Return whether an excluded indexed record should be pruned from the live index."""
        full_path = record.get("full_path", "")
        size = int(record.get("size") or 0)

        if full_path and os.path.exists(full_path):
            real_path = self._canonical_fs_path(full_path)
            if real_path in scanned_real_paths:
                return True, "alias_overlap"
            in_scope, reason = self._evaluate_existing_path_scope(full_path, size=size)
            return (not in_scope), reason

        rel_path = record.get("path", "")
        if rel_path and os.path.exists(rel_path):
            in_scope, reason = self._evaluate_existing_path_scope(rel_path, size=size)
            return (not in_scope), f"fallback:{reason}"

        return False, "missing_on_disk"

    def scan(
        self, catalog: Optional[Catalog] = None
    ) -> tuple[list[FileChange], set[str]]:
        """
        Scan configured directories for changes.

        Returns:
            (changes, deleted_paths) — list of FileChange and set of deleted file paths
        """
        owns_catalog = catalog is None
        catalog = catalog or Catalog()
        catalog.init_db()

        all_changes: list[FileChange] = []
        scanned_paths: set[str] = set()
        scanned_real_paths: set[str] = set()
        self._duplicate_alias_skips = 0
        self._excluded_paths = set()
        self._prunable_excluded_paths = set()
        self._retained_excluded_paths = set()
        self._prunable_excluded_reasons = {}

        for root_dir in self.cfg.scan_roots:
            root_path = Path(root_dir)
            if not root_path.exists():
                logger.warning(f"Scan root not found: {root_dir}")
                continue

            logger.info(f"Scanning: {root_dir}")
            changes = self._scan_directory(
                root_path, catalog, scanned_paths, scanned_real_paths
            )
            all_changes.extend(changes)

        # Find deleted files (in catalog but not scanned)
        truly_deleted, excluded, prunable_excluded = self._find_deleted(
            catalog, scanned_paths, scanned_real_paths
        )
        all_changes, truly_deleted = self._reconcile_moves(
            all_changes, truly_deleted, catalog
        )
        self._excluded_paths = excluded
        self._prunable_excluded_paths = prunable_excluded
        self._retained_excluded_paths = excluded - prunable_excluded

        # Log exclusion summary
        if excluded:
            logger.info(
                f"  Excluded from scan (still on disk): {len(excluded)} files "
                f"(skip rules or root changes — NOT deleted from index)"
            )
        if prunable_excluded:
            reason_counts = Counter(self._prunable_excluded_reasons.values())
            reason_summary = ", ".join(
                f"{reason}={count}" for reason, count in sorted(reason_counts.items())
            )
            logger.info(
                f"  Prunable excluded index entries: {len(prunable_excluded)} files"
            )
            if reason_summary:
                logger.info(f"    Reasons: {reason_summary}")
        if self._retained_excluded_paths:
            logger.info(
                f"  Retained excluded entries for safety review: {len(self._retained_excluded_paths)} files"
            )

        if self._duplicate_alias_skips:
            logger.info(
                f"  Skipped alias/overlap duplicates: {self._duplicate_alias_skips} files"
            )

        if owns_catalog:
            catalog.close()
        return all_changes, truly_deleted

    def _scan_directory(
        self,
        root: Path,
        catalog: Catalog,
        scanned_paths: set[str],
        scanned_real_paths: set[str],
    ) -> list[FileChange]:
        """Recursively scan a directory for changes."""
        changes = []

        for dirpath, dirnames, filenames in os.walk(str(root)):
            # CRITICAL: Remove symlink/junction dirs BEFORE os.walk descends into them
            # This prevents infinite recursion (e.g., .kimi/.kimi -> .kimi)
            dirs_to_remove = []
            for d in dirnames:
                full_dir = os.path.join(dirpath, d)
                # Check if it's a symlink or junction point
                if os.path.islink(full_dir) or os.path.isjunction(full_dir):
                    dirs_to_remove.append(d)
                # Also check against skip patterns
                elif self._should_skip_dir(d) or self._should_skip_subdir(d, dirpath):
                    dirs_to_remove.append(d)

            for d in dirs_to_remove:
                dirnames.remove(d)

            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                ext = self._index_extension(filename)

                if ext not in self.cfg.index_extensions:
                    continue

                # Check file-level high-value include patterns
                # This ensures we only index specific files from owl-agent, etc.
                rel_from_root = os.path.relpath(filepath, str(root)).replace("\\", "/")
                if not self._should_include_file(rel_from_root):
                    continue

                real_path = self._canonical_fs_path(filepath)
                if real_path in scanned_real_paths:
                    self._duplicate_alias_skips += 1
                    continue
                scanned_real_paths.add(real_path)

                try:
                    stat = os.stat(filepath)
                except (OSError, PermissionError):
                    continue

                if stat.st_size > self.cfg.tier2_max_size:
                    continue

                rel_path = self._make_index_path(filepath, root)

                scanned_paths.add(rel_path)

                mtime = stat.st_mtime
                content_hash = self._compute_hash(filepath)

                # Check if file exists in catalog
                existing = catalog.get_file(rel_path)

                if existing is None:
                    # New file
                    changes.append(
                        FileChange(
                            path=rel_path,
                            full_path=os.path.abspath(filepath).replace("\\", "/"),
                            change_type="new",
                            size=stat.st_size,
                            mtime=mtime,
                            content_hash=content_hash,
                            ext=ext,
                        )
                    )
                elif (
                    existing["mtime"] != mtime
                    or existing["content_hash"] != content_hash
                ):
                    # Modified file
                    changes.append(
                        FileChange(
                            path=rel_path,
                            full_path=os.path.abspath(filepath).replace("\\", "/"),
                            change_type="modified",
                            size=stat.st_size,
                            mtime=mtime,
                            content_hash=content_hash,
                            ext=ext,
                        )
                    )

        return changes

    def _find_deleted(
        self, catalog: Catalog, scanned_paths: set[str], scanned_real_paths: set[str]
    ) -> tuple[set[str], set[str], set[str]]:
        """Find files in catalog that no longer exist on disk.

        Returns:
            (truly_deleted, excluded, prunable_excluded) — truly deleted vs intentionally
            excluded by config vs excluded entries that should be pruned from the live index
        """
        truly_deleted = set()
        excluded = set()
        prunable_excluded = set()
        stats = catalog.get_stats()

        all_categories = list(stats.get("categories", {}).keys())
        for cat in all_categories:
            files = catalog.get_files_by_category(cat)
            for f in files:
                if f["path"] not in scanned_paths:
                    # Safety check: does the file still exist on disk?
                    full_path = f.get("full_path", "")
                    if full_path and os.path.exists(full_path):
                        # File still exists on disk but wasn't scanned —
                        # likely excluded by new skip rules or scan root changes.
                        excluded.add(f["path"])
                        should_prune, reason = self._should_prune_excluded_record(
                            f, scanned_real_paths
                        )
                        if should_prune:
                            prunable_excluded.add(f["path"])
                            self._prunable_excluded_reasons[f["path"]] = reason
                    elif os.path.exists(f["path"]):
                        # Try relative path as fallback
                        excluded.add(f["path"])
                        should_prune, reason = self._should_prune_excluded_record(
                            f, scanned_real_paths
                        )
                        if should_prune:
                            prunable_excluded.add(f["path"])
                            self._prunable_excluded_reasons[f["path"]] = reason
                    else:
                        # File genuinely gone from disk
                        truly_deleted.add(f["path"])

        return truly_deleted, excluded, prunable_excluded

    def _reconcile_moves(
        self, changes: list[FileChange], deleted_paths: set[str], catalog: Catalog
    ) -> tuple[list[FileChange], set[str]]:
        """Convert matching delete+new pairs into move events."""
        if not changes or not deleted_paths:
            return changes, deleted_paths

        deleted_by_identity: dict[tuple[str, int, str], list[dict]] = defaultdict(list)
        for path in deleted_paths:
            record = catalog.get_file(path)
            if not record:
                continue
            content_hash = record.get("content_hash") or ""
            if not content_hash:
                continue
            key = (content_hash, int(record.get("size") or 0), record.get("ext") or "")
            deleted_by_identity[key].append(record)

        unmatched_deleted = set(deleted_paths)
        reconciled: list[FileChange] = []
        moves_detected = 0

        for change in changes:
            if change.change_type != "new" or not change.content_hash:
                reconciled.append(change)
                continue

            key = (change.content_hash, int(change.size), change.ext)
            candidates = [
                record
                for record in deleted_by_identity.get(key, [])
                if record["path"] in unmatched_deleted
            ]

            if len(candidates) != 1:
                reconciled.append(change)
                continue

            previous = candidates[0]
            unmatched_deleted.discard(previous["path"])
            reconciled.append(
                FileChange(
                    path=change.path,
                    full_path=change.full_path,
                    change_type="moved",
                    size=change.size,
                    mtime=change.mtime,
                    content_hash=change.content_hash,
                    ext=change.ext,
                    previous_path=previous["path"],
                    previous_full_path=previous.get("full_path", ""),
                )
            )
            moves_detected += 1

        if moves_detected:
            logger.info(f"  Detected {moves_detected} moved files via hash/size match")

        return reconciled, unmatched_deleted

    def get_changes_summary(self, changes: list[FileChange], deleted: set[str]) -> dict:
        """Generate summary of detected changes."""
        new_count = sum(1 for c in changes if c.change_type == "new")
        mod_count = sum(1 for c in changes if c.change_type == "modified")
        moved_count = sum(1 for c in changes if c.change_type == "moved")
        del_count = len(deleted)

        return {
            "new": new_count,
            "modified": mod_count,
            "moved": moved_count,
            "deleted": del_count,
            "total_changes": new_count + mod_count + moved_count + del_count,
        }


def scan_directories() -> tuple[list[FileChange], set[str]]:
    """Convenience function: scan with default config."""
    scanner = FileScanner()
    return scanner.scan()
