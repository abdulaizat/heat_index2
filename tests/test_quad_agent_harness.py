"""Sync Quad agent harness tests."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.build_agent_context import build_context
from scripts.sync_quad_agent_docs import sync_agent_docs


class QuadAgentHarnessTests(unittest.TestCase):
    def test_sync_agent_docs_uses_newest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            older = root / "AGENTS.md"
            newer = root / "CLAUDE.md"
            third = root / "GEMINI.md"
            fourth = root / "ANTIGRAVITY.md"

            older.write_text("old\n", encoding="utf-8")
            newer.write_text("newest\n", encoding="utf-8")
            third.write_text("other\n", encoding="utf-8")
            fourth.write_text("antigravity\n", encoding="utf-8")

            os.utime(older, (1, 1))
            os.utime(newer, (3, 3))
            os.utime(third, (2, 2))
            os.utime(fourth, (1, 1))

            state = sync_agent_docs(root)

            self.assertEqual("CLAUDE.md", state["source"])
            for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md", "ANTIGRAVITY.md"):
                self.assertEqual("newest\n", (root / name).read_text(encoding="utf-8"))

            sync_state = json.loads(
                (root / ".harness" / "state" / "quad_agent_sync.json").read_text(encoding="utf-8")
            )
            self.assertEqual("CLAUDE.md", sync_state["source"])
            self.assertIn("ANTIGRAVITY.md", sync_state["targets"])

    def test_build_context_emits_catalog_and_debug_learnings(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            (root / "download_example.py").write_text(
                '"""Example downloader."""\nprint("ok")\n',
                encoding="utf-8",
            )
            (root / "audit_example.py").write_text(
                '"""Example audit."""\nprint("ok")\n',
                encoding="utf-8",
            )
            (root / "example.log").write_text(
                "2026-03-09 01:00:00 ERROR Failed to fetch tile 42\n",
                encoding="utf-8",
            )

            metadata = build_context(root, "pre")

            self.assertEqual("pre", metadata["phase"])
            catalog = (root / ".harness" / "context" / "SCRIPT_CATALOG.md").read_text(encoding="utf-8")
            debug = (root / ".harness" / "context" / "DEBUG_LEARNINGS.md").read_text(encoding="utf-8")
            current = (root / ".harness" / "context" / "CURRENT_CONTEXT.md").read_text(encoding="utf-8")
            guardrails = (root / ".harness" / "context" / "HARNESS_GUARDRAILS.md").read_text(encoding="utf-8")

            self.assertIn("download_example.py", catalog)
            self.assertIn("Failed to fetch tile", debug)
            self.assertIn("Malaysia weather and air-quality workspace", current)
            self.assertIn("Sync Quad Agent Docs", guardrails)
            self.assertIn("ANTIGRAVITY.md", guardrails)

    def test_pre_context_detects_added_changed_and_removed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            kept = root / "process_sample.py"
            removed = root / "old_helper.py"

            kept.write_text('"""Process sample."""\nvalue = 1\n', encoding="utf-8")
            removed.write_text('"""Old helper."""\n', encoding="utf-8")

            build_context(root, "post")

            kept.write_text('"""Process sample changed."""\nvalue = 2\n', encoding="utf-8")
            removed.unlink()
            (root / "new_helper.py").write_text('"""New helper."""\n', encoding="utf-8")

            metadata = build_context(root, "pre")
            self.assertEqual(1, metadata["delta_counts"]["added"])
            self.assertEqual(1, metadata["delta_counts"]["changed"])
            self.assertEqual(1, metadata["delta_counts"]["removed"])

            delta = (root / ".harness" / "context" / "SESSION_DELTA.md").read_text(encoding="utf-8")
            self.assertIn("new_helper.py", delta)
            self.assertIn("process_sample.py", delta)
            self.assertIn("old_helper.py", delta)


if __name__ == "__main__":
    unittest.main()
