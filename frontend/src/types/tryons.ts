export type TryOnRenderKind = 'generated_lookbook' | 'moodboard';

export interface TryOnResponseData {
  tryon_id: string;
  outfit_id: string;
  image_url: string;
  render_kind: TryOnRenderKind;
  fallback_used: boolean;
  duration_ms: number;
  status: 'ready';
}

export interface TryOnDisplayItem {
  id: string;
  slot: string;
  name: string;
  imageUrl?: string | null;
  primaryColor?: string;
}
