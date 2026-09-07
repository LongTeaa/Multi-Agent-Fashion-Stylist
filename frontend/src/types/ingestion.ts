export type BoundingBox = [number, number, number, number]; // [ymin, xmin, ymax, xmax]

export type InputKind = 'single_item' | 'multi_item' | 'worn_outfit' | 'cluttered' | 'unknown';

export type IngestionStatus =
  | 'uploaded'
  | 'processing'
  | 'needs_review'
  | 'confirmed'
  | 'failed'
  | 'expired';

export interface FashionAttributes {
  category: string;
  sub_category?: string | null;
  primary_color?: string | null;
  secondary_color?: string | null;
  pattern?: string | null;
  material?: string | null;
  style?: string | null;
  fit?: string | null;
  formality_level?: number;
  season?: string[];
  weather_suitability?: string[];
  functional_flags?: string[];
  free_text_tags?: string[];
  [key: string]: unknown;
}

export interface DetectionReviewItem {
  detection_id: string;
  crop_url: string;
  bounding_box: BoundingBox;
  attributes: FashionAttributes;
  field_confidence: Record<string, number>;
}

export interface IngestionBatchReviewResponse {
  batch_id: string;
  input_kind: InputKind | string;
  status: IngestionStatus | string;
  quality_warnings: string[];
  detections: DetectionReviewItem[];
}

export interface DetectionConfirmationItem {
  detection_id: string;
  accepted: boolean;
  custom_attributes?: Partial<FashionAttributes>;
}

export interface ConfirmBatchPayload {
  idempotency_token: string;
  confirmations: DetectionConfirmationItem[];
}

export interface ConfirmBatchResponse {
  batch_id: string;
  status: string;
  wardrobe_item_ids: string[];
}

export interface UploadBatchResponse {
  batch_id: string;
  status: string;
  declared_input_kind?: string;
  item_count: number;
}

export interface ApiSuccessResponse<T> {
  data: T;
  meta?: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}
