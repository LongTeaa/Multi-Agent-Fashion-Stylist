'use client';

import React from 'react';
import type { DetectionReviewItem, FashionAttributes } from '@/types/ingestion';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';

interface DetectionItemCardProps {
  detection: DetectionReviewItem;
  index: number;
  isSelected: boolean;
  accepted: boolean;
  attributes: FashionAttributes;
  onSelect: () => void;
  onToggleAccepted: (accepted: boolean) => void;
  onUpdateAttribute: (key: string, value: unknown) => void;
}

const CATEGORIES = [
  { value: 'top', label: 'Áo (Top)' },
  { value: 'bottom', label: 'Quần / Chân váy (Bottom)' },
  { value: 'footwear', label: 'Giày dép (Footwear)' },
  { value: 'outerwear', label: 'Áo khoác (Outerwear)' },
  { value: 'dress', label: 'Đầm / Váy liền (Dress)' },
  { value: 'accessory', label: 'Phụ kiện (Accessory)' },
];

const SUB_CATEGORY_SUGGESTIONS: Record<string, { value: string; label: string }[]> = {
  footwear: [
    { value: 'sneakers', label: 'Sneakers' },
    { value: 'oxford', label: 'Oxford' },
    { value: 'loafers', label: 'Loafers (Giày lười)' },
    { value: 'leather_shoes', label: 'Giày da' },
    { value: 'sandals', label: 'Sandal' },
    { value: 'slides', label: 'Dép quai ngang' },
    { value: 'boots', label: 'Boots' },
    { value: 'heels', label: 'Giày cao gót' },
  ],
  top: [
    { value: 'tshirt', label: 'Áo thun' },
    { value: 'polo', label: 'Áo Polo' },
    { value: 'shirt', label: 'Áo sơ mi' },
    { value: 'sweater', label: 'Áo len' },
    { value: 'tanktop', label: 'Áo ba lỗ' },
  ],
  bottom: [
    { value: 'trousers', label: 'Quần tây' },
    { value: 'chinos', label: 'Quần Chinos' },
    { value: 'jeans', label: 'Quần Jeans' },
    { value: 'shorts', label: 'Quần short' },
    { value: 'skirt', label: 'Chân váy' },
  ],
  outerwear: [
    { value: 'blazer', label: 'Blazer' },
    { value: 'jacket', label: 'Áo khoác' },
    { value: 'hoodie', label: 'Hoodie' },
    { value: 'cardigan', label: 'Cardigan' },
  ],
  dress: [
    { value: 'casual_dress', label: 'Đầm thường ngày' },
    { value: 'formal_dress', label: 'Đầm dạ hội' },
    { value: 'shirt_dress', label: 'Đầm sơ mi' },
  ],
  accessory: [
    { value: 'belt', label: 'Thắt lưng' },
    { value: 'watch', label: 'Đồng hồ' },
    { value: 'bag', label: 'Túi xách' },
    { value: 'hat', label: 'Mũ / Nón' },
    { value: 'glasses', label: 'Kính mắt' },
  ],
};

const STYLES = [
  { value: 'casual', label: 'Thường nhật (Casual)' },
  { value: 'smart_casual', label: 'Thanh lịch thường nhật (Smart Casual)' },
  { value: 'formal', label: 'Trang trọng (Formal)' },
  { value: 'business', label: 'Công sở (Business)' },
  { value: 'street', label: 'Đường phố (Streetwear)' },
  { value: 'athletic', label: 'Thể thao (Athletic)' },
  { value: 'minimalist', label: 'Tối giản (Minimalist)' },
  { value: 'vintage', label: 'Cổ điển (Vintage)' },
];

const PATTERNS = [
  { value: 'solid', label: 'Trơn (Solid)' },
  { value: 'striped', label: 'Kẻ sọc (Striped)' },
  { value: 'checked', label: 'Kẻ caro (Checked)' },
  { value: 'floral', label: 'Họa tiết hoa (Floral)' },
  { value: 'printed', label: 'Họa tiết in (Printed)' },
  { value: 'graphic', label: 'Họa tiết đồ họa (Graphic)' },
];

const MATERIALS = [
  { value: 'cotton', label: 'Cotton (Bông)' },
  { value: 'linen', label: 'Linen (Đũi)' },
  { value: 'denim', label: 'Denim (Bò)' },
  { value: 'wool', label: 'Len (Wool)' },
  { value: 'polyester', label: 'Polyester' },
  { value: 'silk', label: 'Lụa (Silk)' },
  { value: 'leather', label: 'Da (Leather)' },
  { value: 'knit', label: 'Dệt kim (Knit)' },
];

const FITS = [
  { value: 'slim', label: 'Ôm vừa (Slim fit)' },
  { value: 'regular', label: 'Tiêu chuẩn (Regular fit)' },
  { value: 'relaxed', label: 'Thoải mái (Relaxed)' },
  { value: 'oversized', label: 'Rộng (Oversized)' },
];

const SEASONS = [
  { value: 'spring', label: 'Xuân' },
  { value: 'summer', label: 'Hạ' },
  { value: 'autumn', label: 'Thu' },
  { value: 'winter', label: 'Đông' },
  { value: 'all_year', label: 'Cả năm' },
];

const SILHOUETTES = [
  { value: 1, label: 'Rất ôm sát (1 - Very fitted)' },
  { value: 2, label: 'Ôm vừa (2 - Fitted)' },
  { value: 3, label: 'Tiêu chuẩn (3 - Regular)' },
  { value: 4, label: 'Thoải mái / Rộng (4 - Relaxed)' },
  { value: 5, label: 'Rộng thùng thình (5 - Oversized)' },
];

const LENGTHS = [
  { value: 'cropped', label: 'Dáng ngắn lửng (Cropped)' },
  { value: 'waist', label: 'Dài ngang eo (Waist)' },
  { value: 'hip', label: 'Dài ngang hông (Hip - Tiêu chuẩn)' },
  { value: 'long', label: 'Dáng dài (Long - Phủ chân/Dài qua gối)' },
];

const FUNCTIONAL_FLAGS = [
  { value: 'movement', label: '🏃 Vận động / Co giãn' },
  { value: 'outdoor', label: '🏕️ Dã ngoại / Ngoài trời' },
  { value: 'sun', label: '☀️ Chống nắng' },
  { value: 'rain', label: '🌧️ Chống mưa / Nước' },
  { value: 'work', label: '💼 Đi làm / Công sở' },
  { value: 'sport', label: '⚽ Thể thao' },
  { value: 'protection', label: '🛡️ Bảo hộ / Giữ nhiệt' },
  { value: 'light', label: '🪶 Siêu nhẹ / Thoáng' },
  { value: 'heavy', label: '🧥 Dày ấm / Nặng' },
];

const COMFORT_LABELS: Record<number, string> = {
  1: 'Gò bó / Thô cứng (1)',
  2: 'Hơi hạn chế (2)',
  3: 'Tiêu chuẩn (3)',
  4: 'Thoải mái (4)',
  5: 'Rất thoải mái / Co giãn (5)',
};

export function DetectionItemCard({
  detection,
  index,
  isSelected,
  accepted,
  attributes,
  onSelect,
  onToggleAccepted,
  onUpdateAttribute,
}: DetectionItemCardProps) {
  const confidences = detection.field_confidence || {};
  const cropUrl = detection.crop_url;

  const isLowConfidence = (field: string) => {
    const conf = confidences[field];
    return typeof conf === 'number' && conf < 0.70;
  };

  const renderConfidenceBadge = (field: string) => {
    const conf = confidences[field];
    if (typeof conf !== 'number') {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded-full bg-[#FAF8F5] text-[#5C564E] border border-[#E8E5DE]">
          Chưa xác định
        </span>
      );
    }
    const isLow = conf < 0.70;
    const percentage = Math.round(conf * 100);

    return (
      <span
        className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded-full ${
          isLow
            ? 'bg-amber-100 text-amber-900 border border-amber-300 font-semibold animate-pulse'
            : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
        }`}
      >
        {isLow ? (
          <>
            <span>⚠️ Cần kiểm tra</span>
            <span className="font-bold">({percentage}%)</span>
          </>
        ) : (
          <span>✓ {percentage}% (AI nhận diện)</span>
        )}
      </span>
    );
  };

  const handleSeasonToggle = (seasonVal: string) => {
    const current = Array.isArray(attributes.season) ? attributes.season : [];
    if (current.includes(seasonVal)) {
      onUpdateAttribute('season', current.filter((s) => s !== seasonVal));
    } else {
      onUpdateAttribute('season', [...current, seasonVal]);
    }
  };

  const handleFunctionalFlagToggle = (flagVal: string) => {
    const current = Array.isArray(attributes.functional_flags) ? attributes.functional_flags : [];
    if (current.includes(flagVal)) {
      onUpdateAttribute('functional_flags', current.filter((f) => f !== flagVal));
    } else {
      onUpdateAttribute('functional_flags', [...current, flagVal]);
    }
  };

  return (
    <div
      onClick={onSelect}
      className={`rounded-3xl border transition-all duration-200 overflow-hidden ${
        isSelected
          ? 'border-[#1A1918] ring-2 ring-[#1A1918]/15 shadow-md bg-white'
          : 'border-[#E8E5DE] bg-white hover:border-[#D5D1C7] shadow-2xs'
      } ${!accepted ? 'opacity-60 bg-[#FAF8F5]' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-[#E8E5DE] bg-[#FAF8F5]/80">
        <div className="flex items-center gap-3.5">
          <span className="w-8 h-8 rounded-full bg-[#1A1918] text-[#FBFBF9] font-mono font-semibold text-xs flex items-center justify-center shadow-2xs">
            {index + 1}
          </span>
          <div>
            <h4 className="text-base sm:text-lg font-semibold text-[#1A1918] capitalize">
              {CATEGORIES.find((c) => c.value === attributes.category)?.label.split(' ')[0] || attributes.category || 'Món đồ'} •{' '}
              {attributes.sub_category || 'Chưa phân loại'}
            </h4>
            <p className="text-xs font-mono text-[#5C564E]">Mã AI: {detection.detection_id.slice(0, 8)}</p>
          </div>
        </div>

        {/* Accept / Reject Switch */}
        <label
          onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-2.5 cursor-pointer select-none"
        >
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => onToggleAccepted(e.target.checked)}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-[#E8E5DE] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-[#D5D1C7] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#9C5234]"></div>
          <span className="text-xs sm:text-sm font-mono text-[#1A1918] font-medium">
            {accepted ? 'Lưu món này' : 'Bỏ qua'}
          </span>
        </label>
      </div>

      <div className="p-5 sm:p-6 flex flex-col md:flex-row gap-6 lg:gap-8">
        {/* Crop Preview Column */}
        <div className="flex flex-col items-center flex-shrink-0">
          <div className="w-36 h-36 sm:w-44 sm:h-44 xl:w-48 xl:h-48 rounded-2xl border border-[#E8E5DE] overflow-hidden bg-[#FAF8F5] flex items-center justify-center shadow-2xs relative group">
            {cropUrl ? (
              <PrivateMediaImage
                source={cropUrl}
                alt="Cropped item"
                className="w-full h-full object-contain p-2"
              />
            ) : (
              <span className="text-xs font-mono text-[#736E65]">Không có ảnh</span>
            )}
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition flex items-center justify-center text-white text-xs font-mono font-medium">
              Ảnh cắt chi tiết
            </div>
          </div>
          <span className="mt-2 text-xs font-mono text-[#5C564E]">Vùng ảnh phân tích</span>
        </div>

        {/* Attribute Correction Form Fields */}
        <div className="flex-1 space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-5">
            {/* Category */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">
                  Danh mục chính <span className="text-rose-600">*</span>
                </label>
                {renderConfidenceBadge('category')}
              </div>
              <select
                value={attributes.category || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('category', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  !attributes.category || attributes.category === 'unknown'
                    ? 'border-rose-400 bg-rose-50/20 focus:ring-2 focus:ring-rose-400 text-[#1A1918]'
                    : isLowConfidence('category')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                <option value="" disabled>
                  -- Chọn danh mục (Bắt buộc) --
                </option>
                {CATEGORIES.map((cat) => (
                  <option key={cat.value} value={cat.value}>
                    {cat.label}
                  </option>
                ))}
              </select>
              {(!attributes.category || attributes.category === 'unknown') && accepted && (
                <p className="text-xs text-rose-600 mt-1.5 font-medium">
                  Vui lòng chọn danh mục chính để lưu món đồ này.
                </p>
              )}
            </div>

            {/* Sub-Category */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Loại chi tiết (Sub-category)</label>
                {renderConfidenceBadge('sub_category')}
              </div>
              <input
                type="text"
                list={`sub-suggestions-${index}`}
                value={attributes.sub_category || ''}
                disabled={!accepted}
                placeholder="VD: sneakers, loafers, oxford, polo, chinos..."
                onChange={(e) => onUpdateAttribute('sub_category', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('sub_category')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              />
              <datalist id={`sub-suggestions-${index}`}>
                {(SUB_CATEGORY_SUGGESTIONS[attributes.category] || []).map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </datalist>
              {SUB_CATEGORY_SUGGESTIONS[attributes.category] && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {SUB_CATEGORY_SUGGESTIONS[attributes.category].map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      disabled={!accepted}
                      onClick={() => onUpdateAttribute('sub_category', s.value)}
                      className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                        attributes.sub_category?.toLowerCase() === s.value.toLowerCase()
                          ? 'bg-[#1A1918] text-white border-[#1A1918] font-medium'
                          : 'bg-[#FAF8F5] text-[#5C564E] border-[#E8E5DE] hover:border-[#D5D1C7] hover:text-[#1A1918]'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Primary Color */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Màu sắc chủ đạo</label>
                {renderConfidenceBadge('primary_color')}
              </div>
              <input
                type="text"
                value={attributes.primary_color || ''}
                disabled={!accepted}
                placeholder="VD: trắng, đen, navy, be..."
                onChange={(e) => onUpdateAttribute('primary_color', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('primary_color')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              />
            </div>

            {/* Pattern */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Họa tiết (Pattern)</label>
                {renderConfidenceBadge('pattern')}
              </div>
              <select
                value={attributes.pattern || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('pattern', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('pattern')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                <option value="" disabled>
                  -- Chưa xác định / Vui lòng chọn --
                </option>
                {PATTERNS.map((pat) => (
                  <option key={pat.value} value={pat.value}>
                    {pat.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Material */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Chất liệu (Material)</label>
                {renderConfidenceBadge('material')}
              </div>
              <select
                value={attributes.material || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('material', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('material')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                <option value="" disabled>
                  -- Chưa xác định / Vui lòng chọn --
                </option>
                {MATERIALS.map((mat) => (
                  <option key={mat.value} value={mat.value}>
                    {mat.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Style */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Phong cách (Style)</label>
                {renderConfidenceBadge('style')}
              </div>
              <select
                value={attributes.style || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('style', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('style')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                <option value="" disabled>
                  -- Chưa xác định / Vui lòng chọn --
                </option>
                {STYLES.map((st) => (
                  <option key={st.value} value={st.value}>
                    {st.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Fit */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Phom dáng (Fit)</label>
                {renderConfidenceBadge('fit')}
              </div>
              <select
                value={attributes.fit || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('fit', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('fit')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                <option value="" disabled>
                  -- Chưa xác định / Vui lòng chọn --
                </option>
                {FITS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Formality Level */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">
                  Mức độ trang trọng:{' '}
                  <span className="font-bold text-[#9C5234] text-sm sm:text-base">
                    {attributes.formality_level ? `${attributes.formality_level}/5` : 'Chưa xác định'}
                  </span>
                </label>
                {renderConfidenceBadge('formality_level')}
              </div>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={attributes.formality_level || 3}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('formality_level', parseInt(e.target.value, 10))}
                className="w-full accent-[#9C5234] cursor-pointer h-2"
              />
              <div className="flex justify-between text-xs font-mono text-[#5C564E] mt-1">
                <span>Thường ngày (1)</span>
                <span>Bán trang trọng (3)</span>
                <span>Dạ tiệc (5)</span>
              </div>
            </div>

            {/* Comfort Level (1-5 Sao) */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">
                  Độ thoải mái (Comfort):{' '}
                  <span className="font-bold text-[#9C5234] text-sm sm:text-base">
                    {attributes.comfort_level ? `${attributes.comfort_level}/5 ⭐` : 'Chưa xác định'}
                  </span>
                </label>
                {renderConfidenceBadge('comfort_level')}
              </div>
              <div className="flex items-center gap-1.5 mb-1.5">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    disabled={!accepted}
                    onClick={() => onUpdateAttribute('comfort_level', star)}
                    className={`flex-1 py-1.5 rounded-lg border text-sm transition font-mono ${
                      (attributes.comfort_level || 3) >= star
                        ? 'bg-[#9C5234] text-white border-[#9C5234] shadow-2xs font-semibold'
                        : 'bg-[#FAF8F5] text-[#5C564E] border-[#E8E5DE] hover:border-[#D5D1C7]'
                    }`}
                  >
                    {star}★
                  </button>
                ))}
              </div>
              <p className="text-xs font-mono text-[#5C564E]">
                {COMFORT_LABELS[attributes.comfort_level || 3] || 'Tiêu chuẩn (3)'}
              </p>
            </div>

            {/* Silhouette Level (Dáng tổng thể 1-5) */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Dáng tổng thể (Silhouette)</label>
                {renderConfidenceBadge('silhouette_level')}
              </div>
              <select
                value={attributes.silhouette_level || 3}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('silhouette_level', parseInt(e.target.value, 10))}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('silhouette_level')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                {SILHOUETTES.map((sil) => (
                  <option key={sil.value} value={sil.value}>
                    {sil.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Length (Độ dài trang phục) */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs sm:text-sm font-semibold text-[#1A1918]">Độ dài (Length)</label>
                {renderConfidenceBadge('length')}
              </div>
              <select
                value={attributes.length || 'hip'}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('length', e.target.value)}
                className={`w-full px-3.5 py-2.5 text-sm sm:text-base rounded-xl border focus:outline-none transition ${
                  isLowConfidence('length')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400 text-[#1A1918]'
                    : 'border-[#D5D1C7] bg-white text-[#1A1918] focus:ring-2 focus:ring-[#9C5234]/30 focus:border-[#9C5234]'
                }`}
              >
                {LENGTHS.map((len) => (
                  <option key={len.value} value={len.value}>
                    {len.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Season suitability */}
          <div>
            <label className="text-xs sm:text-sm font-semibold text-[#1A1918] block mb-2">Mùa thích hợp</label>
            <div className="flex flex-wrap gap-2">
              {SEASONS.map((s) => {
                const isSeasonActive = Array.isArray(attributes.season) && attributes.season.includes(s.value);
                return (
                  <button
                    key={s.value}
                    type="button"
                    disabled={!accepted}
                    onClick={() => handleSeasonToggle(s.value)}
                    className={`text-xs sm:text-sm px-4 py-1.5 rounded-full border transition font-mono ${
                      isSeasonActive
                        ? 'bg-[#1A1918] text-[#FBFBF9] border-[#1A1918] font-medium shadow-2xs'
                        : 'bg-[#FAF8F5] text-[#5C564E] border-[#E8E5DE] hover:border-[#D5D1C7] hover:text-[#1A1918]'
                    }`}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Functional flags */}
          <div>
            <label className="text-xs sm:text-sm font-semibold text-[#1A1918] block mb-2">
              Tính năng & Mục đích sử dụng (Thẻ chức năng)
            </label>
            <div className="flex flex-wrap gap-2">
              {FUNCTIONAL_FLAGS.map((f) => {
                const isFlagActive =
                  Array.isArray(attributes.functional_flags) && attributes.functional_flags.includes(f.value);
                return (
                  <button
                    key={f.value}
                    type="button"
                    disabled={!accepted}
                    onClick={() => handleFunctionalFlagToggle(f.value)}
                    className={`text-xs sm:text-sm px-3.5 py-1.5 rounded-full border transition font-mono ${
                      isFlagActive
                        ? 'bg-[#9C5234] text-[#FBFBF9] border-[#9C5234] font-medium shadow-2xs'
                        : 'bg-[#FAF8F5] text-[#5C564E] border-[#E8E5DE] hover:border-[#D5D1C7] hover:text-[#1A1918]'
                    }`}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
