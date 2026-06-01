// Maps backend question_number ("P1-N" / "QN") to the positional answer-map
// key the save endpoint expects ("p1_(N-1)" / "question_(N-1)").
export function answerKeyForDisplayId(rawId: string | undefined | null): string | null {
  const target = (rawId || '').trim().toLowerCase();
  if (!target) return null;
  if (target.startsWith('p1-')) {
    const n = parseInt(target.slice(3), 10);
    return Number.isFinite(n) && n >= 1 ? `p1_${n - 1}` : null;
  }
  if (target.startsWith('q')) {
    const n = parseInt(target.slice(1), 10);
    return Number.isFinite(n) && n >= 1 ? `question_${n - 1}` : null;
  }
  return null;
}
