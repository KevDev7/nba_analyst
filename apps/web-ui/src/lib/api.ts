import { env } from "$env/dynamic/public";
import type { ChatRequest, ChatResponse } from "./artifacts/types";

export function assistantApiUrl(path: string = "/api/chat"): string {
  const apiBaseUrl = (env.PUBLIC_API_BASE_URL || import.meta.env.PUBLIC_API_BASE_URL || "").replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiBaseUrl}${normalizedPath}`;
}

export async function askAssistant(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(assistantApiUrl(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    throw new Error(`Assistant API returned ${response.status}`);
  }

  return (await response.json()) as ChatResponse;
}
