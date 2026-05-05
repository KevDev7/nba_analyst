export const DEFAULT_MAX_QUESTION_CHARS = 250;

export function maxQuestionChars(): number {
  const rawLimit = import.meta.env.PUBLIC_MAX_QUESTION_CHARS?.trim() || "";
  if (!rawLimit) {
    return DEFAULT_MAX_QUESTION_CHARS;
  }

  if (!/^\d+$/.test(rawLimit)) {
    return DEFAULT_MAX_QUESTION_CHARS;
  }

  const parsedLimit = Number.parseInt(rawLimit, 10);
  if (!Number.isFinite(parsedLimit) || parsedLimit < 1) {
    return DEFAULT_MAX_QUESTION_CHARS;
  }

  return parsedLimit;
}
