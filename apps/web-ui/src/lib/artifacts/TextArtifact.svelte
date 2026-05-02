<script lang="ts">
  import type { TextArtifact } from "./types";

  let { artifact }: { artifact: TextArtifact } = $props();
</script>

<article class="text-artifact" data-role={artifact.role}>
  {#if artifact.role === "interpretation"}
    <p class="eyebrow">{artifact.text}</p>
  {:else if artifact.items?.length}
    <div class="label">{artifact.role}</div>
    <ul>
      {#each artifact.items as item}
        <li>{item}</li>
      {/each}
    </ul>
  {:else}
    <p>{artifact.text}</p>
  {/if}
</article>
