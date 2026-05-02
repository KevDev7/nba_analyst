<script lang="ts">
  import { askAssistant } from "$lib/api";
  import ChartArtifact from "$lib/artifacts/ChartArtifact.svelte";
  import TableArtifact from "$lib/artifacts/TableArtifact.svelte";
  import TextArtifact from "$lib/artifacts/TextArtifact.svelte";
  import type { Artifact } from "$lib/artifacts/types";
  import { assistantChatParts } from "$lib/chat/chatParts";
  import "@fontsource/cormorant-garamond/500.css";
  import "@fontsource/inter/400.css";
  import "@fontsource/inter/500.css";
  import "@fontsource/jetbrains-mono/400.css";
  import "$lib/styles.css";

  let question = $state("Show me the top 10 players by points over the last 10 games");
  let debug = $state(false);
  let status = $state<"idle" | "loading" | "ready" | "error">("idle");
  let answer = $state("");
  let artifacts = $state<Artifact[]>([]);
  let error = $state("");
  let debugPayload = $state<Record<string, unknown> | null>(null);
  let submittedQuestion = $state("");
  const assistantParts = $derived(assistantChatParts(artifacts, answer, debugPayload));

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
    submittedQuestion = trimmedQuestion;

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

  function submitOnEnter(event: KeyboardEvent) {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    event.preventDefault();
    void submitQuestion();
  }
</script>

<svelte:head>
  <title>NBA Analyst</title>
  <meta
    name="description"
    content="Local NBA analytics assistant rendered with structured answer artifacts."
  />
</svelte:head>

<main class="chat-shell">
  <aside class="sidebar" aria-label="NBA Analyst navigation">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">*</span>
      <span>NBA Analyst</span>
    </a>

    <button
      type="button"
      class="sidebar-action"
      onclick={() => {
        question = "";
        status = "idle";
        answer = "";
        artifacts = [];
        error = "";
        debugPayload = null;
        submittedQuestion = "";
      }}
    >
      New chat
    </button>

    <nav class="sidebar-section" aria-label="Chats">
      <p class="sidebar-label">Chats</p>
      <a class="chat-link active" href="/">Current chat</a>
    </nav>
  </aside>

  <header class="mobile-topbar" aria-label="NBA Analyst">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">*</span>
      <span>NBA Analyst</span>
    </a>
    <span class:loading={status === "loading"} class:error-state={status === "error"} class="status">
      {status === "loading" ? "Thinking" : status === "ready" ? "Ready" : status === "error" ? "Error" : "Idle"}
    </span>
  </header>

  <section class="chat-thread" aria-live="polite" aria-label="NBA Analyst conversation">
    {#if submittedQuestion}
      <article class="message user-message">
        <div class="message-body">
          <p>{submittedQuestion}</p>
        </div>
      </article>
    {/if}

    {#if status === "loading"}
      <article class="message assistant-message">
        <div class="message-avatar" aria-hidden="true">*</div>
        <div class="message-body">
          <div class="loading-card">
            <div class="pulse"></div>
            <p>Working through semantic interpretation, grounding, execution, and answer synthesis.</p>
          </div>
        </div>
      </article>
    {:else if error}
      <article class="message assistant-message">
        <div class="message-avatar" aria-hidden="true">*</div>
        <div class="message-body">
          <pre class="error">{error}</pre>
        </div>
      </article>
    {:else if status === "ready"}
      {#each assistantParts as part (part.id)}
        <article class="message assistant-message">
          <div class="message-avatar" aria-hidden="true">*</div>
          <div class="message-body">
            {#if part.kind === "text"}
              <TextArtifact artifact={part.artifact} />
            {:else if part.kind === "chart"}
              <ChartArtifact artifact={part.artifact} />
            {:else if part.kind === "table"}
              <TableArtifact artifact={part.artifact} />
            {:else}
              <details class="debug-panel debug-artifact">
                <summary>Debug payload</summary>
                <pre>{JSON.stringify(part.payload, null, 2)}</pre>
              </details>
            {/if}
          </div>
        </article>
      {/each}
      {#if assistantParts.length === 0}
        <article class="message assistant-message">
          <div class="message-avatar" aria-hidden="true">*</div>
          <div class="message-body">
            <p class="empty">Your answer will appear here.</p>
          </div>
        </article>
      {/if}
    {/if}
  </section>

  <section class="composer-shell" aria-label="Ask NBA Analyst">
    <form
      class="composer"
      onsubmit={(event) => {
        event.preventDefault();
        void submitQuestion();
      }}
    >
      <div class="composer-input-row">
        <label class="sr-only" for="question">NBA analytics question</label>
        <textarea
          id="question"
          bind:value={question}
          rows="2"
          placeholder="Ask NBA Analyst..."
          onkeydown={submitOnEnter}
        ></textarea>
      </div>

      <div class="composer-footer">
        <label class="debug-toggle">
          <input bind:checked={debug} type="checkbox" />
          Show debug details
        </label>
        <button class="send-button" disabled={status === "loading"} aria-label="Ask NBA Analyst" type="submit">
          {#if status === "loading"}
            <span aria-hidden="true">...</span>
          {:else}
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M4 19L20 12L4 5V10L14 12L4 14V19Z" />
            </svg>
          {/if}
        </button>
      </div>
    </form>
  </section>
</main>
