from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "pipelines" / "athena" / "metadata" / "pipeline_registry.json"

REQUIRED_TOP_LEVEL_KEYS = {"version", "status", "notes", "artifacts"}
REQUIRED_ARTIFACT_KEYS = {
    "id",
    "layer",
    "name",
    "artifact_type",
    "grain",
    "source_keys",
    "destination_key",
    "entrypoint",
    "dependencies",
    "is_heavy",
    "checkpoint_key",
    "schema_owner",
    "gold_or_serving_exposure",
    "notes",
}
VALID_LAYERS = {"raw", "silver", "legacy_gold", "semantic_gold", "serving"}
VALID_ARTIFACT_TYPES = {"source", "table", "view", "artifact"}
VALID_EXPOSURES = {
    "source",
    "qa",
    "review",
    "internal",
    "internal_debug",
    "gold",
    "semantic_gold",
    "serving",
}


def _load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_pipeline_registry_has_expected_shape():
    registry = _load_registry()

    assert REQUIRED_TOP_LEVEL_KEYS <= registry.keys()
    assert registry["version"] == 1
    assert registry["status"]
    assert isinstance(registry["notes"], list)
    assert registry["artifacts"]


def test_pipeline_registry_artifacts_are_well_formed():
    registry = _load_registry()
    artifacts = registry["artifacts"]
    artifact_ids = [artifact["id"] for artifact in artifacts]

    assert len(artifact_ids) == len(set(artifact_ids))

    for artifact in artifacts:
        assert REQUIRED_ARTIFACT_KEYS <= artifact.keys(), artifact["id"]
        assert artifact["layer"] in VALID_LAYERS, artifact["id"]
        assert artifact["artifact_type"] in VALID_ARTIFACT_TYPES, artifact["id"]
        assert artifact["grain"], artifact["id"]
        assert isinstance(artifact["source_keys"], list), artifact["id"]
        assert isinstance(artifact["dependencies"], list), artifact["id"]
        assert isinstance(artifact["is_heavy"], bool), artifact["id"]
        assert artifact["gold_or_serving_exposure"] in VALID_EXPOSURES, artifact["id"]


def test_pipeline_registry_dependency_graph_is_closed():
    registry = _load_registry()
    artifact_ids = {artifact["id"] for artifact in registry["artifacts"]}

    missing_dependencies = {
        (artifact["id"], dependency)
        for artifact in registry["artifacts"]
        for dependency in artifact["dependencies"]
        if dependency not in artifact_ids
    }

    assert missing_dependencies == set()


def test_pipeline_registry_referenced_files_exist():
    registry = _load_registry()

    missing_paths = []
    for artifact in registry["artifacts"]:
        for key in ("entrypoint", "schema_owner"):
            value = artifact[key]
            if value and not (REPO_ROOT / value).exists():
                missing_paths.append((artifact["id"], key, value))

    assert missing_paths == []


def test_pipeline_registry_destination_keys_match_layer_expectations():
    registry = _load_registry()

    for artifact in registry["artifacts"]:
        destination_key = artifact["destination_key"]
        if artifact["artifact_type"] == "view":
            assert destination_key is None, artifact["id"]
            continue
        if artifact["layer"] == "serving":
            assert artifact["id"] == "serving.duckdb_snapshot"
            assert destination_key is None, artifact["id"]
            continue

        assert destination_key, artifact["id"]
        if artifact["layer"] == "raw":
            assert destination_key.startswith("raw/"), artifact["id"]
        if artifact["layer"] == "silver":
            assert destination_key.startswith("silver/"), artifact["id"]
        if artifact["layer"] == "legacy_gold":
            assert destination_key.startswith("legacy_gold/"), artifact["id"]
        if artifact["layer"] == "semantic_gold":
            assert destination_key.startswith("semantic_gold/"), artifact["id"]
