/** "Look 01", "Look 02"… — the outfit title used across the app. */
export function formatLookNumber(rank: number): string {
  return `Look ${String(rank).padStart(2, '0')}`;
}
