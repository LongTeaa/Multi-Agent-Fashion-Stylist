/** Canonical functional flags a user can set on a garment, in display order. */
export const FUNCTIONAL_FLAG_VALUES = [
  'movement',
  'outdoor',
  'sun',
  'water_resistant',
  'work',
  'sport',
  'protection',
  'light',
  'heavy',
] as const;

export type FunctionalFlag = (typeof FUNCTIONAL_FLAG_VALUES)[number];

/** Short Vietnamese tag names for wardrobe cards and the edit dialog. */
export const FUNCTION_TAG_NAMES: Record<string, string> = {
  movement: 'Vận động',
  outdoor: 'Ngoài trời',
  sun: 'Chống nắng',
  rain: 'Chống mưa',
  water_resistant: 'Chống mưa',
  work: 'Công sở',
  sport: 'Thể thao',
  protection: 'Bảo hộ',
  light: 'Thoáng nhẹ',
  heavy: 'Dày ấm',
};
