import type {
  ApiSuccessResponse,
  ConfirmBatchPayload,
  ConfirmBatchResponse,
  IngestionBatchReviewResponse,
  UploadBatchResponse,
} from '@/types/ingestion';
import type {
  PreferenceOptions,
  PreferenceSelections,
  UserProfile,
} from '@/types/profile';
import type {
  StylistChatRequest,
  StylistChatResponseData,
} from '@/types/chat';
import type {
  BookmarkRequest,
  BookmarkResponseData,
  OutfitDetailResponseData,
  OutfitRatingRequest,
  OutfitRatingResponseData,
  OutfitWornRequest,
  OutfitWornResponseData,
  SavedOutfitsResponseData,
} from '@/types/outfits';
import type {
  DismissPromptRequest,
  DismissPromptResponseData,
} from '@/types/feedback';
import type { TryOnResponseData } from '@/types/tryons';
import type {
  WardrobeItem,
  WardrobeItemListResponse,
  WardrobeItemUpdatePayload,
  WardrobeItemDeleteResponse,
} from '@/types/wardrobe';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const USER_STORAGE_KEY = 'fashion_stylist_user_id';
const SESSION_STORAGE_KEY = 'fashion_stylist_session_id';

let memoryUserId: string | null = null;
let memorySessionId: string | null = null;

/**
 * Get or generate a persistent demo user ID for cross-request session tracking.
 * Gracefully falls back to an in-memory UUID if localStorage is disabled or throws (e.g. Private Browsing).
 */
export function getStoredUserId(): string {
  if (typeof window === 'undefined') {
    return '00000000-0000-0000-0000-000000000001';
  }
  try {
    let userId = localStorage.getItem(USER_STORAGE_KEY);
    if (!userId) {
      userId = crypto.randomUUID();
      localStorage.setItem(USER_STORAGE_KEY, userId);
    }
    return userId;
  } catch {
    if (!memoryUserId) {
      memoryUserId = crypto.randomUUID();
    }
    return memoryUserId;
  }
}

export function setStoredUserId(id: string): void {
  memoryUserId = id;
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(USER_STORAGE_KEY, id);
    } catch {
      // Storage unavailable or blocked
    }
  }
}

/**
 * Get or generate an opaque client session ID stored in sessionStorage (per-tab/session lifecycle).
 * Gracefully falls back to an in-memory UUID if sessionStorage is disabled or throws (e.g. Private Browsing).
 */
export function getStoredSessionId(): string {
  if (typeof window === 'undefined') {
    return '00000000-0000-0000-0000-000000000000';
  }
  try {
    let sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
    return sessionId;
  } catch {
    if (!memorySessionId) {
      memorySessionId = crypto.randomUUID();
    }
    return memorySessionId;
  }
}

export function setStoredSessionId(id: string): void {
  memorySessionId = id;
  if (typeof window !== 'undefined') {
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, id);
    } catch {
      // Storage unavailable or blocked
    }
  }
}

const FEEDBACK_SUPPRESSED_PREFIX = 'fashion_stylist_feedback_suppressed_';
const memorySuppressedSessions = new Set<string>();

export function isSessionFeedbackSuppressed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const sessionId = getStoredSessionId();
    if (memorySuppressedSessions.has(sessionId)) {
      return true;
    }
    return sessionStorage.getItem(`${FEEDBACK_SUPPRESSED_PREFIX}${sessionId}`) === 'true';
  } catch {
    const sessionId = getStoredSessionId();
    return memorySuppressedSessions.has(sessionId);
  }
}

export function setSessionFeedbackSuppressed(): void {
  if (typeof window === 'undefined') return;
  const sessionId = getStoredSessionId();
  memorySuppressedSessions.add(sessionId);
  try {
    sessionStorage.setItem(`${FEEDBACK_SUPPRESSED_PREFIX}${sessionId}`, 'true');
  } catch {
    // Storage restricted or unavailable - in-memory fallback preserved
  }
}

export function clearMemorySuppressedSessionsForTesting(): void {
  memorySuppressedSessions.clear();
}

export class ApiError extends Error {
  code: string;
  details?: unknown;
  status: number;

  constructor(message: string, code = 'UNKNOWN_ERROR', status = 500, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new ApiError('Máy chủ trả về phản hồi không hợp lệ.', 'INVALID_RESPONSE', response.status);
  }

  if (!response.ok) {
    const errorObj = (json as { error?: { message?: string; code?: string; details?: unknown } })?.error;
    const message = errorObj?.message || 'Có lỗi xảy ra khi gọi dịch vụ.';
    const code = errorObj?.code || `HTTP_${response.status}`;
    throw new ApiError(message, code, response.status, errorObj?.details);
  }

  return (json as ApiSuccessResponse<T>).data;
}

/**
 * Robust fetch wrapper ensuring all network dropouts and errors surface as typed ApiError.
 */
async function apiFetch<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw err;
    }
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(
      'Không thể kết nối đến máy chủ. Vui lòng kiểm tra kết nối mạng.',
      'NETWORK_ERROR',
      0,
      err
    );
  }
  return handleResponse<T>(response);
}

/**
 * Upload 1–10 images for garment digitization (POST /api/v1/ingestions)
 */
export async function uploadIngestionImages(
  files: File[],
  declaredKind?: string
): Promise<UploadBatchResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('images[]', file);
  }
  if (declaredKind) {
    formData.append('declared_input_kind', declaredKind);
  }

  const userId = getStoredUserId();
  return apiFetch<UploadBatchResponse>(`${API_BASE_URL}/api/v1/ingestions`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: formData,
  });
}

/**
 * Retrieve ingestion review state, bounding boxes, crops, and attributes (GET /api/v1/ingestions/{batch_id})
 */
export async function getIngestionBatch(batchId: string): Promise<IngestionBatchReviewResponse> {
  const userId = getStoredUserId();
  return apiFetch<IngestionBatchReviewResponse>(`${API_BASE_URL}/api/v1/ingestions/${batchId}`, {
    method: 'GET',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Confirm accepted detections with customized fashion attributes (POST /api/v1/ingestions/{batch_id}/confirm)
 */
export async function confirmIngestionBatch(
  batchId: string,
  payload: ConfirmBatchPayload
): Promise<ConfirmBatchResponse> {
  const userId = getStoredUserId();
  return apiFetch<ConfirmBatchResponse>(`${API_BASE_URL}/api/v1/ingestions/${batchId}/confirm`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Cancel an unconfirmed batch and clean up transient assets (DELETE /api/v1/ingestions/{batch_id})
 */
export async function deleteIngestionBatch(batchId: string): Promise<{ batch_id: string; status: string }> {
  const userId = getStoredUserId();
  return apiFetch<{ batch_id: string; status: string }>(`${API_BASE_URL}/api/v1/ingestions/${batchId}`, {
    method: 'DELETE',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
  });
}

/**
 * Get media image URL with authentication header proxy or direct backend URL
 */
export function getMediaUrl(relativeOrAssetUrl: string): string {
  if (!relativeOrAssetUrl) return '';
  if (relativeOrAssetUrl.startsWith('http://') || relativeOrAssetUrl.startsWith('https://')) {
    return relativeOrAssetUrl;
  }
  const cleanPath = relativeOrAssetUrl.startsWith('/') ? relativeOrAssetUrl : `/${relativeOrAssetUrl}`;
  return `${API_BASE_URL}${cleanPath}`;
}

export async function getUserProfile(): Promise<UserProfile> {
  return apiFetch<UserProfile>(`${API_BASE_URL}/api/v1/user/profile`, {
    headers: { 'X-User-Id': getStoredUserId() },
  });
}

export async function getPreferenceOptions(): Promise<PreferenceOptions> {
  return apiFetch<PreferenceOptions>(`${API_BASE_URL}/api/v1/user/profile/preference-options`, {
    headers: { 'X-User-Id': getStoredUserId() },
  });
}

export async function replaceUserPreferences(
  preferences: PreferenceSelections
): Promise<UserProfile> {
  return apiFetch<UserProfile>(`${API_BASE_URL}/api/v1/user/profile/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
    },
    body: JSON.stringify(preferences),
  });
}

/**
 * Execute AI stylist chat recommendation pipeline (POST /api/v1/stylist/chat)
 */
export async function sendStylistChat(
  payload: StylistChatRequest
): Promise<StylistChatResponseData> {
  const sessionId = payload.client_session_id || getStoredSessionId();
  const bodyPayload: StylistChatRequest = {
    ...payload,
    client_session_id: sessionId,
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-User-Id': getStoredUserId(),
    'X-Client-Session-Id': sessionId,
  };
  if (payload.idempotency_key) {
    headers['X-Idempotency-Key'] = payload.idempotency_key;
  }

  return apiFetch<StylistChatResponseData>(`${API_BASE_URL}/api/v1/stylist/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify(bodyPayload),
  });
}

/**
 * Retrieve detailed outfit recommendation with items and wear/rating history (GET /api/v1/outfits/{outfit_id})
 */
export async function getOutfitDetail(
  outfitId: string
): Promise<OutfitDetailResponseData> {
  return apiFetch<OutfitDetailResponseData>(`${API_BASE_URL}/api/v1/outfits/${encodeURIComponent(outfitId)}`, {
    method: 'GET',
    headers: {
      'X-User-Id': getStoredUserId(),
    },
  });
}

/**
 * Retrieve paginated saved / bookmarked outfits (GET /api/v1/outfits/saved)
 * Strictly matches API Contract parameters: page (ge=1) and page_size (1..50).
 */
export async function getSavedOutfits(
  params?: { page?: number; page_size?: number }
): Promise<SavedOutfitsResponseData> {
  const searchParams = new URLSearchParams();
  if (params?.page !== undefined) {
    searchParams.set('page', String(params.page));
  }
  if (params?.page_size !== undefined) {
    searchParams.set('page_size', String(params.page_size));
  }
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';

  return apiFetch<SavedOutfitsResponseData>(`${API_BASE_URL}/api/v1/outfits/saved${query}`, {
    method: 'GET',
    headers: {
      'X-User-Id': getStoredUserId(),
    },
  });
}

/**
 * Toggle bookmark flag on an outfit (PUT /api/v1/outfits/{outfit_id}/bookmark)
 * Strictly matches API Contract HTTP method: PUT.
 */
export async function setOutfitBookmark(
  outfitId: string,
  isBookmarked: boolean
): Promise<BookmarkResponseData> {
  const payload: BookmarkRequest = { is_bookmarked: isBookmarked };
  return apiFetch<BookmarkResponseData>(`${API_BASE_URL}/api/v1/outfits/${encodeURIComponent(outfitId)}/bookmark`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Record user-confirmed wear action with idempotency key (POST /api/v1/outfits/{outfit_id}/worn)
 */
export async function recordOutfitWorn(
  outfitId: string,
  payload: OutfitWornRequest
): Promise<OutfitWornResponseData> {
  return apiFetch<OutfitWornResponseData>(`${API_BASE_URL}/api/v1/outfits/${encodeURIComponent(outfitId)}/worn`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Submit outfit star rating (PUT /api/v1/outfits/{outfit_id}/rating)
 * Every successful rating suppresses proactive prompts for the remainder of the
 * current browser session, including ratings submitted manually from a card.
 */
export async function rateOutfit(
  outfitId: string,
  payload: OutfitRatingRequest
): Promise<OutfitRatingResponseData> {
  const sessionId = payload.client_session_id ?? getStoredSessionId();
  const bodyPayload: OutfitRatingRequest = {
    ...payload,
    ...(sessionId ? { client_session_id: sessionId } : {}),
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-User-Id': getStoredUserId(),
  };
  if (sessionId) {
    headers['X-Client-Session-Id'] = sessionId;
  }

  const res = await apiFetch<OutfitRatingResponseData>(`${API_BASE_URL}/api/v1/outfits/${encodeURIComponent(outfitId)}/rating`, {
    method: 'PUT',
    headers,
    body: JSON.stringify(bodyPayload),
  });

  setSessionFeedbackSuppressed();

  return res;
}

/**
 * Dismiss proactive feedback rating prompt and activate cooldown (POST /api/v1/feedback/prompts/dismiss)
 */
export async function dismissFeedbackPrompt(
  payload?: DismissPromptRequest
): Promise<DismissPromptResponseData> {
  const sessionId = payload?.client_session_id || getStoredSessionId();
  const bodyPayload: DismissPromptRequest = {
    client_session_id: sessionId,
  };

  return apiFetch<DismissPromptResponseData>(`${API_BASE_URL}/api/v1/feedback/prompts/dismiss`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
      'X-Client-Session-Id': sessionId,
    },
    body: JSON.stringify(bodyPayload),
  });
}

export async function createTryOn(
  outfitId: string,
  options?: { signal?: AbortSignal }
): Promise<TryOnResponseData> {
  return apiFetch<TryOnResponseData>(`${API_BASE_URL}/api/v1/tryons`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
    },
    body: JSON.stringify({ outfit_id: outfitId }),
    signal: options?.signal,
  });
}

/**
 * List wardrobe items with optional filters and pagination (GET /api/v1/wardrobe/items)
 */
export async function listWardrobeItems(params?: {
  category?: string;
  style?: string;
  color?: string;
  text?: string;
  page?: number;
  page_size?: number;
  userId?: string;
}): Promise<WardrobeItemListResponse> {
  const query = new URLSearchParams();
  if (params?.category) query.set('category', params.category);
  if (params?.style) query.set('style', params.style);
  if (params?.color) query.set('color', params.color);
  if (params?.text) query.set('text', params.text);
  if (params?.page) query.set('page', params.page.toString());
  if (params?.page_size) query.set('page_size', params.page_size.toString());

  const queryString = query.toString();
  const url = `${API_BASE_URL}/api/v1/wardrobe/items${queryString ? `?${queryString}` : ''}`;
  return apiFetch<WardrobeItemListResponse>(url, {
    method: 'GET',
    headers: {
      'X-User-Id': params?.userId || getStoredUserId(),
    },
  });
}

/**
 * Get a single wardrobe item by ID (GET /api/v1/wardrobe/items/{id})
 */
export async function getWardrobeItem(itemId: string, userId?: string): Promise<WardrobeItem> {
  return apiFetch<WardrobeItem>(`${API_BASE_URL}/api/v1/wardrobe/items/${itemId}`, {
    method: 'GET',
    headers: {
      'X-User-Id': userId || getStoredUserId(),
    },
  });
}

/**
 * Update wardrobe item attributes (PATCH /api/v1/wardrobe/items/{id})
 */
export async function updateWardrobeItem(
  itemId: string,
  payload: WardrobeItemUpdatePayload,
  userId?: string
): Promise<WardrobeItem> {
  return apiFetch<WardrobeItem>(`${API_BASE_URL}/api/v1/wardrobe/items/${itemId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId || getStoredUserId(),
    },
    body: JSON.stringify(payload),
  });
}

/**
 * Soft-delete / deactivate a wardrobe item (DELETE /api/v1/wardrobe/items/{id})
 */
export async function deleteWardrobeItem(
  itemId: string,
  userId?: string
): Promise<WardrobeItemDeleteResponse> {
  return apiFetch<WardrobeItemDeleteResponse>(`${API_BASE_URL}/api/v1/wardrobe/items/${itemId}`, {
    method: 'DELETE',
    headers: {
      'X-User-Id': userId || getStoredUserId(),
    },
  });
}
