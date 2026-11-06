export type TryOnRenderKind = 'virtual_tryon' | 'generated_lookbook' | 'moodboard';

export interface TryOnResponseData {
  tryon_id: string;
  outfit_id?: string | null;
  image_url: string;
  render_kind: TryOnRenderKind;
  fallback_used: boolean;
  duration_ms: number;
  status: 'processing' | 'ready' | 'failed';
  error_code?: string | null;
}

export interface TryOnAvatar {
  id: string;
  name: string;
  is_preset: boolean;
  preset_gender?: string | null;
  is_default: boolean;
  image_url: string;
  created_at: string;
}

export interface TryOnDisplayItem {
  id: string;
  slot: string;
  name: string;
  imageUrl?: string | null;
  primaryColor?: string;
}
