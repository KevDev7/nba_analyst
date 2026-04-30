# Batch 95

Fixed semantic-gold team-game and team-season runtime source completeness.

The public semantic contract already exposed rich team-game and team-season
boxscore measures, but the runtime S3 reads were using the narrower legacy gold
`fct_team_game` source column list. That meant generated semantic outputs could
leave fields such as assists, rebounds, shooting attempts, turnovers, fouls, and
related derived rates null or zero even though `silver/boxscore_team_game`
contained the data.

Updated:

- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_team_parquet.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`

Notes:

- `semantic_gold.team_game` now owns a rich semantic source column contract for
  `silver/boxscore_team_game.parquet` instead of borrowing the minimal legacy
  gold fact read list.
- `semantic_gold.team_season` and player semantic transforms that build
  team-game context now reuse the semantic-owned team-game source contract.
- This is not a public schema expansion. It fills existing semantic contract
  fields with source data that was already present in silver.
- A focused test now selects the fixture team-game table down to the runtime
  required columns and verifies representative semantic measures still populate.

Expected downstream propagation:

- rebuild `semantic_gold.team_game`
- rebuild `semantic_gold.team_season`
- redeploy semantic-gold Athena tables
- rebuild the local DuckDB semantic snapshot
- regenerate value aliases and ontology artifacts if the snapshot-backed
  artifacts are being refreshed

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
