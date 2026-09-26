import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WardrobeInventory } from '@/components/wardrobe/WardrobeInventory';
import * as api from '@/lib/api';
import type { WardrobeItem } from '@/types/wardrobe';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    listWardrobeItems: vi.fn(),
    updateWardrobeItem: vi.fn(),
    deleteWardrobeItem: vi.fn(),
  };
});

describe('WardrobeInventory Component', () => {
  const mockItems: WardrobeItem[] = [
    {
      id: 'item-1',
      category: 'top',
      sub_category: 'Áo polo trắng',
      primary_color: 'Trắng',
      secondary_color: null,
      pattern: 'trơn',
      material: 'cotton',
      style: 'casual',
      fit: 'regular',
      formality_level: 3,
      comfort_level: 4,
      silhouette_level: 3,
      length: 'hip',
      season: ['mùa hè'],
      weather_suitability: ['ấm áp'],
      functional_flags: ['movement', 'sun'],
      free_text_tags: ['polo'],
      is_active: true,
      times_worn: 2,
      last_worn_at: '2026-09-15T10:00:00Z',
      media_url: '/media/polo.jpg',
      thumbnail_url: '/media/polo_thumb.jpg',
    },
    {
      id: 'item-2',
      category: 'bottom',
      sub_category: 'Quần jeans xanh',
      primary_color: 'Xanh denim',
      secondary_color: null,
      pattern: 'trơn',
      material: 'denim',
      style: 'casual',
      fit: 'slim',
      formality_level: 2,
      comfort_level: 3,
      silhouette_level: 2,
      length: 'long',
      season: ['quanh năm'],
      weather_suitability: ['mát mẻ'],
      functional_flags: [],
      free_text_tags: ['jeans'],
      is_active: true,
      times_worn: 5,
      last_worn_at: '2026-09-17T12:00:00Z',
      media_url: '/media/jeans.jpg',
      thumbnail_url: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially and displays items after fetch', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: mockItems,
      total: 2,
      page: 1,
      page_size: 12,
    });

    render(<WardrobeInventory />);

    expect(screen.getByTestId('wardrobe-loading')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText('Áo polo trắng')).toBeDefined();
      expect(screen.getByText('Quần jeans xanh')).toBeDefined();
    });

    expect(screen.getByText(/Quản lý 2 món trang phục/)).toBeDefined();
  });

  it('renders empty state when no items are returned', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
    });

    const onSwitch = vi.fn();
    render(<WardrobeInventory onSwitchToIngestion={onSwitch} />);

    await waitFor(() => {
      expect(screen.getByText('Chưa có trang phục nào')).toBeDefined();
    });

    const switchBtn = screen.getByText('+ Số Hóa Trang Phục Ngay');
    fireEvent.click(switchBtn);
    expect(onSwitch).toHaveBeenCalledTimes(1);
  });

  it('filters by category when category pill is clicked', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValue({
      items: [mockItems[0]],
      total: 1,
      page: 1,
      page_size: 12,
    });

    render(<WardrobeInventory />);

    await waitFor(() => {
      expect(screen.getByTestId('category-filter-top')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('category-filter-top'));

    await waitFor(() => {
      expect(api.listWardrobeItems).toHaveBeenCalledWith(
        expect.objectContaining({
          category: 'top',
        })
      );
    });
  });

  it('searches for items on form submit', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValue({
      items: [mockItems[1]],
      total: 1,
      page: 1,
      page_size: 12,
    });

    render(<WardrobeInventory />);

    const searchInput = screen.getByTestId('wardrobe-search-input');
    fireEvent.change(searchInput, { target: { value: 'jeans' } });
    fireEvent.submit(searchInput.closest('form')!);

    await waitFor(() => {
      expect(api.listWardrobeItems).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'jeans',
        })
      );
    });
  });

  it('allows editing an item and saves changes', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: [mockItems[0]],
      total: 1,
      page: 1,
      page_size: 12,
    });

    const updatedItem = {
      ...mockItems[0],
      sub_category: 'Áo polo xanh navy',
      primary_color: 'Xanh navy',
    };
    vi.mocked(api.updateWardrobeItem).mockResolvedValueOnce(updatedItem);

    render(<WardrobeInventory />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-item-item-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('edit-item-item-1'));

    expect(screen.getByText('Chỉnh Sửa Trang Phục')).toBeDefined();

    const nameInput = screen.getByTestId('edit-sub-category');
    fireEvent.change(nameInput, { target: { value: 'Áo polo xanh navy' } });

    const colorInput = screen.getByTestId('edit-primary-color');
    fireEvent.change(colorInput, { target: { value: 'Xanh navy' } });

    fireEvent.click(screen.getByTestId('save-edit-btn'));

    await waitFor(() => {
      expect(api.updateWardrobeItem).toHaveBeenCalledWith(
        'item-1',
        expect.objectContaining({
          sub_category: 'Áo polo xanh navy',
          primary_color: 'Xanh navy',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Áo polo xanh navy')).toBeDefined();
    });
  });

  it('allows soft-deleting an item with confirmation', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: [mockItems[0]],
      total: 1,
      page: 1,
      page_size: 12,
    });
    vi.mocked(api.deleteWardrobeItem).mockResolvedValueOnce({
      item_id: 'item-1',
      is_active: false,
    });

    render(<WardrobeInventory />);

    await waitFor(() => {
      expect(screen.getByTestId('delete-item-item-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('delete-item-item-1'));

    expect(screen.getByRole('heading', { name: 'Xác Nhận Xóa' })).toBeDefined();

    fireEvent.click(screen.getByTestId('confirm-delete-btn'));

    await waitFor(() => {
      expect(api.deleteWardrobeItem).toHaveBeenCalledWith('item-1');
    });

    await waitFor(() => {
      expect(screen.queryByTestId('wardrobe-item-card-item-1')).toBeNull();
    });
  });

  it('renders primary + Số Hóa Mới action button in header and triggers callback', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: [mockItems[0]],
      total: 1,
      page: 1,
      page_size: 12,
    });

    const onSwitch = vi.fn();
    render(<WardrobeInventory onSwitchToIngestion={onSwitch} />);

    await waitFor(() => {
      expect(screen.getByTestId('btn-add-garment')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('btn-add-garment'));
    expect(onSwitch).toHaveBeenCalledTimes(1);
  });

  it('displays fashion attributes badges (comfort, silhouette, length, functional flags) on cards', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: mockItems,
      total: 2,
      page: 1,
      page_size: 12,
    });

    render(<WardrobeInventory />);

    await waitFor(() => {
      expect(screen.getByTestId('badge-comfort-item-1')).toBeDefined();
    });

    expect(screen.getByTestId('badge-comfort-item-1').textContent).toContain('Thoải mái 4/5 ⭐');
    expect(screen.getByTestId('badge-silhouette-item-1').textContent).toContain('Tiêu chuẩn');
    expect(screen.getByTestId('badge-silhouette-item-1').textContent).toContain('Ngang hông');
    expect(screen.getByText('#Vận động')).toBeDefined();
    expect(screen.getByText('#Chống nắng')).toBeDefined();
  });

  it('allows editing fashion domain attributes (comfort, silhouette, length, functional flags)', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValueOnce({
      items: [mockItems[0]],
      total: 1,
      page: 1,
      page_size: 12,
    });

    const updatedItem = {
      ...mockItems[0],
      comfort_level: 5,
      silhouette_level: 4,
      length: 'long',
      functional_flags: ['movement', 'sun', 'rain'],
    };
    vi.mocked(api.updateWardrobeItem).mockResolvedValueOnce(updatedItem);

    render(<WardrobeInventory />);

    await waitFor(() => {
      expect(screen.getByTestId('edit-item-item-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('edit-item-item-1'));

    // Change comfort to 5
    fireEvent.click(screen.getByTestId('edit-comfort-5'));

    // Change silhouette to 4 (Rộng)
    const silhouetteSelect = screen.getByTestId('edit-silhouette-level');
    fireEvent.change(silhouetteSelect, { target: { value: '4' } });

    // Change length to long
    const lengthSelect = screen.getByTestId('edit-length');
    fireEvent.change(lengthSelect, { target: { value: 'long' } });

    // Toggle rain flag
    fireEvent.click(screen.getByTestId('edit-flag-rain'));

    // Save
    fireEvent.click(screen.getByTestId('save-edit-btn'));

    await waitFor(() => {
      expect(api.updateWardrobeItem).toHaveBeenCalledWith(
        'item-1',
        expect.objectContaining({
          comfort_level: 5,
          silhouette_level: 4,
          length: 'long',
          functional_flags: expect.arrayContaining(['movement', 'sun', 'rain']),
        })
      );
    });
  });
});

