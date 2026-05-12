from __future__ import annotations

import json
import os
import statistics
import subprocess
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
RUN_ENV = "NBA_RUN_PERFORMANCE_BENCHMARKS"


DRAFTS = {
    "rank_players_points": {
        "task": "rank",
        "subject": "players",
        "measure": "points",
        "measures": ["points"],
        "time_window": {"kind": "last_n_games", "value": 10},
        "limit": 10,
        "sort": "desc",
        "assumptions": [],
    },
    "rank_team_road_net_rating": {
        "task": "rank",
        "subject": "teams",
        "measure": "net rating",
        "measures": ["net rating"],
        "filters": [{"field": "team home or away", "op": "=", "value": "road"}],
        "time_window": {"kind": "last_n_games", "value": 10},
        "rank_intent": "ranked",
        "assumptions": [],
    },
    "result_filter_players_points": {
        "task": "rank",
        "subject": "players",
        "measure": "total points",
        "result_filters": [{"field": "total points", "op": ">", "value": 200}],
        "time_window": {"kind": "last_n_games", "value": 10},
        "sort": "desc",
        "assumptions": [],
    },
    "compare_brunson_tatum": {
        "task": "compare",
        "subject": "players",
        "measure": "points",
        "measures": ["points", "assists", "rebounds"],
        "time_window": {"kind": "last_n_games", "value": 10},
        "entities": ["Brunson", "Tatum"],
        "resolved_entities": [
            {"entityId": 1628973, "entityName": "Jalen Brunson"},
            {"entityId": 1628369, "entityName": "Jayson Tatum"},
        ],
        "assumptions": [],
    },
    "find_lakers_high_score_games": {
        "task": "find",
        "subject": "games",
        "measure": None,
        "measures": [],
        "dimensions": ["date", "opponent", "score"],
        "filters": [
            {"field": "team", "op": "=", "value": "Lakers"},
            {"field": "points", "op": ">", "value": 120},
        ],
        "time_window": {"kind": "all", "value": None},
        "order": [{"by": "date", "direction": "desc"}],
        "entities": ["Lakers"],
        "assumptions": [],
    },
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _planner_binary() -> str:
    result = subprocess.run(
        ["cabal", "list-bin", "-v0", "exe:ontology-hs"],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def _command(label: str, planner_binary: str, draft: dict[str, object]) -> tuple[list[str], Path]:
    args = [
        "plan-semantic-draft-json",
        "--ontology",
        str(ONTOLOGY_PATH),
        "--draft-json",
        json.dumps(draft),
    ]
    if label == "cabal_run":
        return ["cabal", "run", "-v0", "ontology-hs", "--", *args], HASKELL_SERVICE_DIR
    return [planner_binary, *args], ROOT


def _run_one(label: str, planner_binary: str, draft: dict[str, object]) -> float:
    command, cwd = _command(label, planner_binary, draft)
    start = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    elapsed_ms = (time.perf_counter() - start) * 1000
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    payload = json.loads(result.stdout)
    if "execution_plan" not in payload:
        raise RuntimeError("Planner benchmark did not return an execution plan.")
    return elapsed_ms


@unittest.skipUnless(_enabled(RUN_ENV), f"Set {RUN_ENV}=1 to run performance benchmarks.")
class PlannerLatencyBenchmarkTests(unittest.TestCase):
    def test_prebuilt_binary_reduces_median_planner_invocation_latency(self) -> None:
        planner_binary = _planner_binary()
        samples_per_draft = int(os.getenv("NBA_PLANNER_BENCHMARK_SAMPLES", "8"))
        minimum_reduction_pct = float(os.getenv("NBA_PLANNER_BENCHMARK_MIN_REDUCTION_PCT", "50"))

        # Warm both paths so the benchmark measures steady-state invocation overhead.
        for draft in DRAFTS.values():
            _run_one("prebuilt_binary", planner_binary, draft)
            _run_one("cabal_run", planner_binary, draft)

        samples: dict[str, list[float]] = {"cabal_run": [], "prebuilt_binary": []}
        by_draft: dict[str, dict[str, list[float]]] = {
            name: {"cabal_run": [], "prebuilt_binary": []} for name in DRAFTS
        }
        for index in range(samples_per_draft):
            for name, draft in DRAFTS.items():
                order = (
                    ("cabal_run", "prebuilt_binary")
                    if (index + len(name)) % 2 == 0
                    else ("prebuilt_binary", "cabal_run")
                )
                for label in order:
                    elapsed_ms = _run_one(label, planner_binary, draft)
                    samples[label].append(elapsed_ms)
                    by_draft[name][label].append(elapsed_ms)

        cabal_median = statistics.median(samples["cabal_run"])
        binary_median = statistics.median(samples["prebuilt_binary"])
        reduction_pct = (cabal_median - binary_median) / cabal_median * 100
        result = {
            "samples_per_path": len(samples["cabal_run"]),
            "cabal_run_median_ms": round(cabal_median, 2),
            "prebuilt_binary_median_ms": round(binary_median, 2),
            "median_speedup_x": round(cabal_median / binary_median, 2),
            "median_reduction_pct": round(reduction_pct, 1),
            "by_draft": {
                name: {
                    "cabal_run_median_ms": round(statistics.median(values["cabal_run"]), 2),
                    "prebuilt_binary_median_ms": round(
                        statistics.median(values["prebuilt_binary"]), 2
                    ),
                }
                for name, values in by_draft.items()
            },
        }
        print("PLANNER_LATENCY_BENCHMARK_JSON", json.dumps(result, sort_keys=True))

        self.assertGreaterEqual(reduction_pct, minimum_reduction_pct)
