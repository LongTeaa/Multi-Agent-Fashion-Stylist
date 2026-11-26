'use client';

import React from 'react';
import type { DetectionReviewItem, FashionAttributes } from '@/types/ingestion';
import type { GarmentTaxonomy } from '@/types/wardrobe';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import { SegmentedScale } from '@/components/ui/SegmentedScale';
import { FUNCTIONAL_FLAG_VALUES, hasGarmentLength, type FunctionalFlag } from '@/lib/garmentAttributes';
import { colorFromInput, colorInputValue } from '@/lib/preferenceLabels';

interface DetectionItemCardProps {
  cropEditor?: React.ReactNode;
  detection: DetectionReviewItem;
  taxonomy?: GarmentTaxonomy;
  index: number;
  isSelected: boolean;
  accepted: boolean;
  attributes: FashionAttributes;
  onSelect: () => void;
  onToggleAccepted: (accepted: boolean) => void;
  onUpdateAttribute: (key: string, value: unknown) => void;
}

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

// Longer, explanatory labels for the review step; the flag set itself is shared.
const FUNCTIONAL_FLAG_REVIEW_LABELS: Record<FunctionalFlag, string> = {
  movement: 'Vận động / Co giãn',
  outdoor: 'Dã ngoại / Ngoài trời',
  sun: 'Chống nắng',
  water_resistant: 'Chống mưa / Nước',
  work: 'Đi làm / Công sở',
  sport: 'Thể thao',
  protection: 'Bảo hộ / Giữ nhiệt',
  light: 'Siêu nhẹ / Thoáng',
  heavy: 'Dày ấm / Nặng',
};

const FUNCTIONAL_FLAGS = FUNCTIONAL_FLAG_VALUES.map((value) => ({
  value,
  label: FUNCTIONAL_FLAG_REVIEW_LABELS[value],
}));

const COMFORT_LABELS: Record<number, string> = {
  1: 'Gò bó / Thô cứng (1)',
  2: 'Hơi hạn chế (2)',
  3: 'Tiêu chuẩn (3)',
  4: 'Thoải mái (4)',
  5: 'Rất thoải mái / Co giãn (5)',
};

export function DetectionItemCard({
  cropEditor,
  detection,
  taxonomy = { groups: [] },
  index,
  isSelected,
  accepted,
  attributes,
  onSelect,
  onToggleAccepted,
  onUpdateAttribute,
}: DetectionItemCardProps) {
  const fold = (value: string) => value.toLowerCase().replaceAll('đ', 'd').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  const categoryGroups = taxonomy.groups.filter((group) => group.category === attributes.category);
  const selectedGroup = categoryGroups.find((group) => [group.value, group.label, ...group.aliases,
    ...group.types.flatMap((type) => [type.value, type.label, ...type.aliases])]
    .some((alias) => fold(alias) === fold(attributes.sub_category || '')))
    || categoryGroups[0];
  const fieldId = (field: string) => `detection-${detection.detection_id}-${field}`;
  const suggestions = selectedGroup?.types || [];
  // Canonical values stay stored; known types and colours are shown and typed in Vietnamese.
  const selectedType = suggestions.find((type) => [type.value, type.label, ...type.aliases]
    .some((alias) => fold(alias) === fold(attributes.sub_category || '')));
  const subCategoryDisplay = selectedType ? selectedType.label : attributes.sub_category || '';
  const subCategoryFromInput = (text: string) =>
    suggestions.find((type) => fold(type.label) === fold(text))?.value ?? text;
  const confidences = detection.field_confidence || {};
  const cropUrl = detection.crop_url;

  const isLowConfidence = (field: string) => {
    if (field === 'length' && !hasGarmentLength(attributes.category)) return false;
    const conf = confidences[field];
    return typeof conf === 'number' && conf < 0.70 && attributes[field] === detection.attributes[field];
  };

  const advancedFields = ['pattern', 'material', 'style', 'fit', 'formality_level', 'comfort_level', 'silhouette_level', 'length'];
  const advancedNeedsReview = advancedFields.some(isLowConfidence);
  const renderConfidenceBadge = (field: string) => isLowConfidence(field)
    ? <span className="text-xs font-semibold text-warning">Cần kiểm tra</span>
    : null;

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

  const isMissingCategory = !attributes.category || attributes.category === 'unknown';
  const fieldClass = (field: string, missing = false) =>
    `field ${missing ? 'border-danger bg-danger-soft/40' : isLowConfidence(field) ? 'border-warning bg-warning-soft/50' : ''}`;

  return (
    <div
      onClick={onSelect}
      className={`card overflow-hidden transition-[border-color,box-shadow,opacity] ${
        isSelected ? 'border-ink shadow-[0_10px_30px_-18px_rgb(28_25_22/0.35)]' : ''
      } ${!accepted ? 'opacity-60' : ''}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="hang-tag">{String(index + 1).padStart(2, '0')}</span>
          <h4 className="truncate text-[1rem] font-semibold capitalize text-ink">
            {selectedType ? selectedType.label : `${selectedGroup?.label || 'Món đồ'} · ${attributes.sub_category || 'Chưa phân loại'}`}
          </h4>
        </div>

        <label onClick={(e) => e.stopPropagation()} className="relative flex shrink-0 cursor-pointer select-none items-center gap-2.5">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => onToggleAccepted(e.target.checked)}
            className="peer sr-only"
          />
          <span className="relative h-6 w-11 rounded-full bg-line-strong transition-colors after:absolute after:left-[3px] after:top-[3px] after:h-[18px] after:w-[18px] after:rounded-full after:bg-surface after:shadow-sm after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-5 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent" />
          <span className="text-sm font-semibold text-ink">{accepted ? 'Lưu món này' : 'Bỏ qua'}</span>
        </label>
      </div>

      <div className="flex flex-col gap-6 p-5 md:flex-row">
        {/* Crop preview */}
        <div className="flex shrink-0 flex-col items-center md:items-start">
          <div className="flex h-40 w-40 items-center justify-center overflow-hidden rounded-2xl bg-sunken sm:h-44 sm:w-44">
            {cropUrl ? (
              <PrivateMediaImage source={cropUrl} alt="Ảnh món đồ đã cắt" className="h-full w-full object-contain p-2" />
            ) : (
              <span className="text-xs text-muted">Không có ảnh</span>
            )}
          </div>
          {cropEditor && <div className="mt-3 w-full max-w-sm">{cropEditor}</div>}
        </div>

        {/* Attribute correction */}
        <div className="min-w-0 flex-1 space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* Category */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor={fieldId('category')} className="field-label mb-0">
                  Danh mục chính <span className="text-danger">*</span>
                </label>
                {renderConfidenceBadge('category')}
              </div>
              <select id={fieldId('category')}
                value={selectedGroup?.value || ''}
                disabled={!accepted}
                onChange={(e) => {
                  const group = taxonomy.groups.find((entry) => entry.value === e.target.value);
                  if (group) {
                    onUpdateAttribute('category', group.category);
                    onUpdateAttribute('sub_category', group.value);
                  }
                }}
                className={fieldClass('category', isMissingCategory)}
              >
                <option value="" disabled>
                  -- Chọn danh mục (Bắt buộc) --
                </option>
                {taxonomy.groups.map((cat) => (
                  <option key={cat.value} value={cat.value}>
                    {cat.label}
                  </option>
                ))}
              </select>
              {isMissingCategory && accepted && (
                <p className="mt-1.5 text-xs font-medium text-danger">Vui lòng chọn danh mục chính để lưu món đồ này.</p>
              )}
            </div>

            {/* Sub-category */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor={fieldId('sub_category')} className="field-label mb-0">Loại món</label>
                {renderConfidenceBadge('sub_category')}
              </div>
              <input id={fieldId('sub_category')}
                type="text"
                list={`sub-suggestions-${index}`}
                value={subCategoryDisplay}
                disabled={!accepted}
                placeholder="VD: Áo thun, Quần jeans, Giày sneaker…"
                onChange={(e) => onUpdateAttribute('sub_category', subCategoryFromInput(e.target.value))}
                className={fieldClass('sub_category')}
              />
              <datalist id={`sub-suggestions-${index}`}>
                {suggestions.map((s) => (
                  <option key={s.value} value={s.label} />
                ))}
              </datalist>
              {suggestions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {suggestions.map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      disabled={!accepted}
                      aria-pressed={attributes.sub_category?.toLowerCase() === s.value.toLowerCase()}
                      onClick={() => onUpdateAttribute('sub_category', s.value)}
                      className="chip min-h-8 px-2.5 text-xs"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Primary color */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor={fieldId('primary_color')} className="field-label mb-0">Màu sắc chủ đạo</label>
                {renderConfidenceBadge('primary_color')}
              </div>
              <input id={fieldId('primary_color')}
                type="text"
                value={colorInputValue(attributes.primary_color)}
                disabled={!accepted}
                placeholder="VD: Trắng, Đen, Xanh navy, Be…"
                onChange={(e) => onUpdateAttribute('primary_color', colorFromInput(e.target.value))}
                className={fieldClass('primary_color')}
              />
            </div>
          </div>

          <details className="group border-t border-line pt-4">
            <summary className="cursor-pointer list-none rounded-lg text-sm font-semibold text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
              <span className="inline-block transition-transform group-open:rotate-90" aria-hidden="true">
                ›
              </span>{' '}
              Chi tiết bổ sung{advancedNeedsReview ? ' · Có thông tin cần kiểm tra' : ''}
            </summary>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Pattern */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('pattern')} className="field-label mb-0">Họa tiết</label>
                  {renderConfidenceBadge('pattern')}
                </div>
                <select id={fieldId('pattern')}
                  value={attributes.pattern || ''}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('pattern', e.target.value)}
                  className={fieldClass('pattern')}
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
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('material')} className="field-label mb-0">Chất liệu</label>
                  {renderConfidenceBadge('material')}
                </div>
                <select id={fieldId('material')}
                  value={attributes.material || ''}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('material', e.target.value)}
                  className={fieldClass('material')}
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
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('style')} className="field-label mb-0">Phong cách</label>
                  {renderConfidenceBadge('style')}
                </div>
                <select id={fieldId('style')}
                  value={attributes.style || ''}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('style', e.target.value)}
                  className={fieldClass('style')}
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
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('fit')} className="field-label mb-0">Phom dáng</label>
                  {renderConfidenceBadge('fit')}
                </div>
                <select id={fieldId('fit')}
                  value={attributes.fit || ''}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('fit', e.target.value)}
                  className={fieldClass('fit')}
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

              {/* Formality */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('formality_level')} className="field-label mb-0">
                    Mức độ trang trọng:{' '}
                    <span className="text-accent">
                      {attributes.formality_level ? `${attributes.formality_level}/5` : 'Chưa xác định'}
                    </span>
                  </label>
                  {renderConfidenceBadge('formality_level')}
                </div>
                <input id={fieldId('formality_level')}
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={attributes.formality_level || 3}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('formality_level', parseInt(e.target.value, 10))}
                  className="h-2 w-full cursor-pointer accent-[var(--color-ink)]"
                  aria-label="Mức độ trang trọng"
                />
                <div className="mt-1 flex justify-between text-xs text-muted">
                  <span>Thường ngày</span>
                  <span>Bán trang trọng</span>
                  <span>Dạ tiệc</span>
                </div>
              </div>

              {/* Comfort */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="field-label mb-0">
                    Độ thoải mái:{' '}
                    <span className="text-accent">
                      {attributes.comfort_level ? `${attributes.comfort_level}/5` : 'Chưa xác định'}
                    </span>
                  </span>
                  {renderConfidenceBadge('comfort_level')}
                </div>
                <SegmentedScale
                  label="Độ thoải mái"
                  value={attributes.comfort_level || 3}
                  onChange={(level) => onUpdateAttribute('comfort_level', level)}
                  disabled={!accepted}
                />
                <p className="mt-1 text-xs text-muted">
                  {COMFORT_LABELS[attributes.comfort_level || 3] || 'Tiêu chuẩn (3)'}
                </p>
              </div>

              {/* Silhouette */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor={fieldId('silhouette_level')} className="field-label mb-0">Dáng tổng thể</label>
                  {renderConfidenceBadge('silhouette_level')}
                </div>
                <select id={fieldId('silhouette_level')}
                  value={attributes.silhouette_level || 3}
                  disabled={!accepted}
                  onChange={(e) => onUpdateAttribute('silhouette_level', parseInt(e.target.value, 10))}
                  className={fieldClass('silhouette_level')}
                >
                  {SILHOUETTES.map((sil) => (
                    <option key={sil.value} value={sil.value}>
                      {sil.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Length applies to garments, not shoes or accessories. */}
              {hasGarmentLength(attributes.category) && (
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label htmlFor={fieldId('length')} className="field-label mb-0">Độ dài</label>
                    {renderConfidenceBadge('length')}
                  </div>
                  <select id={fieldId('length')}
                    value={attributes.length || 'hip'}
                    disabled={!accepted}
                    onChange={(e) => onUpdateAttribute('length', e.target.value)}
                    className={fieldClass('length')}
                  >
                    {LENGTHS.map((len) => (
                      <option key={len.value} value={len.value}>
                        {len.label}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {/* Seasons */}
            <div className="mt-5">
              <span className="field-label">Mùa thích hợp</span>
              <div className="flex flex-wrap gap-2">
                {SEASONS.map((s) => {
                  const isSeasonActive = Array.isArray(attributes.season) && attributes.season.includes(s.value);
                  return (
                    <button
                      key={s.value}
                      type="button"
                      disabled={!accepted}
                      aria-pressed={isSeasonActive}
                      onClick={() => handleSeasonToggle(s.value)}
                      className="chip"
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Functional flags */}
            <div className="mt-5">
              <span className="field-label">Công dụng</span>
              <div className="flex flex-wrap gap-2">
                {FUNCTIONAL_FLAGS.map((f) => {
                  const isFlagActive =
                    Array.isArray(attributes.functional_flags) && attributes.functional_flags.includes(f.value);
                  return (
                    <button
                      key={f.value}
                      type="button"
                      disabled={!accepted}
                      aria-pressed={isFlagActive}
                      onClick={() => handleFunctionalFlagToggle(f.value)}
                      className="chip"
                    >
                      {f.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
