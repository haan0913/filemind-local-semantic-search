"""Regression tests for agent-root skip behavior."""

import unittest

from filemind.config import (
    AGENT_WORKING_DIR_INVENTORY,
    AGENT_WORKING_DIR_LANES,
    agent_subpath_lane,
    agent_working_dir_lane,
    config,
)
from filemind.scanner import FileScanner


def scanner_path_key(path):
    return str(path)


class ScannerAgentRootTests(unittest.TestCase):
    def test_agent_inventory_covers_required_task_160_aliases(self):
        expected_lanes = {
            ".codex": "normal",
            ".claude": "normal",
            ".kimi": "normal",
            ".cline": "normal",
            ".openclaw": "normal",
            ".agents": "normal",
            ".windsurf": "normal",
            ".aider": "normal",
            ".codeium": "normal",
            ".copilot": "normal",
            ".claude-code": "normal",
            ".gemini": "normal",
            ".qwen": "normal",
            ".antigravity": "normal",
            "opencode": "normal",
            "OpenCode": "normal",
            "cagent": "normal",
            "agent-browser": "normal",
            "mcporter": "normal",
            "n8n": "normal",
            "playwright-mcp": "normal",
            "pm2": "normal",
            ".node-llama-cpp": "excluded",
            ".ollama": "excluded",
            "u2net": "excluded",
            "huggingface": "excluded",
            ".codex/sessions": "protected",
            ".codex/sessions/session.jsonl": "protected",
            ".kimi/credentials": "protected",
            ".ollama/models/blobs/sha256-abcd": "excluded",
        }

        for alias, lane in expected_lanes.items():
            with self.subTest(alias=alias):
                self.assertEqual(agent_working_dir_lane(alias), lane)

    def test_agent_inventory_uses_all_task_160_lanes(self):
        self.assertEqual(
            {spec.lane for spec in AGENT_WORKING_DIR_INVENTORY}, AGENT_WORKING_DIR_LANES
        )

    def test_existing_normal_agent_roots_are_default_scan_roots(self):
        scan_root_keys = {scanner_path_key(root) for root in config.scan_roots}
        for spec in AGENT_WORKING_DIR_INVENTORY:
            if spec.lane != "normal":
                continue
            existing_paths = [path for path in spec.paths if path.exists()]
            if not existing_paths:
                continue
            with self.subTest(agent_root=spec.name):
                self.assertTrue(
                    any(
                        scanner_path_key(path) in scan_root_keys
                        for path in existing_paths
                    ),
                    f"{spec.name} has an existing normal-lane path but no scan root",
                )

    def test_excluded_model_blob_roots_are_not_default_scan_roots(self):
        scan_root_keys = {scanner_path_key(root) for root in config.scan_roots}
        for spec in AGENT_WORKING_DIR_INVENTORY:
            if spec.lane != "excluded":
                continue
            for path in spec.paths:
                if not path.exists():
                    continue
                with self.subTest(agent_root=spec.name, path=str(path)):
                    self.assertNotIn(scanner_path_key(path), scan_root_keys)

    def test_raw_sessions_and_credentials_are_protected_subpaths(self):
        protected_paths = [
            ".codex/sessions/session.jsonl",
            ".claude/projects/project.jsonl",
            ".kimi/credentials/tokens.json",
            ".qwen/projects/project.jsonl",
            ".gemini/antigravity/brain/state.json",
        ]

        for rel_path in protected_paths:
            with self.subTest(rel_path=rel_path):
                self.assertEqual(agent_subpath_lane(rel_path), "protected")

    def test_agent_runtime_noise_is_excluded_subpath(self):
        excluded_paths = [
            ".ollama/models/blobs/sha256-abcd",
            ".node-llama-cpp/vendor/build.log",
            ".u2net/u2net.pth",
            ".cache/huggingface/hub/models--org--model",
            ".playwright-mcp/browser-profile/Default/History",
            ".pm2/logs/service-out.log",
            ".local/share/opencode/storage/session_diff/ses_123.json",
        ]

        for rel_path in excluded_paths:
            with self.subTest(rel_path=rel_path):
                self.assertEqual(agent_subpath_lane(rel_path), "excluded")

    def test_agent_config_docs_stay_normal_subpath(self):
        normal_paths = [
            ".codex/AGENTS.md",
            ".gemini/settings.json",
            ".windsurf/config.json",
            ".n8n/workflows/example.json",
        ]

        for rel_path in normal_paths:
            with self.subTest(rel_path=rel_path):
                self.assertEqual(agent_subpath_lane(rel_path), "normal")

    def test_exact_claude_root_is_still_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir(".claude"))

    def test_claude_code_root_is_not_swallowed_by_claude_skip(self):
        scanner = FileScanner()
        self.assertFalse(scanner._should_skip_dir(".claude-code"))

    def test_backups_is_still_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir("backups"))

    def test_pytest_cache_is_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir(".pytest_cache"))

    def test_bench_dir_is_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir(".bench"))

    def test_shadow_index_and_run_dirs_are_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir(".index_shadow"))
        self.assertTrue(scanner._should_skip_dir(".shadow_runs"))

    def test_egg_info_dir_is_skipped(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir("filemind.egg-info"))

    def test_codex_worktrees_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir(
                "worktrees", r"C:\AI_STATION\hub\agents\assistants\.codex"
            )
        )

    def test_codex_vendor_imports_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir(
                "vendor_imports", r"C:\AI_STATION\hub\agents\assistants\.codex"
            )
        )

    def test_runtime_tmp_is_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir(
                "tmp", r"C:\AI_STATION\governance\skill_router\.runtime"
            )
        )

    def test_eval_result_artifacts_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir("results", r"C:\AI_STATION\hub\docs\evals")
        )

    def test_obsidian_backups_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir("_backups", r"C:\AI_STATION\hub\notes")
        )

    def test_obsidian_quarantine_and_raw_bookmark_batches_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir("_vault_quarantine", r"C:\AI_STATION\hub\notes")
        )
        self.assertTrue(
            scanner._should_skip_subdir(
                ".obsidian", r"C:\AI_STATION\hub\notes\obsidian-vault"
            )
        )
        self.assertTrue(
            scanner._should_skip_subdir(
                "manual_tweet_synthesis_2026-04-26",
                r"C:\AI_STATION\hub\notes\obsidian-vault\00_Raw\imports\bookmark_intelligence",
            )
        )

    def test_opencode_session_diffs_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir(
                "session_diff",
                r"C:\AI_STATION\hub\agents\frameworks\.local\share\opencode\storage",
            )
        )

    def test_agent_browser_profiles_are_skipped_as_noise(self):
        scanner = FileScanner()
        self.assertTrue(
            scanner._should_skip_subdir(
                "browser-profile", r"C:\Users\amirk\.playwright-mcp"
            )
        )

    def test_excluded_model_roots_are_skipped_under_workspace_scan(self):
        scanner = FileScanner()
        self.assertTrue(scanner._should_skip_dir(".ollama"))
        self.assertTrue(scanner._should_skip_dir(".node-llama-cpp"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
