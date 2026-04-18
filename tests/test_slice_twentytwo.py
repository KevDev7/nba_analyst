from __future__ import annotations

import unittest
from collections import deque
from pathlib import Path

import yaml

from apps.cli.semantic_interpreter import ROOT, _capability_artifact


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


def _load_ontology() -> dict:
    return yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))


class SliceTwentyTwoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ontology = _load_ontology()
        cls.objects_by_name = {
            object_entry["name"]: object_entry for object_entry in cls.ontology["objects"]
        }
        cls.links_from_object: dict[str, list[str]] = {}
        for link in cls.ontology["links"]:
            cls.links_from_object.setdefault(link["source_object"], []).append(
                link["target_object"]
            )

    def test_capabilities_only_advertise_executable_ontology_metrics(self) -> None:
        artifact = _capability_artifact()

        for family in artifact["families"]:
            executable_metrics = {
                metric["name"]
                for metric in self.objects_by_name[family["core_fact_object"]].get("metrics", [])
                if metric.get("executable")
            }
            self.assertTrue(
                set(family["metrics"]).issubset(executable_metrics),
                msg=f"{family['family_key']} exposed metrics {family['metrics']} outside executable ontology metrics {sorted(executable_metrics)}",
            )

    def test_capabilities_do_not_advertise_non_executable_points_per_36(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family["family_key"]
            for family in artifact["families"]
            if "points_per_36" in family["metrics"]
        ]

        self.assertEqual(matching, [])

    def test_capability_dimensions_stay_within_ontology_backed_surface(self) -> None:
        artifact = _capability_artifact()

        for family in artifact["families"]:
            if family["query_kind"] == "object_query":
                supported_dimensions = self._public_dimensions(family["row_object"])
            else:
                supported_dimensions = self._reachable_dimensions(family["core_fact_object"])

            self.assertTrue(
                set(family["dimensions"]).issubset(supported_dimensions),
                msg=f"{family['family_key']} exposed dimensions {family['dimensions']} outside ontology-backed supported dimensions {sorted(supported_dimensions)}",
            )

    def test_known_object_metrics_aggregate_from_ontology_truth(self) -> None:
        artifact = _capability_artifact()

        team_game_monthly = next(
            family
            for family in artifact["families"]
            if family["family_key"] == "team_game_monthly_metric"
        )
        self.assertEqual(team_game_monthly["metrics"], ["average_points", "total_points"])

        player_season_team = next(
            family
            for family in artifact["families"]
            if family["family_key"] == "player_season_team_season_metric"
        )
        self.assertEqual(
            player_season_team["metrics"],
            ["average_points", "games_played", "total_points"],
        )

    def _public_dimensions(self, object_name: str | None) -> set[str]:
        if object_name is None:
            return set()

        object_entry = self.objects_by_name[object_name]
        return {
            attribute["name"]
            for attribute in object_entry.get("attributes", [])
            if attribute.get("visibility") == "public"
            and attribute.get("kind") == "dimension"
        }

    def _reachable_dimensions(self, fact_object_name: str) -> set[str]:
        reachable_objects = {fact_object_name}
        queue: deque[tuple[str, int]] = deque([(fact_object_name, 0)])

        while queue:
            current_object, depth = queue.popleft()
            if depth >= 2:
                continue
            for target_object in self.links_from_object.get(current_object, []):
                if target_object in reachable_objects:
                    continue
                reachable_objects.add(target_object)
                queue.append((target_object, depth + 1))

        supported_dimensions: set[str] = set()
        for object_name in reachable_objects:
            supported_dimensions.update(self._public_dimensions(object_name))
        return supported_dimensions


if __name__ == "__main__":
    unittest.main()
