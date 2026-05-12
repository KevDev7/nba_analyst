# Purpose:
# Expose ontology and snapshot coverage as a governed catalog-inspection tool.
#
# Uses:
# - fixtures/ontology/semantic-gold.yaml
# - fixtures/duckdb/gold_slice.duckdb coverage metadata
#
# Produces:
# - JSON-serializable catalog slices for future orchestrator planning

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Literal, Optional

import duckdb
import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from scripts.load_gold_snapshot import DB_PATH, load_database


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
UNSUPPORTED_SURFACES = [
    "play_by_play",
    "lineups",
    "on_off",
    "clutch",
    "shot_location",
]
DEFAULT_FACETS = ["subjects", "fact_surfaces", "metrics", "dimensions", "filters", "time_grains", "coverage"]

CatalogFacet = Literal["subjects", "fact_surfaces", "metrics", "dimensions", "filters", "time_grains", "coverage"]


class OntologyCatalogRequest(BaseModel):
    facets: list[CatalogFacet] = Field(default_factory=lambda: list(DEFAULT_FACETS))
    subject_hint: Optional[str] = None
    search: Optional[str] = None
    include_aliases: bool = True
    include_limitations: bool = True
    max_items: int = Field(default=200, ge=1, le=2000)


class OntologyCatalogError(BaseModel):
    code: str
    message: str


class OntologyCatalogResult(BaseModel):
    ok: bool
    ontology_version: Optional[str] = None
    data_snapshot_id: Optional[str] = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    subjects: list[dict[str, Any]] = Field(default_factory=list)
    fact_surfaces: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    time_grains: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    error: Optional[OntologyCatalogError] = None


def inspect(request: Optional[OntologyCatalogRequest] = None) -> OntologyCatalogResult:
    request = request or OntologyCatalogRequest()
    try:
        ontology = _load_ontology()
        objects = [obj for obj in ontology.get("objects", []) if isinstance(obj, dict)]
        selected_objects = _filter_objects(objects, request.subject_hint)
        facets = set(request.facets)
        coverage = _coverage() if "coverage" in facets else {}
        return OntologyCatalogResult(
            ok=True,
            ontology_version=f"semantic-gold:{_file_hash(ONTOLOGY_PATH)}",
            data_snapshot_id=f"gold-snapshot:{_file_hash(DB_PATH)}" if DB_PATH.exists() else None,
            coverage=coverage,
            subjects=_subjects(selected_objects, request) if "subjects" in facets else [],
            fact_surfaces=_fact_surfaces(selected_objects, request) if "fact_surfaces" in facets else [],
            metrics=_metrics(selected_objects, request) if "metrics" in facets else [],
            dimensions=_dimensions(selected_objects, request) if "dimensions" in facets else [],
            filters=_filters(selected_objects, request) if "filters" in facets else [],
            time_grains=_time_grains(selected_objects, request) if "time_grains" in facets else [],
            limitations=_limitations() if request.include_limitations else [],
        )
    except Exception as exc:
        return OntologyCatalogResult(
            ok=False,
            error=OntologyCatalogError(code="ontology_catalog_failed", message=str(exc)),
        )


def _load_ontology() -> dict[str, Any]:
    payload = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ontology payload must be an object.")
    return payload


def _filter_objects(objects: list[dict[str, Any]], subject_hint: Optional[str]) -> list[dict[str, Any]]:
    if not subject_hint:
        return objects
    hint = _normalize(subject_hint)
    filtered = [
        obj for obj in objects
        if hint in _normalize(str(obj.get("name", "")))
        or hint in _normalize(str(obj.get("backing_table", "")))
        or _singular(hint) in _normalize(str(obj.get("name", "")))
        or _singular(hint) in _normalize(str(obj.get("backing_table", "")))
    ]
    return filtered or objects


def _subjects(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    items = []
    for obj in objects:
        if _is_fact_surface(obj):
            continue
        attributes = [attr for attr in obj.get("attributes", []) if isinstance(attr, dict)]
        metrics = [metric for metric in obj.get("metrics", []) if isinstance(metric, dict)]
        item = {
            "key": obj.get("name"),
            "label": _label(str(obj.get("name", ""))),
            "backing_table": obj.get("backing_table"),
            "description": obj.get("description"),
            "attribute_count": len(attributes),
            "metric_count": len(metrics),
        }
        items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "backing_table", "description"]), request.max_items)


def _fact_surfaces(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    items = []
    for obj in objects:
        if not _is_fact_surface(obj):
            continue
        metrics = [metric for metric in obj.get("metrics", []) if isinstance(metric, dict)]
        item = {
            "key": obj.get("name"),
            "label": _label(str(obj.get("name", ""))),
            "subject": _subject_for_fact_surface(str(obj.get("name", ""))),
            "backing_table": obj.get("backing_table"),
            "grain": _grain_for_fact_surface(str(obj.get("name", ""))),
            "metric_count": len(metrics),
        }
        items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "subject", "backing_table", "grain"]), request.max_items)


def _metrics(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    items = []
    for obj in objects:
        for metric in obj.get("metrics", []):
            if not isinstance(metric, dict):
                continue
            item = {
                "key": metric.get("name"),
                "label": _label(str(metric.get("name", ""))),
                "fact_object": obj.get("name"),
                "backing_table": obj.get("backing_table"),
                "aggregation": metric.get("aggregation"),
                "source_attributes": metric.get("source_attributes", []),
                "executable": bool(metric.get("executable")),
                "ranking_polarity": metric.get("ranking_polarity"),
            }
            if request.include_aliases:
                item["aliases"] = metric.get("aliases", [])
            items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "fact_object", "backing_table", "aliases"]), request.max_items)


def _dimensions(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    items = []
    for obj in objects:
        for attr in obj.get("attributes", []):
            if not isinstance(attr, dict) or attr.get("kind") not in {"dimension", "primary_key"}:
                continue
            item = _attribute_item(obj, attr)
            if request.include_aliases:
                item["aliases"] = attr.get("aliases", [])
                item["value_alias_count"] = len(attr.get("value_aliases", {}) or {})
            items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "object", "backing_table", "aliases"]), request.max_items)


def _filters(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    items = []
    for obj in objects:
        for attr in obj.get("attributes", []):
            if not isinstance(attr, dict) or attr.get("visibility") != "public":
                continue
            item = _attribute_item(obj, attr)
            if request.include_aliases:
                item["aliases"] = attr.get("aliases", [])
                item["value_alias_count"] = len(attr.get("value_aliases", {}) or {})
            items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "object", "backing_table", "aliases"]), request.max_items)


def _time_grains(objects: list[dict[str, Any]], request: OntologyCatalogRequest) -> list[dict[str, Any]]:
    time_names = {"game_date", "game_month", "game_year", "game_year_month", "season_year", "season_type"}
    items = []
    for obj in objects:
        for attr in obj.get("attributes", []):
            if not isinstance(attr, dict) or attr.get("name") not in time_names:
                continue
            item = _attribute_item(obj, attr)
            derivation = attr.get("derivation")
            if isinstance(derivation, dict):
                item["derivation"] = {
                    "source_attribute": derivation.get("source_attribute"),
                    "expression_kind": "sql_expression" if derivation.get("sql_expression") else None,
                }
            items.append(item)
    return _limit(_search(items, request.search, ["key", "label", "object", "backing_table"]), request.max_items)


def _attribute_item(obj: dict[str, Any], attr: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": attr.get("name"),
        "label": _label(str(attr.get("name", ""))),
        "object": obj.get("name"),
        "backing_table": obj.get("backing_table"),
        "kind": attr.get("kind"),
        "source_column": attr.get("source_column"),
        "visibility": attr.get("visibility"),
        "comparison_identity": bool(attr.get("comparison_identity")),
    }


def _coverage() -> dict[str, Any]:
    load_database()
    with duckdb.connect(str(DB_PATH), read_only=True) as conn:
        seasons = [row[0] for row in conn.execute("SELECT DISTINCT season_year FROM game ORDER BY season_year").fetchall()]
        season_types = [row[0] for row in conn.execute("SELECT DISTINCT season_type FROM game ORDER BY season_type").fetchall()]
        min_date, max_date, game_count = conn.execute(
            "SELECT MIN(game_date), MAX(game_date), COUNT(*) FROM game"
        ).fetchone()
        row_counts = {
            table: int(count)
            for table, count in conn.execute(
                """
                SELECT table_name, estimated_size
                FROM duckdb_tables()
                WHERE database_name = 'gold_slice'
                ORDER BY table_name
                """
            ).fetchall()
        }
    return {
        "seasons": seasons,
        "season_types": season_types,
        "default_season": seasons[-1] if seasons else None,
        "default_season_type": "regular_season" if "regular_season" in season_types else (season_types[0] if season_types else None),
        "min_game_date": str(min_date) if min_date is not None else None,
        "max_game_date": str(max_date) if max_date is not None else None,
        "game_count": int(game_count or 0),
        "row_counts": row_counts,
        "lowest_grain": "game",
        "unsupported_surfaces": list(UNSUPPORTED_SURFACES),
    }


def _limitations() -> list[str]:
    return [
        "Catalog v1 is derived from semantic-gold.yaml plus DuckDB coverage metadata; Haskell remains the authoritative ontology validator.",
        "The current ontology does not expose possession, lineup, on-off, clutch, shot-location, or play-by-play surfaces as first-class concepts.",
    ]


def _is_fact_surface(obj: dict[str, Any]) -> bool:
    return bool(obj.get("metrics"))


def _subject_for_fact_surface(name: str) -> str:
    if name.startswith("Team"):
        return "Team"
    if name.startswith("Player"):
        return "Player"
    return name


def _grain_for_fact_surface(name: str) -> str:
    if "Game" in name:
        return "game"
    if "Season" in name:
        return "season"
    return "unknown"


def _search(items: list[dict[str, Any]], search: Optional[str], keys: list[str]) -> list[dict[str, Any]]:
    if not search:
        return items
    needle = _normalize(search)
    return [item for item in items if any(_contains(item.get(key), needle) for key in keys)]


def _contains(value: object, needle: str) -> bool:
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return needle in _normalize(str(value))


def _limit(items: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    return items[:max_items]


def _label(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _normalize(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _singular(value: str) -> str:
    return value[:-1] if value.endswith("s") else value


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
