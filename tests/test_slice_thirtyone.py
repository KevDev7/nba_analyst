from __future__ import annotations

import json
import subprocess
import unittest

from apps.cli.main import ROOT


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


def call_query_model_foundation_example(example_kind: str) -> dict:
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "query-model-foundation-json",
        example_kind,
    ]
    result = subprocess.run(
        command,
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(payload_text)
    return json.loads(payload_text)


class SliceThirtyOneTests(unittest.TestCase):
    def test_query_model_modules_are_compiled_into_haskell_package(self) -> None:
        cabal_contents = (HASKELL_SERVICE_DIR / "ontology-hs.cabal").read_text(
            encoding="utf-8"
        )

        self.assertIn("QueryModel.Intent", cabal_contents)
        self.assertIn("QueryModel.Ground", cabal_contents)
        self.assertIn("QueryModel.Build", cabal_contents)

    def test_metric_query_foundation_example_normalizes_into_current_ir_shape(self) -> None:
        payload = call_query_model_foundation_example("metric")

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame")
        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["total_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["dimensions"], ["player_name"])
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            payload["spec"]["sharedQuery"]["orders"],
            [{"kind": "desc", "metric": "total_points"}],
        )
        self.assertEqual(payload["spec"]["sharedQuery"]["limit"], 10)
        self.assertEqual(payload["spec"]["entityFilters"], [])
        self.assertIsNone(payload["spec"]["comparison"])

    def test_object_query_foundation_example_normalizes_into_current_ir_shape(self) -> None:
        payload = call_query_model_foundation_example("object")

        self.assertEqual(payload["kind"], "object_query")
        self.assertEqual(payload["spec"]["rowObject"], "Player")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame")
        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["average_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["dimensions"], ["player_name"])
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            payload["spec"]["sharedQuery"]["orders"],
            [{"kind": "desc", "metric": "average_points"}],
        )
        self.assertIsNone(payload["spec"]["sharedQuery"]["limit"])


if __name__ == "__main__":
    unittest.main()
