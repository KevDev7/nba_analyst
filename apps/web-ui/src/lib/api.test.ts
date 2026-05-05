import { afterEach, describe, expect, it, vi } from "vitest";

import { askAssistant, assistantApiUrl } from "./api";

describe("assistantApiUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses the local dev proxy path when no public API base URL is configured", () => {
    expect(assistantApiUrl()).toBe("/api/chat");
  });

  it("prefixes deployed requests with the configured public API base URL", () => {
    vi.stubEnv("PUBLIC_API_BASE_URL", "https://nba-analyst-api.onrender.com/");

    expect(assistantApiUrl()).toBe("https://nba-analyst-api.onrender.com/api/chat");
    expect(assistantApiUrl("healthz")).toBe("https://nba-analyst-api.onrender.com/healthz");
  });
});

describe("askAssistant", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("posts chat requests to the assistant API endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, answer: "Answer", artifacts: [] })
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(askAssistant({ question: "top teams", debug: false })).resolves.toEqual({
      ok: true,
      answer: "Answer",
      artifacts: []
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: "top teams", debug: false })
      })
    );
  });

  it("posts chat requests to the deployed assistant API when configured", async () => {
    vi.stubEnv("PUBLIC_API_BASE_URL", "https://nba-analyst-api.onrender.com");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, answer: "Answer", artifacts: [] })
    });
    vi.stubGlobal("fetch", fetchMock);

    await askAssistant({ question: "top teams", debug: false });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://nba-analyst-api.onrender.com/api/chat",
      expect.any(Object)
    );
  });
});
