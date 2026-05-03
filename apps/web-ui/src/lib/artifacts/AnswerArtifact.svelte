<script lang="ts">
  import type { AnswerArtifact } from "$lib/chat/chatParts";

  let { artifact }: { artifact: AnswerArtifact } = $props();
</script>

<article class="answer-artifact">
  {#if artifact.interpretation}
    <p class="answer-interpretation">{artifact.interpretation.text}</p>
  {/if}

  {#if artifact.summary}
    <p class="answer-summary">{artifact.summary.text}</p>
  {/if}

  {#if artifact.assumptions?.items?.length}
    <div class="answer-assumptions">
      <p class="label">Assumptions</p>
      <ul>
        {#each artifact.assumptions.items as item}
          <li>{item}</li>
        {/each}
      </ul>
    </div>
  {:else if artifact.assumptions?.text}
    <div class="answer-assumptions">
      <p class="label">Assumptions</p>
      <p>{artifact.assumptions.text}</p>
    </div>
  {/if}
</article>
