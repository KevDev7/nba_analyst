export function maxQuestionChars(): number | undefined {
  const rawLimit = import.meta.env.PUBLIC_MAX_QUESTION_CHARS?.trim() || "";
  if (!rawLimit) {
    return undefined;
  }

  if (!/^\d+$/.test(rawLimit)) {
    return undefined;
  }

  const parsedLimit = Number.parseInt(rawLimit, 10);
  if (!Number.isFinite(parsedLimit) || parsedLimit < 1) {
    return undefined;
  }

  return parsedLimit;
}
