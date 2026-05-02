<script lang="ts">
  import { textArtifactsOrFallback } from "./text";
  import type { Artifact } from "./types";
  import { isChartArtifact, isTableArtifact } from "./types";
  import TextArtifact from "./TextArtifact.svelte";
  import TableArtifact from "./TableArtifact.svelte";
  import ChartArtifact from "./ChartArtifact.svelte";

  let { artifacts = [], fallbackAnswer = "" }: { artifacts?: Artifact[]; fallbackAnswer?: string } = $props();

  const textArtifacts = $derived(textArtifactsOrFallback(artifacts, fallbackAnswer));
  const chartArtifacts = $derived(artifacts.filter(isChartArtifact));
  const tableArtifacts = $derived(artifacts.filter(isTableArtifact));
</script>

{#if textArtifacts.length === 0 && chartArtifacts.length === 0 && tableArtifacts.length === 0}
  <p class="empty">Your answer will appear here.</p>
{:else}
  <div class="artifact-stack">
    {#each textArtifacts as artifact}
      <TextArtifact {artifact} />
    {/each}

    {#each chartArtifacts as artifact}
      <ChartArtifact {artifact} />
    {/each}

    {#each tableArtifacts as artifact}
      <TableArtifact {artifact} />
    {/each}
  </div>
{/if}
