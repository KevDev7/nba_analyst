<script lang="ts">
  import { page } from "$app/state";
  import { askAssistant } from "$lib/api";
  import AnswerArtifact from "$lib/artifacts/AnswerArtifact.svelte";
  import ChartArtifact from "$lib/artifacts/ChartArtifact.svelte";
  import TableArtifact from "$lib/artifacts/TableArtifact.svelte";
  import type { Artifact } from "$lib/artifacts/types";
  import { assistantChatParts } from "$lib/chat/chatParts";
  import { maxQuestionChars } from "$lib/questionLimits";

  const questionCharLimit = maxQuestionChars();
  let question = $state("Show me the top 10 players by points over the last 10 games");
  let status = $state<"idle" | "loading" | "ready" | "error">("idle");
  let answer = $state("");
  let artifacts = $state<Artifact[]>([]);
  let error = $state("");
  let debugPayload = $state<Record<string, unknown> | null>(null);
  let submittedQuestion = $state("");
  let lastResetToken = $state<string | null>(null);
  const assistantParts = $derived(assistantChatParts(artifacts, answer, debugPayload));

  function resetChat() {
    question = "";
    status = "idle";
    answer = "";
    artifacts = [];
    error = "";
    debugPayload = null;
    submittedQuestion = "";
  }

  $effect(() => {
    const resetToken = page.url.searchParams.get("new");
    if (resetToken && resetToken !== lastResetToken) {
      lastResetToken = resetToken;
      resetChat();
    }
  });

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
        debug: false
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
          <p>Checking the numbers...</p>
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
    <article class="message assistant-message">
      <div class="message-avatar" aria-hidden="true">*</div>
      <div class="message-body assistant-response-stack">
        {#each assistantParts as part (part.id)}
          {#if part.kind === "answer"}
            <AnswerArtifact artifact={part.artifact} />
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
        {/each}
        {#if assistantParts.length === 0}
          <p class="empty">Your answer will appear here.</p>
        {/if}
      </div>
    </article>
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
        maxlength={questionCharLimit ?? undefined}
        rows="1"
        placeholder="Ask NBA Analyst..."
        onkeydown={submitOnEnter}
      ></textarea>
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
