import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_MAX_QUESTION_CHARS, maxQuestionChars } from "./questionLimits";

describe("maxQuestionChars", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to the public beta question limit", () => {
    expect(maxQuestionChars()).toBe(DEFAULT_MAX_QUESTION_CHARS);
  });

  it("uses a positive integer public build-time override", () => {
    vi.stubEnv("PUBLIC_MAX_QUESTION_CHARS", "100");

    expect(maxQuestionChars()).toBe(100);
  });

  it("ignores invalid overrides", () => {
    for (const value of ["", "0", "-1", "abc", "12abc", "1.5"]) {
      vi.stubEnv("PUBLIC_MAX_QUESTION_CHARS", value);

      expect(maxQuestionChars()).toBe(DEFAULT_MAX_QUESTION_CHARS);
    }
  });
});
