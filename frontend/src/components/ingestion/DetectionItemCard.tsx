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
  { value: 'dress', label: 'Đầm liền (Dress)' },
  { value: 'accessory', label: 'Phụ kiện (Accessory)' },
];

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
        <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#FAF8F5] text-[#736E65] border border-[#E8E5DE]">
          Chưa xác định
        </span>
      );
    }
    const isLow = conf < 0.70;
    const percentage = Math.round(conf * 100);

    return (
      <span
        className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${
          isLow
            ? 'bg-amber-100 text-amber-800 border border-amber-300 animate-pulse'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
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

  return (
    <div
      onClick={onSelect}
      className={`rounded-2xl border transition-all duration-200 overflow-hidden ${
        isSelected
          ? 'border-[#1A1918] ring-2 ring-[#1A1918]/15 shadow-md bg-white'
          : 'border-[#E8E5DE] bg-white hover:border-[#D5D1C7] shadow-2xs'
      } ${!accepted ? 'opacity-60 bg-[#FAF8F5]' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#E8E5DE] bg-[#FAF8F5]/80">
        <div className="flex items-center gap-3">
          <span className="w-7 h-7 rounded-full bg-[#1A1918] text-[#FBFBF9] font-mono font-semibold text-xs flex items-center justify-center shadow-2xs">
            {index + 1}
          </span>
          <div>
            <h4 className="text-sm font-semibold text-[#1A1918] capitalize">
              {CATEGORIES.find((c) => c.value === attributes.category)?.label.split(' ')[0] || attributes.category || 'Món đồ'} •{' '}
              {attributes.sub_category || 'Chưa phân loại'}
            </h4>
            <p className="text-xs font-mono text-[#736E65]">Mã AI: {detection.detection_id.slice(0, 8)}</p>
          </div>
        </div>

        {/* Accept / Reject Switch */}
        <label
          onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-2 cursor-pointer select-none"
        >
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => onToggleAccepted(e.target.checked)}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-[#E8E5DE] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-[#D5D1C7] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#9C5234]"></div>
          <span className="text-xs font-mono text-[#5C564E]">
            {accepted ? 'Lưu món này' : 'Bỏ qua'}
          </span>
        </label>
      </div>

      <div className="p-5 flex flex-col md:flex-row gap-6">
        {/* Crop Preview Column */}
        <div className="flex flex-col items-center flex-shrink-0">
          <div className="w-36 h-36 rounded-xl border border-slate-200 overflow-hidden bg-slate-100 flex items-center justify-center shadow-inner relative group">
            {cropUrl ? (
              <PrivateMediaImage
                source={cropUrl}
                alt="Cropped item"
                className="w-full h-full object-contain p-1"
              />
            ) : (
              <span className="text-xs text-slate-400">Không có ảnh</span>
            )}
            <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition flex items-center justify-center text-white text-[11px] font-medium">
              Ảnh cắt tự động
            </div>
          </div>
          <span className="mt-2 text-[11px] text-slate-500">Kích thước vùng crop</span>
        </div>

        {/* Attribute Correction Form Fields */}
        <div className="flex-1 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Category */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">
                  Danh mục chính <span className="text-red-500">*</span>
                </label>
                {renderConfidenceBadge('category')}
              </div>
              <select
                value={attributes.category || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('category', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  !attributes.category || attributes.category === 'unknown'
                    ? 'border-red-400 bg-red-50/20 focus:ring-2 focus:ring-red-400'
                    : isLowConfidence('category')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
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
                <p className="text-[11px] text-red-600 mt-1 font-medium">
                  Vui lòng chọn danh mục chính để lưu món đồ này.
                </p>
              )}
            </div>

            {/* Sub-Category */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Loại chi tiết (Sub-category)</label>
                {renderConfidenceBadge('sub_category')}
              </div>
              <input
                type="text"
                value={attributes.sub_category || ''}
                disabled={!accepted}
                placeholder="VD: polo, chinos, t-shirt, jeans..."
                onChange={(e) => onUpdateAttribute('sub_category', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('sub_category')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
                }`}
              />
            </div>

            {/* Primary Color */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Màu sắc chủ đạo</label>
                {renderConfidenceBadge('primary_color')}
              </div>
              <input
                type="text"
                value={attributes.primary_color || ''}
                disabled={!accepted}
                placeholder="VD: trắng, đen, navy, be..."
                onChange={(e) => onUpdateAttribute('primary_color', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('primary_color')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
                }`}
              />
            </div>

            {/* Pattern */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Họa tiết (Pattern)</label>
                {renderConfidenceBadge('pattern')}
              </div>
              <select
                value={attributes.pattern || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('pattern', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('pattern')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
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
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Chất liệu (Material)</label>
                {renderConfidenceBadge('material')}
              </div>
              <select
                value={attributes.material || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('material', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('material')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
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
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Phong cách (Style)</label>
                {renderConfidenceBadge('style')}
              </div>
              <select
                value={attributes.style || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('style', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('style')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
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
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-slate-700">Phom dáng (Fit)</label>
                {renderConfidenceBadge('fit')}
              </div>
              <select
                value={attributes.fit || ''}
                disabled={!accepted}
                onChange={(e) => onUpdateAttribute('fit', e.target.value)}
                className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none transition ${
                  isLowConfidence('fit')
                    ? 'border-amber-400 bg-amber-50/20 focus:ring-2 focus:ring-amber-400'
                    : 'border-slate-300 bg-white focus:ring-2 focus:ring-indigo-500'
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
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold text-[#1A1918]">
                  Mức độ trang trọng:{' '}
                  <span className="font-bold text-[#9C5234]">
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
                className="w-full accent-[#9C5234] cursor-pointer"
              />
              <div className="flex justify-between text-[10px] font-mono text-[#736E65] mt-0.5">
                <span>Thường ngày (1)</span>
                <span>Bán trang trọng (3)</span>
                <span>Dạ tiệc (5)</span>
              </div>
            </div>
          </div>

          {/* Season suitability */}
          <div>
            <label className="text-xs font-semibold text-[#1A1918] block mb-1.5">Mùa thích hợp</label>
            <div className="flex flex-wrap gap-2">
              {SEASONS.map((s) => {
                const isSeasonActive = Array.isArray(attributes.season) && attributes.season.includes(s.value);
                return (
                  <button
                    key={s.value}
                    type="button"
                    disabled={!accepted}
                    onClick={() => handleSeasonToggle(s.value)}
                    className={`text-xs px-3.5 py-1 rounded-full border transition font-mono ${
                      isSeasonActive
                        ? 'bg-[#1A1918] text-[#FBFBF9] border-[#1A1918] font-medium shadow-2xs'
                        : 'bg-[#FAF8F5] text-[#5C564E] border-[#E8E5DE] hover:border-[#D5D1C7]'
                    }`}
                  >
                    {s.label}
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
