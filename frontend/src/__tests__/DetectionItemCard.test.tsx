import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DetectionItemCard } from '@/components/ingestion/DetectionItemCard';
import taxonomy from './garment-taxonomy.fixture';
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
      <DetectionItemCard taxonomy={taxonomy}
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

    expect(screen.queryByText(/95%/)).toBeNull();
    expect(screen.queryByText(/45%/)).toBeNull();
    expect(screen.queryByText(/Mã AI/)).toBeNull();
    expect(screen.getByText('Cần kiểm tra', { exact: true })).toBeDefined();
    const summary = screen.getByText(/Chi tiết bổ sung/);
    expect(summary.textContent).toContain('Có thông tin cần kiểm tra');
    const details = summary.closest('details')!;
    expect(details.hasAttribute('open')).toBe(false);
    fireEvent.click(summary);
    expect(details.hasAttribute('open')).toBe(true);

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
      <DetectionItemCard taxonomy={taxonomy}
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
      <DetectionItemCard taxonomy={taxonomy}
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

    const categorySelect = screen.getByDisplayValue('Áo');
    fireEvent.change(categorySelect, { target: { value: 'skirt' } });
    expect(handleUpdate).toHaveBeenCalledWith('category', 'bottom');
    expect(handleUpdate).toHaveBeenCalledWith('sub_category', 'skirt');
  });

  it('omits garment length controls and their uncertainty for footwear', () => {
    const attributes = { ...mockDetection.attributes, category: 'footwear' };
    render(<DetectionItemCard taxonomy={taxonomy} detection={{ ...mockDetection, attributes, field_confidence: { length: .4 } }}
      attributes={attributes} index={0} isSelected={false} accepted={true}
      onSelect={vi.fn()} onToggleAccepted={vi.fn()} onUpdateAttribute={vi.fn()} />);
    expect(screen.queryByText('Độ dài')).toBeNull();
    expect(screen.queryByText(/Có thông tin cần kiểm tra/)).toBeNull();
  });
});
