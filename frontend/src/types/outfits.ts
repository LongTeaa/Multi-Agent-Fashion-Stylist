import type { OutfitSlotRole } from './chat';

export type RatingSource = 'prompted' | 'manual';
export type WardrobeCategory = 'top' | 'bottom' | 'shoes' | 'outerwear' | 'accessory';

export interface OutfitItemDetailResponse {
  slot_role: OutfitSlotRole;
  wardrobe_item_id: string;
  name: string;
  category: WardrobeCategory;
  sub_category: string;
  primary_color: string;
  secondary_color?: string | null;
  pattern: string;
  material: string;
  style: string;
  image_url?: string | null;
  is_active: boolean;
}

export interface OutfitDetailResponseData {
  id: string;
  request_id: string;
  user_query: string;
  explanation_vi: string;
  fashion_score: number;
  personalization_score: number;
  composite_score: number;
  rank: number;
  is_bookmarked: boolean;
  times_worn: number;
  last_worn_at?: string | null;
  user_rating?: number | null;
  items: OutfitItemDetailResponse[];
  created_at: string;
}

export interface SavedOutfitsResponseData {
  items: OutfitDetailResponseData[];
  page: number;
  page_size: number;
  total: number;
}

export interface BookmarkRequest {
  is_bookmarked: boolean;
}

export interface BookmarkResponseData {
  outfit_id: string;
  is_bookmarked: boolean;
  updated_at: string;
}

export interface OutfitWornRequest {
  idempotency_key: string;
  worn_at?: string | null;
}

export interface OutfitWornResponseData {
  wear_log_id: string;
  outfit_id: string;
  worn_at: string;
  times_worn: number;
  already_processed: boolean;
}

export interface OutfitRatingRequest {
  stars: number;
  source: RatingSource;
  client_session_id?: string | null;
}

export interface OutfitRatingResponseData {
  rating_id: string;
  outfit_id: string;
  stars: number;
  source: RatingSource;
  ratings_count: number;
  created_at: string;
  updated_at: string;
}
