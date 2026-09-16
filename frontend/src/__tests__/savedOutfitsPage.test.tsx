import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SavedOutfitsPage from '@/app/saved/page';
import * as api from '@/lib/api';
import type { SavedOutfitsResponseData } from '@/types/outfits';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    getSavedOutfits: vi.fn(),
    setOutfitBookmark: vi.fn(),
    recordOutfitWorn: vi.fn(),
    rateOutfit: vi.fn(),
  };
});

describe('SavedOutfitsPage Integration', () => {
  const mockSavedData: SavedOutfitsResponseData = {
    items: [
      {
        id: 'outfit-1',
        request_id: 'req-1',
        user_query: 'đi làm thứ hai',
        rank: 1,
        fashion_score: 0.95,
        personalization_score: 0.90,
        composite_score: 0.92,
        explanation_vi: 'Set đồ thanh lịch đi làm thứ hai đầu tuần.',
        is_bookmarked: true,
        times_worn: 3,
        last_worn_at: '2026-09-14T09:00:00Z',
        user_rating: 4,
        created_at: '2026-09-10T10:00:00Z',
        items: [
          {
            wardrobe_item_id: 'wi-1',
            slot_role: 'top' as const,
            name: 'Áo sơ mi lụa trắng',
            category: 'top' as const,
            sub_category: 'shirt',
            primary_color: 'Trắng',
            pattern: 'trơn',
            material: 'lụa',
            style: 'thanh lịch',
            image_url: '/media/shirt.jpg',
            is_active: true,
          },
          {
            wardrobe_item_id: 'wi-2',
            slot_role: 'bottom' as const,
            name: 'Chân váy bút chì đen',
            category: 'bottom' as const,
            sub_category: 'skirt',
            primary_color: 'Đen',
            pattern: 'trơn',
            material: 'cotton',
            style: 'công sở',
            image_url: null,
            is_active: true,
          },
        ],
      },
      {
        id: 'outfit-2',
        request_id: 'req-2',
        user_query: 'dạo phố cuối tuần',
        rank: 2,
        fashion_score: 0.89,
        personalization_score: 0.87,
        composite_score: 0.88,
        explanation_vi: 'Set đồ năng động dạo phố cuối tuần.',
        is_bookmarked: true,
        times_worn: 0,
        last_worn_at: null,
        created_at: '2026-09-11T14:00:00Z',
        items: [
          {
            wardrobe_item_id: 'wi-3',
            slot_role: 'top' as const,
            name: 'Áo thun polo xám',
            category: 'top' as const,
            sub_category: 'polo',
            primary_color: 'Xám',
            pattern: 'trơn',
            material: 'cotton',
            style: 'năng động',
            image_url: null,
            is_active: true,
          },
        ],
      },
    ],
    total: 25,
    page: 1,
    page_size: 10,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
  });

  it('renders loading skeleton initially while fetching saved outfits', async () => {
    let resolvePromise: (val: SavedOutfitsResponseData) => void;
    const pendingPromise = new Promise<SavedOutfitsResponseData>((resolve) => {
      resolvePromise = resolve;
    });

    vi.mocked(api.getSavedOutfits).mockReturnValueOnce(pendingPromise);

    render(<SavedOutfitsPage />);

    expect(screen.getByRole('status')).toBeDefined();

    resolvePromise!(mockSavedData);

    await waitFor(() => {
      expect(screen.queryByRole('status')).toBeNull();
      expect(screen.getByText('Bộ Trang Phục Đã Lưu')).toBeDefined();
    });
  });

  it('renders empty state with CTA to /chat when user has no saved outfits', async () => {
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
    });

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      expect(screen.getByTestId('saved-outfits-empty')).toBeDefined();
      expect(screen.getByText('Bạn Chưa Lưu Bộ Trang Phục Nào')).toBeDefined();
    });

    const ctaLink = screen.getByRole('link', { name: /Nhờ Stylist Gợi Ý Ngay/i });
    expect(ctaLink.getAttribute('href')).toBe('/chat');
  });

  it('renders error state and handles retry button click', async () => {
    vi.mocked(api.getSavedOutfits).mockRejectedValueOnce(
      new api.ApiError('Lỗi tải dữ liệu tủ đồ', 'SERVER_ERROR', 500)
    );

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
      expect(screen.getByText('Lỗi tải dữ liệu tủ đồ')).toBeDefined();
    });

    // Setup success on retry
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockSavedData);

    const retryBtn = screen.getByRole('button', { name: /Thử lại/i });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText(/Set đồ thanh lịch đi làm/i)).toBeDefined();
    });
    expect(api.getSavedOutfits).toHaveBeenCalledTimes(2);
  });

  it('renders saved outfits list and allows pagination to page 2', async () => {
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockSavedData);

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      expect(screen.getByText('Tổng cộng 25 bộ đồ')).toBeDefined();
      expect(screen.getByText(/Set đồ thanh lịch đi làm/i)).toBeDefined();
      expect(screen.getByText(/Set đồ năng động dạo phố/i)).toBeDefined();
    });

    // Pagination info
    expect(screen.getByText(/Trang 1 \/ 3/i)).toBeDefined();

    // Prepare page 2 mock response
    const mockPage2Data: SavedOutfitsResponseData = {
      items: [
        {
          id: 'outfit-3',
          request_id: 'req-3',
          user_query: 'đi tiệc tối',
          rank: 1,
          fashion_score: 0.92,
          personalization_score: 0.88,
          composite_score: 0.9,
          explanation_vi: 'Set đồ trang phục trang trọng đi tiệc.',
          is_bookmarked: true,
          times_worn: 1,
          last_worn_at: null,
          created_at: '2026-09-08T10:00:00Z',
          items: [],
        },
      ],
      total: 25,
      page: 2,
      page_size: 10,
    };
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockPage2Data);

    const nextBtn = screen.getByRole('button', { name: /Trang sau/i });
    fireEvent.click(nextBtn);

    await waitFor(() => {
      expect(api.getSavedOutfits).toHaveBeenLastCalledWith({ page: 2, page_size: 10 });
      expect(screen.getByText(/Set đồ trang phục trang trọng đi tiệc/i)).toBeDefined();
    });
    expect(window.scrollTo).toHaveBeenCalled();
  });

  it('updates local state when an outfit is unbookmarked from the page', async () => {
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockSavedData);
    vi.mocked(api.setOutfitBookmark).mockResolvedValueOnce({
      outfit_id: 'outfit-1',
      is_bookmarked: false,
      updated_at: '2026-09-15T09:00:00Z',
    });

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      expect(screen.getByText(/Set đồ thanh lịch đi làm/i)).toBeDefined();
    });

    const unbookmarkBtns = screen.getAllByRole('button', { name: /Bỏ lưu bộ đồ này/i });
    expect(unbookmarkBtns.length).toBe(2);

    fireEvent.click(unbookmarkBtns[0]);

    await waitFor(() => {
      expect(api.setOutfitBookmark).toHaveBeenCalledWith('outfit-1', false);
    });
  });

  it('auto-recovers to valid previous page and avoids showing empty state when page drift occurs', async () => {
    // Initial fetch for page 1
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockSavedData);

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      expect(screen.getByText('Tổng cộng 25 bộ đồ')).toBeDefined();
    });

    // Simulate page 2 returns 0 items while total is still 10
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce({
      items: [],
      total: 10,
      page: 2,
      page_size: 10,
    });

    const nextBtn = screen.getByRole('button', { name: /Trang sau/i });
    fireEvent.click(nextBtn);

    // Mock the auto-recovery response for page 1
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce({
      ...mockSavedData,
      total: 10,
    });

    await waitFor(() => {
      // Must NOT show global empty state because total is 10
      expect(screen.queryByTestId('saved-outfits-empty')).toBeNull();
      // Verifies it auto-requested page 1
      expect(api.getSavedOutfits).toHaveBeenLastCalledWith({ page: 1, page_size: 10 });
    });
  });

  it('renders initial ratings on saved cards and allows rating an outfit with source: "manual"', async () => {
    vi.mocked(api.getSavedOutfits).mockResolvedValueOnce(mockSavedData);
    vi.mocked(api.rateOutfit).mockResolvedValueOnce({
      rating_id: 'rating-saved-1',
      outfit_id: 'outfit-2',
      stars: 5,
      source: 'manual',
      ratings_count: 2,
      created_at: '2026-09-15T08:00:00Z',
      updated_at: '2026-09-15T08:00:00Z',
    });

    render(<SavedOutfitsPage />);

    await waitFor(() => {
      // outfit-1 has user_rating: 4
      expect(screen.getByText('4/5★')).toBeDefined();
    });

    // Find outfit-2 card
    const outfitCards = screen.getAllByTestId('outfit-card');
    const outfit2Card = outfitCards.find((c) => c.getAttribute('data-outfit-id') === 'outfit-2');
    expect(outfit2Card).toBeDefined();

    // Click star 5 on outfit-2
    const star5Btn = outfit2Card!.querySelector('button[aria-label="Đánh giá 5 sao"]');
    expect(star5Btn).not.toBeNull();
    fireEvent.click(star5Btn!);

    await waitFor(() => {
      expect(api.rateOutfit).toHaveBeenCalledWith('outfit-2', {
        stars: 5,
        source: 'manual',
      });
    });

    // outfit-2 should now display 5/5★
    await waitFor(() => {
      expect(screen.getByText('5/5★')).toBeDefined();
    });
  });
});
