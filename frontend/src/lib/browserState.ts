/** sessionStorage key holding the batch id of an unfinished wardrobe upload. */
export const ACTIVE_INGESTION_BATCH_KEY = 'active_ingestion_batch_id';

/** Drop one query parameter from the address bar without adding a history entry. */
export function removeUrlParam(name: string): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  if (!params.has(name)) return;
  params.delete(name);
  const rest = params.toString();
  window.history.replaceState(null, '', `${window.location.pathname}${rest ? `?${rest}` : ''}`);
}
