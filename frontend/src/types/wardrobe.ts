export type WardrobeCategory =
  | 'top'
  | 'bottom'
  | 'dress'
  | 'footwear'
  | 'outerwear'
  | 'accessory';

export interface WardrobeItem {
  id: string;
  category: WardrobeCategory;
  sub_category: string;
  primary_color: string;
  secondary_color?: string | null;
  pattern: string;
  material: string;
  style: string;
  fit: string;
  formality_level: number;
  comfort_level: number;
  silhouette_level: number;
  length: string;
  season: string[];
  weather_suitability: string[];
  functional_flags: string[];
  free_text_tags: string[];
  is_active: boolean;
  times_worn: number;
  last_worn_at?: string | null;
  media_url?: string | null;
  thumbnail_url?: string | null;
}

export interface WardrobeItemListResponse {
  items: WardrobeItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface WardrobeItemUpdatePayload {
  sub_category?: string;
  primary_color?: string;
  secondary_color?: string | null;
  pattern?: string;
  material?: string;
  style?: string;
  fit?: string;
  formality_level?: number;
  comfort_level?: number;
  silhouette_level?: number;
  length?: string;
  season?: string[];
  weather_suitability?: string[];
  functional_flags?: string[];
  free_text_tags?: string[];
  is_active?: boolean;
}

export interface WardrobeItemDeleteResponse {
  item_id: string;
  is_active: boolean;
}
