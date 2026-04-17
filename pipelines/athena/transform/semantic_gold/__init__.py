"""Purpose: Semantic-gold parallel surface built from silver-first object models.
Inputs: Semantic contracts and transform entrypoints for player/team/game objects.
Outputs: Importable schemas, table specs, and semantic build scripts.
Next file: contracts.py defines the public table contract for semantic_gold v1.
"""

from .contracts import SEMANTIC_GOLD_TABLE_SPECS

__all__ = ["SEMANTIC_GOLD_TABLE_SPECS"]
