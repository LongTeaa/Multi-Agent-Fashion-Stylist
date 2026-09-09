export interface PreferenceSelections {
  styles: string[];
  color_palettes: string[];
  priorities: string[];
  avoid_colors: string[];
  avoid_styles: string[];
  fit_preferences: string[];
}

export interface PreferenceOptionGroup {
  values: string[];
  selection_limit: number;
}

export interface PreferenceOptions {
  version: number;
  styles: PreferenceOptionGroup;
  color_palettes: PreferenceOptionGroup;
  priorities: PreferenceOptionGroup;
  fit_preferences: PreferenceOptionGroup;
  avoid_colors: PreferenceOptionGroup;
  avoid_styles: PreferenceOptionGroup;
}

export interface UserProfile {
  user_id: string;
  email: string | null;
  full_name: string | null;
  preferences: PreferenceSelections;
  feature_weights: Record<string, unknown>;
  ratings_count: number;
}
