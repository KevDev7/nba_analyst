<script lang="ts">
  import { askAssistant } from "$lib/api";
  import ArtifactRenderer from "$lib/artifacts/ArtifactRenderer.svelte";
  import type { Artifact } from "$lib/artifacts/types";
  import "$lib/styles.css";

  let question = $state("Show me the top 10 players by points over the last 10 games");
  let debug = $state(false);
  let status = $state<"idle" | "loading" | "ready" | "error">("idle");
  let answer = $state("");
  let artifacts = $state<Artifact[]>([]);
  let error = $state("");
  let debugPayload = $state<Record<string, unknown> | null>(null);

  async function submitQuestion() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      status = "error";
      error = "Question is required.";
      answer = "";
      artifacts = [];
      debugPayload = null;
      return;
    }

    status = "loading";
    error = "";
    answer = "";
    artifacts = [];
    debugPayload = null;

    try {
      const response = await askAssistant({
        question: trimmedQuestion,
        debug
      });

      if (!response.ok) {
        status = "error";
        error = response.error || "The assistant could not answer this question.";
        return;
      }

      status = "ready";
      answer = response.answer || "";
      artifacts = response.artifacts || [];
      debugPayload = response.debug || null;
    } catch (caught) {
      status = "error";
      error = caught instanceof Error ? caught.message : String(caught);
    }
  }
</script>

<svelte:head>
  <title>NBA Analyst</title>
  <meta
    name="description"
    content="Local NBA analytics assistant rendered with structured answer artifacts."
  />
</svelte:head>

<main class="shell">
  <section class="hero">
    <p class="hero-kicker">Structured artifact UI</p>
    <h1>Ask the NBA analyst</h1>
    <p class="lede">
      Type one analytics question. SvelteKit sends it through the existing FastAPI assistant API and renders
      the returned text and table artifacts.
    </p>
  </section>

  <section class="panel question-panel" aria-labelledby="question-title">
    <div>
      <p class="section-kicker">Question</p>
      <h2 id="question-title">One prompt, one grounded answer</h2>
    </div>

    <form
      onsubmit={(event) => {
        event.preventDefault();
        void submitQuestion();
      }}
    >
      <label class="sr-only" for="question">NBA analytics question</label>
      <textarea
        id="question"
        bind:value={question}
        rows="4"
        placeholder="Show me the top 10 players by points over the last 10 games"
      ></textarea>

      <div class="controls">
        <label class="debug-toggle">
          <input bind:checked={debug} type="checkbox" />
          Show debug details
        </label>
        <button disabled={status === "loading"} type="submit">
          {status === "loading" ? "Thinking..." : "Ask analyst"}
        </button>
      </div>
    </form>
  </section>

  <section class="panel output-panel" aria-live="polite">
    <div class="output-header">
      <div>
        <p class="section-kicker">Response</p>
        <h2>Artifact render</h2>
      </div>
      <span class:loading={status === "loading"} class:error-state={status === "error"} class="status">
        {status === "loading" ? "Thinking" : status === "ready" ? "Ready" : status === "error" ? "Error" : "Idle"}
      </span>
    </div>

    {#if status === "loading"}
      <div class="loading-card">
        <div class="pulse"></div>
        <p>Running semantic interpretation, Haskell grounding, runtime execution, and answer synthesis.</p>
      </div>
    {:else if error}
      <pre class="error">{error}</pre>
    {:else}
      <ArtifactRenderer {artifacts} fallbackAnswer={answer} />
    {/if}

    {#if debugPayload}
      <details class="debug-panel">
        <summary>Debug payload</summary>
        <pre>{JSON.stringify(debugPayload, null, 2)}</pre>
      </details>
    {/if}
  </section>
</main>
