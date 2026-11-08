import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TryOnModal } from '@/components/tryon/TryOnModal';
import * as api from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    createTryOn: vi.fn(),
    setOutfitBookmark: vi.fn(),
    getMediaUrl: vi.fn((path: string) => `http://media.test${path}`),
  };
});

const items = [
  { id: 'top-1', slot: 'top', name: 'Áo polo trắng', primaryColor: 'Trắng' },
  { id: 'bottom-1', slot: 'bottom', name: 'Quần chinos navy', primaryColor: 'Navy' },
];

describe('TryOnModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.setOutfitBookmark).mockResolvedValue({
      outfit_id: 'outfit-1',
      is_bookmarked: true,
      updated_at: '2026-09-17T08:00:00Z',
    });
  });

  it('renders generated lookbook, item list, and no forced rating controls', async () => {
    let resolveTryOn: (value: Awaited<ReturnType<typeof api.createTryOn>>) => void = () => undefined;
    vi.mocked(api.createTryOn).mockReturnValue(
      new Promise((resolve) => {
        resolveTryOn = resolve;
      })
    );
    const response = {
      tryon_id: 'tryon-1',
      outfit_id: 'outfit-1',
      image_url: '/api/v1/media/render-1',
      render_kind: 'generated_lookbook' as const,
      fallback_used: false,
      duration_ms: 420,
      status: 'ready' as const,
    };

    render(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={items}
        isBookmarked={false}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Đang tạo ảnh minh họa');
    });
    resolveTryOn(response);
    await waitFor(() => {
      expect(screen.getByText('Ảnh minh họa AI')).toBeDefined();
    });

    expect(screen.getByRole('dialog', { name: 'Xem trước bộ trang phục' })).toBeDefined();
    expect(screen.getByAltText('Ảnh minh họa AI cho bộ trang phục')).toBeDefined();
    expect(screen.getByText('Áo polo trắng')).toBeDefined();
    expect(screen.getByText('Quần chinos navy')).toBeDefined();
    expect(screen.queryByText(/Đánh giá/)).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('labels moodboard fallback, regenerates, bookmarks, and closes with Escape', async () => {
    vi.mocked(api.createTryOn).mockResolvedValue({
      tryon_id: 'tryon-fallback',
      outfit_id: 'outfit-1',
      image_url: '/api/v1/media/fallback-1',
      render_kind: 'moodboard',
      fallback_used: true,
      duration_ms: 38,
      status: 'ready',
    });
    const onClose = vi.fn();
    const onBookmarkChange = vi.fn();

    render(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={items}
        isBookmarked={false}
        onBookmarkChange={onBookmarkChange}
        onClose={onClose}
      />
    );

    await waitFor(() => expect(screen.getByText('Moodboard dự phòng')).toBeDefined());
    fireEvent.click(screen.getByRole('button', { name: 'Tạo lại ảnh minh họa' }));
    await waitFor(() => expect(api.createTryOn).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole('button', { name: 'Lưu bộ đồ' }));
    await waitFor(() => {
      expect(api.setOutfitBookmark).toHaveBeenCalledWith('outfit-1', true);
      expect(onBookmarkChange).toHaveBeenCalledWith('outfit-1', true);
    });

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows an inline error and allows retry', async () => {
    vi.mocked(api.createTryOn)
      .mockRejectedValueOnce(new api.ApiError('Không thể tạo ảnh minh họa.', 'TRYON_FAILED', 504))
      .mockResolvedValueOnce({
        tryon_id: 'tryon-retry',
        outfit_id: 'outfit-1',
        image_url: '/api/v1/media/retry-1',
        render_kind: 'generated_lookbook',
        fallback_used: false,
        duration_ms: 310,
        status: 'ready',
      });

    render(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={items}
        isBookmarked={false}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined());
    fireEvent.click(screen.getByRole('button', { name: 'Thử tạo lại' }));
    await waitFor(() => expect(screen.getByText('Ảnh minh họa AI')).toBeDefined());
  });

  it('supports avatar selection and renders virtual try-on with before/after toggle', async () => {
    vi.mocked(api.createTryOn).mockResolvedValue({
      tryon_id: 'tryon-vton-1',
      outfit_id: 'outfit-1',
      image_url: '/api/v1/media/vton-result',
      render_kind: 'virtual_tryon',
      fallback_used: false,
      duration_ms: 480,
      status: 'ready',
    });

    render(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={items}
        isBookmarked={false}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Ảnh mặc thử AI')).toBeDefined();
    });

    // Check before / after compare buttons
    expect(screen.getByText('Kết quả mặc thử AI')).toBeDefined();
    expect(screen.getByText('Ảnh mẫu gốc (Trước khi mặc)')).toBeDefined();

    // Switch to female avatar -> should trigger exactly 1 new createTryOn call (total 2), not duplicate
    fireEvent.click(screen.getByText('Nữ mẫu (Chuẩn)'));
    await waitFor(() => {
      expect(api.createTryOn).toHaveBeenCalledWith(
        'outfit-1',
        expect.objectContaining({ avatarId: 'preset-female' })
      );
    });
    expect(api.createTryOn).toHaveBeenCalledTimes(2);
  });

  it('does not abort or re-trigger generation when parent re-renders with a new items array reference', async () => {
    vi.mocked(api.createTryOn).mockResolvedValue({
      tryon_id: 'tryon-vton-stable',
      outfit_id: 'outfit-1',
      image_url: '/api/v1/media/vton-stable',
      render_kind: 'virtual_tryon',
      fallback_used: false,
      duration_ms: 350,
      status: 'ready',
    });

    const { rerender } = render(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={[...items]}
        isBookmarked={false}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Ảnh mặc thử AI')).toBeDefined();
    });
    expect(api.createTryOn).toHaveBeenCalledTimes(1);

    // Simulate parent re-render after bookmark toggle with freshly allocated items array
    rerender(
      <TryOnModal
        isOpen
        outfitId="outfit-1"
        items={items.map((item) => ({ ...item }))}
        isBookmarked={true}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(api.createTryOn).toHaveBeenCalledTimes(1);
  });

  it('handles layering toggle when both top and outerwear exist, plus footwear coordination', async () => {
    const layeredItems = [
      { id: 'top-1', slot: 'top', name: 'Áo sơ mi oxford', primaryColor: 'Trắng' },
      { id: 'outer-1', slot: 'outerwear', name: 'Áo blazer len', primaryColor: 'Xanh navy' },
      { id: 'bottom-1', slot: 'bottom', name: 'Quần âu', primaryColor: 'Đen' },
      { id: 'shoe-1', slot: 'footwear', name: 'Giày oxford', primaryColor: 'Nâu' },
      { id: 'acc-1', slot: 'accessory', name: 'Đồng hồ da', primaryColor: 'Bạc' },
    ];

    vi.mocked(api.createTryOn).mockResolvedValue({
      tryon_id: 'tryon-layer-1',
      outfit_id: 'outfit-layered',
      image_url: '/api/v1/media/layered-result',
      render_kind: 'virtual_tryon',
      fallback_used: false,
      duration_ms: 510,
      status: 'ready',
    });

    render(
      <TryOnModal
        isOpen
        outfitId="outfit-layered"
        items={layeredItems}
        isBookmarked={false}
        onBookmarkChange={vi.fn()}
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Ảnh mặc thử AI')).toBeDefined();
    });

    // Layering controls visible
    expect(screen.getByText('Ướm áo khoác ngoài')).toBeDefined();
    expect(screen.getByText('Ướm áo trong')).toBeDefined();

    // Footwear & accessories section visible
    expect(screen.getByText('Phối kèm (Giày & Phụ kiện)')).toBeDefined();
    expect(screen.getByText('Giày oxford')).toBeDefined();
    expect(screen.getByText('Đồng hồ da')).toBeDefined();

    // Toggle to inner top
    fireEvent.click(screen.getByText('Ướm áo trong'));
    await waitFor(() => {
      expect(api.createTryOn).toHaveBeenCalledWith(
        'outfit-layered',
        expect.objectContaining({
          itemIds: expect.arrayContaining(['top-1', 'bottom-1']),
        })
      );
    });
  });
});
