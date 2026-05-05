<script lang="ts">
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import ChevronsLeft from "@lucide/svelte/icons/chevrons-left";
  import ChevronsRight from "@lucide/svelte/icons/chevrons-right";
  import { Button } from "$lib/components/ui/button";
  import * as Table from "$lib/components/ui/table";
  import type { PaginationState, SortingState } from "$lib/table/tableModel";
  import { nextSortingState, renderArtifactTable, TABLE_PAGE_SIZE } from "$lib/table/tableModel";
  import { columnAlignment, formatCellValue } from "$lib/table/format";
  import type { TableArtifact } from "./types";

  let { artifact }: { artifact: TableArtifact } = $props();
  let sorting = $state<SortingState>([]);
  let pagination = $state<PaginationState>({ pageIndex: 0, pageSize: TABLE_PAGE_SIZE });
  const renderedTable = $derived(renderArtifactTable(artifact, sorting, pagination));

  function sortColumn(columnId: string) {
    sorting = nextSortingState(sorting, columnId);
    pagination = { ...pagination, pageIndex: 0 };
  }

  function setPageIndex(pageIndex: number) {
    pagination = { ...pagination, pageIndex };
  }

  function previousPage() {
    setPageIndex(Math.max(renderedTable.pagination.pageIndex - 1, 0));
  }

  function nextPage() {
    setPageIndex(Math.min(renderedTable.pagination.pageIndex + 1, renderedTable.pagination.pageCount - 1));
  }

  function rowLabel(count: number) {
    return `${count} ${count === 1 ? "row" : "rows"}`;
  }
</script>

<article class="table-artifact">
  <div class="bg-white">
    <div class="overflow-x-auto" role="region" aria-label={artifact.title}>
      <Table.Root class="min-w-[680px]">
        <Table.Header class="bg-sky-50">
          <Table.Row class="hover:bg-sky-50">
            {#each renderedTable.headers as header}
              <Table.Head class={columnAlignment(header.type) === "right" ? "text-right text-slate-700" : "text-slate-700"}>
                <button
                  class="flex h-10 w-full min-h-0 items-center gap-2 rounded-none bg-transparent p-0 text-left text-sm font-medium text-slate-700 transition-colors hover:bg-transparent hover:text-sky-700 disabled:pointer-events-none disabled:bg-transparent disabled:text-slate-700 disabled:opacity-100 data-[align=right]:justify-end data-[align=right]:text-right"
                  data-align={columnAlignment(header.type) === "right" ? "right" : "left"}
                  type="button"
                  disabled={!header.canSort}
                  aria-label={`Sort by ${header.label}`}
                  onclick={() => sortColumn(header.columnId)}
                >
                  <span>{header.label}</span>
                  <span class="ml-auto text-xs text-slate-400 data-[align=right]:ml-0" data-align={columnAlignment(header.type) === "right" ? "right" : "left"} aria-hidden="true">
                    {header.sortDirection === "asc" ? "↑" : header.sortDirection === "desc" ? "↓" : "↕"}
                  </span>
                </button>
              </Table.Head>
            {/each}
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {#each renderedTable.rows as row}
            <Table.Row class="hover:bg-sky-50/70">
              {#each row.cells as cell}
                {@const column = artifact.columns.find((candidate) => candidate.id === cell.columnId)}
                <Table.Cell class={columnAlignment(column?.type ?? "text") === "right" ? "text-right text-slate-700" : "text-slate-700"}>
                  {formatCellValue(cell.value, column?.type ?? "text")}
                </Table.Cell>
              {/each}
            </Table.Row>
          {/each}
        </Table.Body>
      </Table.Root>
    </div>
    <div class="flex flex-col gap-4 border-t border-sky-100 bg-white px-4 py-4 md:flex-row md:items-center md:justify-between">
      <div class="flex items-center gap-1 text-muted-foreground text-sm whitespace-nowrap">
        {#if renderedTable.pagination.needsPagination}
          <span>Rows per page:</span>
          <span class="text-foreground">{renderedTable.pagination.pageSize}</span>
        {:else}
          <span>{rowLabel(renderedTable.pagination.rowCount)}</span>
        {/if}
      </div>
      {#if renderedTable.pagination.needsPagination}
        <div class="flex items-center gap-4" aria-label="Table pagination">
          <p class="page-count text-muted-foreground text-sm whitespace-nowrap">
            Page {renderedTable.pagination.pageIndex + 1} of {renderedTable.pagination.pageCount}
          </p>
          <div class="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon-sm"
              class="border-sky-100 text-slate-500 hover:bg-sky-50 hover:text-sky-700 disabled:bg-sky-50 disabled:text-slate-300"
              type="button"
              aria-label="First page"
              disabled={!renderedTable.pagination.canPreviousPage}
              onclick={() => setPageIndex(0)}
            >
              <ChevronsLeft class="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              class="border-sky-100 text-slate-500 hover:bg-sky-50 hover:text-sky-700 disabled:bg-sky-50 disabled:text-slate-300"
              type="button"
              aria-label="Previous page"
              disabled={!renderedTable.pagination.canPreviousPage}
              onclick={previousPage}
            >
              <ChevronLeft class="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              class="border-sky-100 text-slate-500 hover:bg-sky-50 hover:text-sky-700 disabled:bg-sky-50 disabled:text-slate-300"
              type="button"
              aria-label="Next page"
              disabled={!renderedTable.pagination.canNextPage}
              onclick={nextPage}
            >
              <ChevronRight class="size-4" />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              class="border-sky-100 text-slate-500 hover:bg-sky-50 hover:text-sky-700 disabled:bg-sky-50 disabled:text-slate-300"
              type="button"
              aria-label="Last page"
              disabled={!renderedTable.pagination.canNextPage}
              onclick={() => setPageIndex(renderedTable.pagination.pageCount - 1)}
            >
              <ChevronsRight class="size-4" />
            </Button>
          </div>
        </div>
      {/if}
    </div>
  </div>
</article>
