import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OutfitCard, normalizeStylistItems, normalizeDetailItems, generateUUIDv4 } from '@/components/outfits/OutfitCard';
import * as api from '@/lib/api';
import type { OutfitWornResponseData } from '@/types/outfits';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    setOutfitBookmark: vi.fn(),
    recordOutfitWorn: vi.fn(),
  };
});

describe('OutfitCard Component', () => {
  const mockItems = [
    {
      id: 'item-1',
      slot: 'top',
      name: 'Áo sơ mi Oxford xanh pastel',
      imageUrl: '/media/items/top1.jpg',
      category: 'top',
      subCategory: 'shirt',
      primaryColor: 'Xanh pastel',
      isActive: true,
    },
    {
      id: 'item-2',
      slot: 'bottom',
      name: 'Quần tây xếp ly ghi sáng',
      imageUrl: null,
      category: 'bottom',
      subCategory: 'trouser',
      primaryColor: 'Ghi sáng',
      isActive: true,
    },
    {
      id: 'item-3',
      slot: 'shoes',
      name: 'Giày Penny Loafer da nâu',
      imageUrl: '/media/items/shoes1.jpg',
      category: 'shoes',
      subCategory: 'loafer',
      primaryColor: 'Nâu cognac',
      isActive: false, // Inactive / deleted item test
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('normalizes stylist and detail items accurately', () => {
    const stylistItems = [
      {
        item_id: 's-1',
        slot: 'top' as const,
        name: 'Áo thun',
        image_url: 'http://img.jpg',
      },
    ];
    const normalizedS = normalizeStylistItems(stylistItems);
    expect(normalizedS).toEqual([
      {
        id: 's-1',
        slot: 'top',
        name: 'Áo thun',
        imageUrl: 'http://img.jpg',
        isActive: true,
      },
    ]);

    const detailItems = [
      {
        wardrobe_item_id: 'd-1',
        slot_role: 'bottom' as const,
        name: 'Quần jeans',
        image_url: null,
        category: 'bottom' as const,
        sub_category: 'jeans',
        primary_color: 'Xanh navy',
        secondary_color: null,
        pattern: 'trơn',
        material: 'denim',
        style: 'casual',
        is_active: false,
      },
    ];
    const normalizedD = normalizeDetailItems(detailItems);
    expect(normalizedD).toEqual([
      {
        id: 'd-1',
        slot: 'bottom',
        name: 'Quần jeans',
        imageUrl: null,
        category: 'bottom',
        subCategory: 'jeans',
        primaryColor: 'Xanh navy',
        isActive: false,
      },
    ]);
  });

  it('renders card with rank, match percentage, slots, and stylist explanation', () => {
    render(
      <OutfitCard
        outfitId="outfit-101"
        rank={1}
        compositeScore={0.94}
        explanationVi="Set đồ hài hòa chuẩn thanh lịch cho buổi hẹn hò cà phê."
        appliedPreferences={['Thanh lịch', 'Gam màu dịu']}
        items={mockItems}
        initialIsBookmarked={false}
        initialTimesWorn={2}
      />
    );

    // Verify Rank and Score
    expect(screen.getByText('#1')).toBeDefined();
    expect(screen.getByText('94%')).toBeDefined();
    expect(screen.getByText('phù hợp')).toBeDefined();

    // Verify Explanation
    expect(
      screen.getByText(/Set đồ hài hòa chuẩn thanh lịch cho buổi hẹn hò cà phê/i)
    ).toBeDefined();

    // Verify Slots and Names
    expect(screen.getByText('Áo sơ mi Oxford xanh pastel')).toBeDefined();
    expect(screen.getByText('Quần tây xếp ly ghi sáng')).toBeDefined();
    expect(screen.getByText('Giày Penny Loafer da nâu')).toBeDefined();

    // Verify Alt Text for items with images
    const topImg = screen.getByAltText('Ảnh của Áo sơ mi Oxford xanh pastel (Áo)');
    expect(topImg).toBeDefined();
    expect(topImg.getAttribute('src')).toContain('/media/items/top1.jpg');

    // Verify fallback when no image
    expect(screen.getByText('Không có ảnh')).toBeDefined();

    // Verify inactive garment indication
    expect(screen.getByText('Đã xóa khỏi tủ')).toBeDefined();

    // Verify applied preferences
    expect(screen.getByText('✓ Thanh lịch')).toBeDefined();
    expect(screen.getByText('✓ Gam màu dịu')).toBeDefined();

    // Verify times worn header/footer badges
    expect(screen.getAllByText(/Đã mặc 2 lần/i).length).toBeGreaterThanOrEqual(1);
  });

  it('CONTRACT INVARIANT: strictly does NOT contain Like/Dislike or rating controls', () => {
    render(
      <OutfitCard
        outfitId="outfit-101"
        explanationVi="Phối đồ đơn giản"
        items={mockItems}
      />
    );

    // No like / dislike / rating controls in Task 5.8
    expect(screen.queryByRole('button', { name: /thích/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /không thích/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /đánh giá/i })).toBeNull();
    expect(screen.queryByRole('radio')).toBeNull();
  });

  it('performs optimistic bookmark toggle and invokes onBookmarkChange callback', async () => {
    vi.mocked(api.setOutfitBookmark).mockResolvedValueOnce({
      outfit_id: 'outfit-101',
      is_bookmarked: true,
      updated_at: '2026-09-15T08:00:00Z',
    });

    const onBookmarkChange = vi.fn();

    render(
      <OutfitCard
        outfitId="outfit-101"
        explanationVi="Phối đồ thanh lịch"
        items={mockItems}
        initialIsBookmarked={false}
        onBookmarkChange={onBookmarkChange}
      />
    );

    const bookmarkBtn = screen.getByRole('button', { name: /Lưu bộ đồ này/i });
    expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('false');

    // Click bookmark button
    fireEvent.click(bookmarkBtn);

    // Optimistic immediate update
    expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('true');
    expect(onBookmarkChange).toHaveBeenCalledWith('outfit-101', true);
    expect(api.setOutfitBookmark).toHaveBeenCalledWith('outfit-101', true);

    await waitFor(() => {
      expect(bookmarkBtn.getAttribute('aria-label')).toBe('Bỏ lưu bộ đồ này');
    });
  });

  it('rolls back bookmark state and displays error if API fails', async () => {
    vi.mocked(api.setOutfitBookmark).mockRejectedValueOnce(
      new api.ApiError('Lỗi kết nối máy chủ', 'NETWORK_ERROR', 500)
    );

    const onBookmarkChange = vi.fn();

    render(
      <OutfitCard
        outfitId="outfit-101"
        explanationVi="Phối đồ thanh lịch"
        items={mockItems}
        initialIsBookmarked={false}
        onBookmarkChange={onBookmarkChange}
      />
    );

    const bookmarkBtn = screen.getByRole('button', { name: /Lưu bộ đồ này/i });
    fireEvent.click(bookmarkBtn);

    // Optimistic state
    expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('true');

    // Wait for rollback
    await waitFor(() => {
      expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('false');
      expect(screen.getByRole('alert')).toBeDefined();
      expect(screen.getByText('Lỗi kết nối máy chủ')).toBeDefined();
    });

    // onBookmarkChange rollback notification
    expect(onBookmarkChange).toHaveBeenLastCalledWith('outfit-101', false);
  });

  it('records worn action idempotently and disables button while pending', async () => {
    let resolvePromise: (val: OutfitWornResponseData) => void;
    const pendingPromise = new Promise<OutfitWornResponseData>((resolve) => {
      resolvePromise = resolve;
    });

    vi.mocked(api.recordOutfitWorn).mockReturnValueOnce(pendingPromise);

    const onWearSuccess = vi.fn();

    render(
      <OutfitCard
        outfitId="outfit-101"
        explanationVi="Phối đồ thanh lịch"
        items={mockItems}
        initialTimesWorn={0}
        onWearSuccess={onWearSuccess}
      />
    );

    const wearBtn = screen.getByRole('button', {
      name: /Xác nhận đã mặc bộ trang phục này hôm nay/i,
    });
    expect(wearBtn).toBeDefined();

    // Click wear button
    fireEvent.click(wearBtn);

    // Check loading state: button disabled
    expect(wearBtn.hasAttribute('disabled')).toBe(true);
    expect(screen.getByText('Đang ghi nhận...')).toBeDefined();

    // Verify first API call had compliant UUID v4 idempotency key
    expect(api.recordOutfitWorn).toHaveBeenCalledTimes(1);
    const firstCallArgs = vi.mocked(api.recordOutfitWorn).mock.calls[0];
    expect(firstCallArgs[0]).toBe('outfit-101');
    const firstKey = firstCallArgs[1].idempotency_key;
    expect(typeof firstKey).toBe('string');
    expect(firstKey).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );

    // Resolve API call
    resolvePromise!({
      wear_log_id: 'wear-log-0',
      outfit_id: 'outfit-101',
      times_worn: 1,
      already_processed: false,
      worn_at: '2026-09-15T08:30:00Z',
    });

    await waitFor(() => {
      expect(screen.getByText(/Đã ghi nhận bạn mặc bộ này!/i)).toBeDefined();
    });

    expect(wearBtn.hasAttribute('disabled')).toBe(false);
    expect(screen.getAllByText(/Đã mặc 1 lần/i).length).toBeGreaterThanOrEqual(1);
    expect(onWearSuccess).toHaveBeenCalledWith('outfit-101', 1);
  });

  it('preserves same idempotency key on network failure for safe retry', async () => {
    vi.mocked(api.recordOutfitWorn).mockRejectedValueOnce(
      new api.ApiError('Lỗi mạng tạm thời', 'TIMEOUT', 504)
    );

    render(
      <OutfitCard
        outfitId="outfit-101"
        explanationVi="Phối đồ thanh lịch"
        items={mockItems}
        initialTimesWorn={0}
      />
    );

    const wearBtn = screen.getByRole('button', {
      name: /Xác nhận đã mặc bộ trang phục này hôm nay/i,
    });

    // First attempt fails
    fireEvent.click(wearBtn);

    await waitFor(() => {
      expect(screen.getByText(/✕ Lỗi mạng tạm thời/i)).toBeDefined();
    });

    const firstKey = vi.mocked(api.recordOutfitWorn).mock.calls[0][1].idempotency_key;

    // Second attempt succeeds
    vi.mocked(api.recordOutfitWorn).mockResolvedValueOnce({
      wear_log_id: 'wear-log-1',
      outfit_id: 'outfit-101',
      times_worn: 1,
      already_processed: false,
      worn_at: '2026-09-15T08:31:00Z',
    });

    fireEvent.click(wearBtn);

    await waitFor(() => {
      expect(screen.getByText(/Đã ghi nhận bạn mặc bộ này!/i)).toBeDefined();
    });

    const secondKey = vi.mocked(api.recordOutfitWorn).mock.calls[1][1].idempotency_key;
    // CRITICAL IDEMPOTENCY CHECK: retry must reuse the exact same key!
    expect(secondKey).toBe(firstKey);
  });

  it('generateUUIDv4 produces RFC 4122 v4 compliant UUID in native and fallback mode', () => {
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    // Native mode
    const nativeKey = generateUUIDv4();
    expect(nativeKey).toMatch(uuidRegex);

    // Fallback mode (when crypto.randomUUID is undefined)
    const originalRandomUUID = crypto.randomUUID;
    try {
      // @ts-expect-error - simulate environment without crypto.randomUUID
      crypto.randomUUID = undefined;
      const fallbackKey = generateUUIDv4();
      expect(fallbackKey).toMatch(uuidRegex);
      expect(fallbackKey.charAt(14)).toBe('4');
      expect(['8', '9', 'a', 'b']).toContain(fallbackKey.charAt(19).toLowerCase());
    } finally {
      crypto.randomUUID = originalRandomUUID;
    }
  });

  it('localizes outerwear and accessory slots accurately', () => {
    const extendedItems = [
      {
        id: 'item-outerwear',
        slot: 'outerwear',
        name: 'Áo khoác dạ dáng dài',
        imageUrl: null,
      },
      {
        id: 'item-accessory',
        slot: 'accessory',
        name: 'Khăn len cashmere',
        imageUrl: null,
      },
    ];

    render(
      <OutfitCard
        outfitId="outfit-ext"
        explanationVi="Phối đồ mùa đông"
        items={extendedItems}
      />
    );

    expect(screen.getByText('Áo khoác dạ dáng dài')).toBeDefined();
    expect(screen.getByText('Khăn len cashmere')).toBeDefined();
    expect(screen.getByText('Vị trí: Áo khoác')).toBeDefined();
    expect(screen.getByText('Vị trí: Phụ kiện')).toBeDefined();
  });

  it('synchronizes internal state when parent updates initialIsBookmarked and initialTimesWorn props', () => {
    const { rerender } = render(
      <OutfitCard
        outfitId="outfit-sync"
        explanationVi="Set đồ"
        items={mockItems}
        initialIsBookmarked={false}
        initialTimesWorn={1}
      />
    );

    const bookmarkBtn = screen.getByRole('button', { name: /Lưu bộ đồ này/i });
    expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getAllByText(/Đã mặc 1 lần/i).length).toBeGreaterThanOrEqual(1);

    // Parent updates props (e.g. from server refetch)
    rerender(
      <OutfitCard
        outfitId="outfit-sync"
        explanationVi="Set đồ"
        items={mockItems}
        initialIsBookmarked={true}
        initialTimesWorn={5}
      />
    );

    expect(bookmarkBtn.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getAllByText(/Đã mặc 5 lần/i).length).toBeGreaterThanOrEqual(1);
  });
});
