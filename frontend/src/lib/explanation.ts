export interface ExplanationPart {
  text: string;
  isItem: boolean;
}

/**
 * Split a recommendation explanation into plain text and garment names.
 * The API marks each garment as `[name]` (MULTI_AGENT_SPEC.md section 7, checked by the
 * benchmark); the UI shows the name without the brackets.
 */
export function splitExplanation(text: string): ExplanationPart[] {
  const parts: ExplanationPart[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[([^[\]]+)\]/g)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ text: text.slice(last, start), isItem: false });
    parts.push({ text: match[1].trim(), isItem: true });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), isItem: false });
  return parts;
}
