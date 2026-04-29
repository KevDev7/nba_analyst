from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from apps.cli.main import ROOT


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


def call_validate_ontology(ontology_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "ontology-hs",
            "--",
            "validate-ontology-json",
            "--ontology",
            str(ontology_path),
        ],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def write_temp_ontology(payload: dict) -> Path:
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
        handle.write(yaml.safe_dump(payload, sort_keys=False))
        path = Path(handle.name)
    return path


class OntologyLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))

    def test_generated_semantic_gold_ontology_validates(self) -> None:
        result = call_validate_ontology(ONTOLOGY_PATH)

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(json.loads(result.stdout), {"status": "ok"})

    def test_validation_rejects_metric_source_attributes_outside_object(self) -> None:
        ontology = yaml.safe_load(yaml.safe_dump(self.ontology))
        player_game = next(obj for obj in ontology["objects"] if obj["name"] == "PlayerGame")
        player_game["metrics"][0]["source_attributes"] = ["missing_points"]
        path = write_temp_ontology(ontology)
        self.addCleanup(path.unlink, missing_ok=True)

        result = call_validate_ontology(path)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stage"], "OntologyLayer.Validation")
        self.assertIn(
            "metric 'total_points' references missing source attribute 'missing_points'",
            payload["message"],
        )

    def test_validation_rejects_broken_link_keys(self) -> None:
        ontology = yaml.safe_load(yaml.safe_dump(self.ontology))
        ontology["links"][0]["source_key"] = "missing_arena_id"
        path = write_temp_ontology(ontology)
        self.addCleanup(path.unlink, missing_ok=True)

        result = call_validate_ontology(path)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stage"], "OntologyLayer.Validation")
        self.assertIn(
            "source key 'missing_arena_id' does not exist on object 'Game'",
            payload["message"],
        )

    def test_generated_ontology_includes_team_value_aliases(self) -> None:
        team = next(obj for obj in self.ontology["objects"] if obj["name"] == "Team")
        attributes = {attribute["name"]: attribute for attribute in team["attributes"]}

        self.assertIn("western conference", attributes["conference"]["value_aliases"]["west"])
        self.assertIn("LA Lakers", attributes["team_name"]["value_aliases"]["Lakers"])
        self.assertIn("LA Lakers", attributes["team_abbreviation"]["value_aliases"]["LAL"])

    def test_validation_rejects_ambiguous_value_aliases(self) -> None:
        ontology = yaml.safe_load(yaml.safe_dump(self.ontology))
        team = next(obj for obj in ontology["objects"] if obj["name"] == "Team")
        team_name = next(attribute for attribute in team["attributes"] if attribute["name"] == "team_name")
        team_name["value_aliases"]["Lakers"].append("LA")
        team_name["value_aliases"]["Clippers"].append("LA")
        path = write_temp_ontology(ontology)
        self.addCleanup(path.unlink, missing_ok=True)

        result = call_validate_ontology(path)

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["stage"], "OntologyLayer.Validation")
        self.assertIn("attribute 'team_name' has ambiguous value alias 'la'", payload["message"])


if __name__ == "__main__":
    unittest.main()
