<script lang="ts">
  import type { SortingState } from "$lib/table/tableModel";
  import { nextSortingState, renderArtifactTable } from "$lib/table/tableModel";
  import { columnAlignment, formatCellValue } from "$lib/table/format";
  import type { TableArtifact } from "./types";

  let { artifact }: { artifact: TableArtifact } = $props();
  let sorting = $state<SortingState>([]);
  const renderedTable = $derived(renderArtifactTable(artifact, sorting));

  function sortColumn(columnId: string) {
    sorting = nextSortingState(sorting, columnId);
  }
</script>

<article class="table-artifact">
  <div class="table-shell">
    <div class="table-frame" role="region" aria-label={artifact.title}>
      <table>
        <thead>
          <tr>
            {#each renderedTable.headers as header}
              <th class:align-right={columnAlignment(header.type) === "right"}>
                <button
                  class="column-button"
                  type="button"
                  disabled={!header.canSort}
                  aria-label={`Sort by ${header.label}`}
                  onclick={() => sortColumn(header.columnId)}
                >
                  <span>{header.label}</span>
                  <span class="sort-indicator" aria-hidden="true">
                    {header.sortDirection === "asc" ? "↑" : header.sortDirection === "desc" ? "↓" : "↕"}
                  </span>
                </button>
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each renderedTable.rows as row}
            <tr>
              {#each row.cells as cell}
                {@const column = artifact.columns.find((candidate) => candidate.id === cell.columnId)}
                <td class:align-right={columnAlignment(column?.type ?? "text") === "right"}>
                  {formatCellValue(cell.value, column?.type ?? "text")}
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="table-footer">
      <p class="row-count">
        Showing {artifact.displayed_row_count} of {artifact.row_count} rows
      </p>
    </div>
  </div>
</article>
