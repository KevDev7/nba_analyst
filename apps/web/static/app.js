const form = document.querySelector("#chat-form");
const questionInput = document.querySelector("#question");
const debugInput = document.querySelector("#debug");
const submitButton = document.querySelector("#submit");
const statusLabel = document.querySelector("#status");
const answerOutput = document.querySelector("#answer");
const errorOutput = document.querySelector("#error");
const debugDetails = document.querySelector("#debug-details");
const debugOutput = document.querySelector("#debug-output");

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  statusLabel.textContent = isLoading ? "Thinking" : "Idle";
  document.body.classList.toggle("is-loading", isLoading);
}

function showError(message) {
  answerOutput.textContent = "";
  errorOutput.hidden = false;
  errorOutput.textContent = message;
  statusLabel.textContent = "Error";
}

function showAnswer(payload) {
  errorOutput.hidden = true;
  errorOutput.textContent = "";
  answerOutput.textContent = payload.answer || "";
  statusLabel.textContent = "Ready";

  if (payload.debug) {
    debugDetails.hidden = false;
    debugOutput.textContent = JSON.stringify(payload.debug, null, 2);
  } else {
    debugDetails.hidden = true;
    debugOutput.textContent = "";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const question = questionInput.value.trim();
  if (!question) {
    showError("Question is required.");
    return;
  }

  setLoading(true);
  answerOutput.textContent = "Running the semantic pipeline...";
  errorOutput.hidden = true;
  debugDetails.hidden = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        debug: debugInput.checked,
      }),
    });
    const payload = await response.json();
    if (!payload.ok) {
      showError(payload.error || "The assistant could not answer this question.");
      return;
    }
    showAnswer(payload);
  } catch (error) {
    showError(error instanceof Error ? error.message : String(error));
  } finally {
    setLoading(false);
  }
});
