import type { ChatRequest, ChatResponse } from "./artifacts/types";

export async function askAssistant(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    throw new Error(`Assistant API returned ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}
