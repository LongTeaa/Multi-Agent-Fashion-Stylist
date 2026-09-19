export type OutfitSlotRole = 'top' | 'bottom' | 'shoes';

export interface StylistChatRequest {
  query: string;
  location?: string | null;
  client_session_id?: string | null;
  idempotency_key?: string | null;
}

export interface StylistRecommendationItem {
  slot: OutfitSlotRole;
  item_id: string;
  name: string;
  image_url: string | null;
}

export interface StylistRecommendation {
  outfit_id: string;
  rank: number;
  composite_score: number;
  items: StylistRecommendationItem[];
  explanation_vi: string;
  applied_preferences: string[];
}

export interface StylistContext {
  occasion?: string | null;
  time_of_day?: string | null;
  event_date?: string | null;
  location_text?: string | null;
  environment?: string | null;
  weather_condition?: string | null;
  temperature_celsius?: number | null;
  target_formality_range: number[];
  style_hints: string[];
  vibe_keywords: string[];
  must_have: string[];
  must_avoid: string[];
  weather_source: string;
}

export interface StylistChatResponseData {
  request_id: string;
  needs_clarification: boolean;
  clarification_question?: string | null;
  context: StylistContext;
  recommendations: StylistRecommendation[];
  feedback_prompt_eligible: boolean;
  feedback_target_outfit_id?: string | null;
  warnings: string[];
}
