# BBR Bridge Remaining Ambiguous Rows

This document captures the remaining ambiguous rows in `silver/player_identity_bridge_bbr_nba_ambiguous` after the March 28, 2026 bridge refinements:

- suffix-preserving exact-name matching
- one-to-one BBR ownership resolution
- shared-name micro-bucket handling
- manual owner override for `Jaylin Williams -> 1631119`

If this file conflicts with the live parquet outputs, treat the parquet outputs as the source of truth.

Latest audited run:
- `s3://nba-analytics-lakehouse-dev/silver/_audit/player_identity_bridge_bbr_nba/run_date=2026-03-28/player_identity_bridge_bbr_nba_20260328T191644Z_a20caec9.json`

Current counts:
- matched: `4838`
- duplicate NBA rows: `170`
- ambiguous: `16`
- unmatched NBA: `1658`
- unmatched BBR: `564`

## Remaining Ambiguous Rows

| NBA person id | Name | BBR candidate ids | Current classification |
| --- | --- | --- | --- |
| `76610` | `Bob Duffy` | `duffybo01` | `shared_name_strongest_row_winner_loser:winner_bbr_id=duffybo01` |
| `76909` | `Matt Guokas` | `guokama01` | `manual_shared_name_collision` |
| `1538` | `Cedric Henderson` | `hendece02` | `shared_name_strongest_row_winner_loser:winner_bbr_id=hendece01` |
| `1114` | `Jaren Jackson` | `jacksja01` | `shared_name_strongest_row_winner_loser:winner_bbr_id=jacksja02` |
| `203187` | `Chris Johnson` | `johnsch04` | `manual_shared_name_collision` |
| `2256` | `Ken Johnson` | `johnske03` | `shared_name_strongest_row_winner_loser:winner_bbr_id=johnske01` |
| `1641794` | `Dillon Jones` | `jonesdi01` | raw weak-score single-candidate hold |
| `77818` | `Jim Paxson` | `paxsoji02`, `paxsoji01` | `shared_name_strongest_row_winner_loser:winner_bbr_id=paxsoji02` |
| `1631376` | `Dmytro Skapintsev` | `skapidm01` | raw weak-score single-candidate hold |
| `40043` | `Charles Smith` | `smithch04`, `smithch02`, `smithch01` | `manual_shared_name_collision` |
| `1630607` | `Chris Smith` | `smithch05` | `shared_name_strongest_row_winner_loser:winner_bbr_id=smithch05` |
| `78382` | `Jack Turner` | `turneja02` | `shared_name_strongest_row_winner_loser:winner_bbr_id=turneja01` |
| `1630314` | `Brandon Williams` | `willibr03`, `willibr01` | `shared_name_strongest_row_winner_loser:winner_bbr_id=willibr01` |
| `1642444` | `Jaylin Williams` | `willija07` | `shared_name_strongest_row_winner_loser:winner_bbr_id=willija07` |
| `1631466` | `Nate Williams` | `willina01`, `willije02` | `shared_name_strongest_row_winner_loser:winner_bbr_id=willina01` |
| `2826` | `Nate Williams` | `willina01`, `willije02` | `shared_name_strongest_row_winner_loser:winner_bbr_id=willina01` |

## Notes

- Rows labeled `shared_name_strongest_row_winner_loser:...` are leftover sibling rows after another NBA-side row with the same name won the BBR ownership claim.
- Rows labeled `manual_shared_name_collision` are true unresolved same-name collisions under the current bridge inputs.
- `Dillon Jones` and `Dmytro Skapintsev` are currently held because they remain weak-score single-candidate cases and were intentionally left out of this phase.
