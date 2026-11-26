import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { DetectionItemCard } from '@/components/ingestion/DetectionItemCard';
import { hasGarmentLength } from '@/lib/garmentAttributes';
import { attributeLabel, colorFromInput, colorInputValue } from '@/lib/preferenceLabels';
import { initialPresetId, rememberPresetId } from '@/lib/tryonAvatar';
import taxonomy from './garment-taxonomy.fixture';
import type { DetectionReviewItem } from '@/types/ingestion';

describe('colour labels', () => {
  it('labels colours the vision provider returns beyond the preference palette', () => {
    expect(attributeLabel('charcoal')).toBe('Xám than');
    expect(attributeLabel('dark_gray')).toBe('Xám đậm');
    expect(attributeLabel('teal')).toBe('Xanh mòng két');
    expect(attributeLabel('light blue')).toBe('Xanh nhạt');
    expect(attributeLabel('smart casual')).toBe('Thanh lịch thường ngày');
  });

  it('shows known colours in Vietnamese and maps typed labels back to canonical values', () => {
    expect(colorInputValue('white')).toBe('Trắng');
    expect(colorInputValue('dusty rose')).toBe('dusty rose');
    expect(colorFromInput('xanh navy')).toBe('navy');
    expect(colorFromInput('Xám')).toBe('grey');
    expect(colorFromInput('xanh ngọc')).toBe('xanh ngọc');
  });
});

describe('garment length', () => {
  it('applies to body garments only', () => {
    expect(hasGarmentLength('top')).toBe(true);
    expect(hasGarmentLength('dress')).toBe(true);
    expect(hasGarmentLength('footwear')).toBe(false);
    expect(hasGarmentLength('accessory')).toBe(false);
  });
});

describe('review card wording', () => {
  const detection: DetectionReviewItem = {
    detection_id: 'det-1',
    crop_url: '/api/v1/media/crop-1',
    bounding_box: [0.1, 0.1, 0.8, 0.8],
    attributes: { category: 'top', sub_category: 'shirt', primary_color: 'white', season: [] },
    field_confidence: {},
  };

  it('shows the Vietnamese type and colour while storing canonical values', () => {
    const update = vi.fn();
    render(
      <DetectionItemCard taxonomy={taxonomy} detection={detection} index={0} isSelected={false} accepted
        attributes={detection.attributes} onSelect={vi.fn()} onToggleAccepted={vi.fn()} onUpdateAttribute={update} />
    );

    expect(screen.getByRole('heading', { level: 4 }).textContent).toBe('Áo sơ mi');
    expect(screen.getByDisplayValue('Áo sơ mi')).toBeDefined();
    const color = screen.getByDisplayValue('Trắng');
    expect(screen.queryByDisplayValue('shirt')).toBeNull();
    expect(screen.queryByDisplayValue('white')).toBeNull();

    fireEvent.change(color, { target: { value: 'Đen' } });
    expect(update).toHaveBeenCalledWith('primary_color', 'black');
    fireEvent.change(screen.getByDisplayValue('Áo sơ mi'), { target: { value: 'Áo Polo' } });
    expect(update).toHaveBeenCalledWith('sub_category', 'polo');
  });
});

describe('try-on preset choice', () => {
  afterEach(() => localStorage.clear());

  it('starts a dress outfit on the female preset and remembers an explicit preset choice', () => {
    expect(initialPresetId([{ slot: 'dress' }, { slot: 'footwear' }])).toBe('preset-female');
    expect(initialPresetId([{ slot: 'top' }, { slot: 'bottom' }])).toBe('preset-male');

    rememberPresetId('preset-female');
    expect(initialPresetId([{ slot: 'top' }, { slot: 'bottom' }])).toBe('preset-female');

    rememberPresetId('user-avatar-123');
    expect(initialPresetId([{ slot: 'top' }])).toBe('preset-female');
  });
});
