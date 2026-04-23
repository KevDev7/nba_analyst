from __future__ import annotations

import json
import subprocess

from apps.cli.main import ROOT


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"


def call_plan_query_json(query_payload: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "ontology-hs",
            "--",
            "plan-query-json",
            "--ontology",
            str(ONTOLOGY_PATH),
            "--query-json",
            json.dumps(query_payload),
        ],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if not payload_text:
        raise RuntimeError("Haskell planner returned no output.")
    payload = json.loads(payload_text)
    if result.returncode != 0:
        raise RuntimeError(payload.get("message", payload_text))
    return payload
