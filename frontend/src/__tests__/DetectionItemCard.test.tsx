import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DetectionItemCard } from '@/components/ingestion/DetectionItemCard';
import type { DetectionReviewItem, FashionAttributes } from '@/types/ingestion';

describe('DetectionItemCard', () => {
  const mockDetection: DetectionReviewItem = {
    detection_id: 'det-test-12345678',
    crop_url: '/api/v1/media/crop-1',
    bounding_box: [0.1, 0.1, 0.8, 0.8],
    attributes: {
      category: 'top',
      sub_category: 't-shirt',
      primary_color: 'white',
      pattern: '',
      material: '',
      style: '',
      fit: '',
      formality_level: 2,
      season: ['summer'],
    },
    field_confidence: {
      category: 0.95,
      sub_category: 0.85,
      primary_color: 0.90,
      pattern: 0.45,
    },
  };

  it('renders confidence badges correctly according to threshold', () => {
    render(
      <DetectionItemCard
        detection={mockDetection}
        index={0}
        isSelected={false}
        accepted={true}
        attributes={mockDetection.attributes}
        onSelect={vi.fn()}
        onToggleAccepted={vi.fn()}
        onUpdateAttribute={vi.fn()}
      />
    );

    // High confidence (>= 70%)
    expect(screen.getByText(/✓ 95% \(AI nhận diện\)/)).toBeDefined();

    // Low confidence (< 70%)
    expect(screen.getByText(/⚠️ Cần kiểm tra/)).toBeDefined();
    expect(screen.getByText(/\(45%\)/)).toBeDefined();

    // Undefined confidence -> "Chưa xác định"
    const unverifiedBadges = screen.getAllByText('Chưa xác định');
    expect(unverifiedBadges.length).toBeGreaterThan(0);
  });

  it('does not apply speculative default values to dropdown selects', () => {
    const emptyAttributes: FashionAttributes = {
      category: '',
      sub_category: '',
      primary_color: '',
      pattern: '',
      material: '',
      style: '',
      fit: '',
      season: [],
    };

    render(
      <DetectionItemCard
        detection={{ ...mockDetection, attributes: emptyAttributes }}
        index={0}
        isSelected={false}
        accepted={true}
        attributes={emptyAttributes}
        onSelect={vi.fn()}
        onToggleAccepted={vi.fn()}
        onUpdateAttribute={vi.fn()}
      />
    );

    const placeholderOptions = screen.getAllByText('-- Chưa xác định / Vui lòng chọn --');
    // Pattern, Material, Style, Fit
    expect(placeholderOptions.length).toBe(4);

    // Category should have required placeholder
    expect(screen.getByText('-- Chọn danh mục (Bắt buộc) --')).toBeDefined();

    // Red warning for missing category
    expect(
      screen.getByText('Vui lòng chọn danh mục chính để lưu món đồ này.')
    ).toBeDefined();
  });

  it('triggers onUpdateAttribute when user changes selection', () => {
    const handleUpdate = vi.fn();
    render(
      <DetectionItemCard
        detection={mockDetection}
        index={0}
        isSelected={false}
        accepted={true}
        attributes={mockDetection.attributes}
        onSelect={vi.fn()}
        onToggleAccepted={vi.fn()}
        onUpdateAttribute={handleUpdate}
      />
    );

    const categorySelect = screen.getByDisplayValue('Áo (Top)');
    fireEvent.change(categorySelect, { target: { value: 'bottom' } });
    expect(handleUpdate).toHaveBeenCalledWith('category', 'bottom');
  });
});
