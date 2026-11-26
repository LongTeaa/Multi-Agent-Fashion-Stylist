/** Vietnamese display labels for preference option values returned by the API. */
export const PREFERENCE_LABELS: Record<string, string> = {
  casual: 'Thoải mái',
  minimalist: 'Tối giản',
  smart_casual: 'Thanh lịch thường ngày',
  streetwear: 'Đường phố',
  formal: 'Trang trọng',
  vintage: 'Cổ điển',
  neutral: 'Trung tính',
  earth_tone: 'Tông đất',
  cool_tone: 'Tông lạnh',
  warm_tone: 'Tông ấm',
  monochrome: 'Đơn sắc',
  comfort: 'Thoải mái',
  polished: 'Chỉn chu',
  expressive: 'Nổi bật',
  mobility: 'Dễ vận động',
  low_maintenance: 'Dễ chăm sóc',
  slim: 'Ôm',
  regular: 'Vừa vặn',
  relaxed: 'Rộng vừa',
  oversized: 'Rộng',
  white: 'Trắng',
  black: 'Đen',
  grey: 'Xám',
  beige: 'Be',
  cream: 'Kem',
  khaki: 'Khaki',
  navy: 'Xanh navy',
  brown: 'Nâu',
  tan: 'Nâu nhạt',
  red: 'Đỏ',
  orange: 'Cam',
  yellow: 'Vàng',
  green: 'Xanh lá',
  blue: 'Xanh dương',
  purple: 'Tím',
  pink: 'Hồng',
};

export function preferenceLabel(value: string): string {
  return PREFERENCE_LABELS[value] ?? value;
}

/** Colour values the vision provider returns beyond the preference palette. */
const EXTRA_COLOR_LABELS: Record<string, string> = {
  charcoal: 'Xám than',
  dark_gray: 'Xám đậm',
  dark_grey: 'Xám đậm',
  light_gray: 'Xám nhạt',
  light_grey: 'Xám nhạt',
  silver: 'Bạc',
  teal: 'Xanh mòng két',
  olive: 'Ô-liu',
  burgundy: 'Đỏ đô',
  maroon: 'Đỏ đô',
  light_blue: 'Xanh nhạt',
  denim_blue: 'Xanh denim',
};

const ATTRIBUTE_LABELS: Record<string, string> = {
  ...PREFERENCE_LABELS,
  casual: 'Thường ngày',
  business: 'Công sở',
  street: 'Đường phố',
  athletic: 'Thể thao',
  gray: 'Xám',
  multicolor: 'Nhiều màu',
  ...EXTRA_COLOR_LABELS,
};

/**
 * Display label for a stored garment attribute (style, colour…). Known enum
 * values get their Vietnamese label; free text is shown as typed; "unknown"
 * is hidden.
 */
export function attributeLabel(value: string | null | undefined): string {
  if (!value) return '';
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (!key || key === 'unknown') return '';
  return ATTRIBUTE_LABELS[key] ?? value.replace(/_/g, ' ');
}

const COLOR_KEYS = [
  'white', 'black', 'grey', 'gray', 'beige', 'cream', 'khaki', 'navy', 'brown', 'tan', 'red', 'orange',
  'yellow', 'green', 'blue', 'purple', 'pink', 'multicolor', ...Object.keys(EXTRA_COLOR_LABELS),
];

/** Text shown in a colour input: the Vietnamese label of a known value, otherwise the value as typed. */
export function colorInputValue(value: string | null | undefined): string {
  if (!value) return '';
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, '_');
  return COLOR_KEYS.includes(key) ? ATTRIBUTE_LABELS[key] : value;
}

/** Stored colour for typed text: a known Vietnamese label maps back to its canonical value. */
export function colorFromInput(text: string): string {
  const typed = text.trim().toLowerCase();
  const match = COLOR_KEYS.find((key) => ATTRIBUTE_LABELS[key].toLowerCase() === typed);
  return match ?? text;
}
