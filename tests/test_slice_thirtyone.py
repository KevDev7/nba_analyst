from __future__ import annotations

import json
import subprocess
import unittest

from apps.cli.main import ROOT


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"

SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}


def call_semantic_draft_planner(draft: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "--builddir=/tmp/nba-analyst-slice31-cabal",
            "ontology-hs",
            "--",
            "plan-semantic-draft-json",
            "--ontology",
            str(ONTOLOGY_PATH),
            "--draft-json",
            json.dumps(draft),
        ],
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
    def test_semantic_draft_module_is_compiled(self) -> None:
        cabal_contents = (HASKELL_SERVICE_DIR / "ontology-hs.cabal").read_text(
            encoding="utf-8"
        )

        self.assertIn("QueryModel.IR", cabal_contents)
        self.assertIn("QueryModel.SemanticDraft", cabal_contents)

    def test_semantic_draft_normalizes_into_current_ir_shape(self) -> None:
        payload = call_semantic_draft_planner(SAMPLE_DRAFT)

        self.assertEqual(payload["kind"] if "kind" in payload else payload["query"]["kind"], "metric_query")
        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(
            shared["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            shared["orders"],
            [{"kind": "desc", "metric": "total_points"}],
        )
        self.assertEqual(shared["limit"], 10)


if __name__ == "__main__":
    unittest.main()
