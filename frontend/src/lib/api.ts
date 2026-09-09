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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const USER_STORAGE_KEY = 'fashion_stylist_user_id';

/**
 * Get or generate a persistent demo user ID for cross-request session tracking.
 */
export function getStoredUserId(): string {
  if (typeof window === 'undefined') {
    return '00000000-0000-0000-0000-000000000001';
  }
  let userId = localStorage.getItem(USER_STORAGE_KEY);
  if (!userId) {
    userId = crypto.randomUUID();
    localStorage.setItem(USER_STORAGE_KEY, userId);
  }
  return userId;
}

export function setStoredUserId(id: string): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem(USER_STORAGE_KEY, id);
  }
}

class ApiError extends Error {
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
  const response = await fetch(`${API_BASE_URL}/api/v1/ingestions`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
    },
    body: formData,
  });

  return handleResponse<UploadBatchResponse>(response);
}

/**
 * Retrieve ingestion review state, bounding boxes, crops, and attributes (GET /api/v1/ingestions/{batch_id})
 */
export async function getIngestionBatch(batchId: string): Promise<IngestionBatchReviewResponse> {
  const userId = getStoredUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/ingestions/${batchId}`, {
    method: 'GET',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
  });

  return handleResponse<IngestionBatchReviewResponse>(response);
}

/**
 * Confirm accepted detections with customized fashion attributes (POST /api/v1/ingestions/{batch_id}/confirm)
 */
export async function confirmIngestionBatch(
  batchId: string,
  payload: ConfirmBatchPayload
): Promise<ConfirmBatchResponse> {
  const userId = getStoredUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/ingestions/${batchId}/confirm`, {
    method: 'POST',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  return handleResponse<ConfirmBatchResponse>(response);
}

/**
 * Cancel an unconfirmed batch and clean up transient assets (DELETE /api/v1/ingestions/{batch_id})
 */
export async function deleteIngestionBatch(batchId: string): Promise<{ batch_id: string; status: string }> {
  const userId = getStoredUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/ingestions/${batchId}`, {
    method: 'DELETE',
    headers: {
      'X-User-Id': userId,
      'Content-Type': 'application/json',
    },
  });

  return handleResponse<{ batch_id: string; status: string }>(response);
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
  const userId = getStoredUserId();
  const sep = cleanPath.includes('?') ? '&' : '?';
  return `${API_BASE_URL}${cleanPath}${sep}user_id=${encodeURIComponent(userId)}`;
}

export async function getUserProfile(): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/api/v1/user/profile`, {
    headers: { 'X-User-Id': getStoredUserId() },
  });
  return handleResponse<UserProfile>(response);
}

export async function getPreferenceOptions(): Promise<PreferenceOptions> {
  const response = await fetch(`${API_BASE_URL}/api/v1/user/profile/preference-options`, {
    headers: { 'X-User-Id': getStoredUserId() },
  });
  return handleResponse<PreferenceOptions>(response);
}

export async function replaceUserPreferences(
  preferences: PreferenceSelections
): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/api/v1/user/profile/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getStoredUserId(),
    },
    body: JSON.stringify(preferences),
  });
  return handleResponse<UserProfile>(response);
}
