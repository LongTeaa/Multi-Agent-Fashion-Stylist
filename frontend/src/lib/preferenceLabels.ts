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

const ATTRIBUTE_LABELS: Record<string, string> = {
  ...PREFERENCE_LABELS,
  casual: 'Thường ngày',
  business: 'Công sở',
  street: 'Đường phố',
  athletic: 'Thể thao',
  gray: 'Xám',
  multicolor: 'Nhiều màu',
};

/**
 * Display label for a stored garment attribute (style, colour…). Known enum
 * values get their Vietnamese label; free text is shown as typed; "unknown"
 * is hidden.
 */
export function attributeLabel(value: string | null | undefined): string {
  if (!value) return '';
  const key = value.trim().toLowerCase();
  if (!key || key === 'unknown') return '';
  return ATTRIBUTE_LABELS[key] ?? value.replace(/_/g, ' ');
}
