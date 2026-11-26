const PRESET_STORAGE_KEY = 'fashion_stylist_tryon_preset';
const PRESET_IDS = ['preset-male', 'preset-female'];

/**
 * Preset model shown first in the try-on dialog: the preset the viewer chose last,
 * otherwise the female preset for an outfit built around a dress (a dress renders
 * poorly on the male preset), otherwise the male preset. Uploaded avatars are not
 * remembered because they can be deleted.
 */
export function initialPresetId(items: ReadonlyArray<{ slot: string }>): string {
  try {
    const stored = localStorage.getItem(PRESET_STORAGE_KEY);
    if (stored && PRESET_IDS.includes(stored)) return stored;
  } catch {
    // Storage unavailable (private browsing, server render): fall through.
  }
  return items.some((item) => item.slot === 'dress') ? 'preset-female' : 'preset-male';
}

export function rememberPresetId(avatarId: string): void {
  if (!PRESET_IDS.includes(avatarId)) return;
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, avatarId);
  } catch {
    // Storage unavailable: the choice applies to this dialog only.
  }
}
