from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.assistant import pipeline


class DeployRuntimePathTests(unittest.TestCase):
    def test_planner_command_uses_cabal_for_local_development_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            command, cwd = pipeline._planner_command_for_semantic_draft('{"task":"rank"}')

        self.assertEqual(
            command[:6],
            ["cabal", "run", "-v0", "ontology-hs", "--", "plan-semantic-draft-json"],
        )
        self.assertEqual(cwd, pipeline.HASKELL_SERVICE_DIR)
        self.assertIn(str(pipeline.ONTOLOGY_PATH), command)
        self.assertIn('{"task":"rank"}', command)

    def test_planner_command_uses_prebuilt_binary_when_configured(self) -> None:
        with patch.dict("os.environ", {pipeline.PLANNER_BINARY_ENV: "/app/bin/ontology-hs"}, clear=True):
            command, cwd = pipeline._planner_command_for_semantic_draft('{"task":"rank"}')

        self.assertEqual(command[:5], ["/app/bin/ontology-hs", "plan-semantic-draft-json", "--ontology", str(pipeline.ONTOLOGY_PATH), "--draft-json"])
        self.assertEqual(command[-1], '{"task":"rank"}')
        self.assertEqual(cwd, pipeline.ROOT)

    def test_snapshot_loader_import_does_not_import_athena_rebuild_module(self) -> None:
        for module_name in [
            "scripts.load_gold_snapshot",
            "scripts.build_gold_slice_snapshot",
            "build_gold_slice_snapshot",
            "boto3",
            "pyarrow",
        ]:
            sys.modules.pop(module_name, None)

        imported = importlib.import_module("scripts.load_gold_snapshot")

        self.assertIsNotNone(imported)
        self.assertNotIn("scripts.build_gold_slice_snapshot", sys.modules)
        self.assertNotIn("build_gold_slice_snapshot", sys.modules)
        self.assertNotIn("boto3", sys.modules)
        self.assertNotIn("pyarrow", sys.modules)

    def test_disabled_snapshot_rebuild_fails_clearly_when_snapshot_is_missing(self) -> None:
        from scripts import load_gold_snapshot

        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.duckdb"
            with (
                patch.object(load_gold_snapshot, "DUCKDB_DIR", Path(temp_dir)),
                patch.object(load_gold_snapshot, "DUCKDB_PATH", missing_path),
                patch.dict("os.environ", {load_gold_snapshot.DISABLE_REBUILD_ENV: "1"}),
            ):
                with self.assertRaises(RuntimeError) as context:
                    load_gold_snapshot.load_database()

        self.assertIn("DuckDB snapshot is missing or stale", str(context.exception))
        self.assertIn(load_gold_snapshot.DISABLE_REBUILD_ENV, str(context.exception))

    def test_existing_snapshot_can_be_loaded_with_rebuild_disabled(self) -> None:
        from scripts import load_gold_snapshot

        with patch.dict("os.environ", {load_gold_snapshot.DISABLE_REBUILD_ENV: "1"}):
            self.assertEqual(load_gold_snapshot.load_database(), load_gold_snapshot.DB_PATH)


if __name__ == "__main__":
    unittest.main()
