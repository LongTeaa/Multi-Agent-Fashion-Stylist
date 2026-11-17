import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import Home from '@/app/page';
import * as api from '@/lib/api';

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element -- plain img stands in for next/image in jsdom
  default: ({ src, alt }: { src: string; alt: string }) => <img src={src} alt={alt} />,
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    listWardrobeItems: vi.fn(),
    getSavedOutfits: vi.fn(),
    getUserProfile: vi.fn(),
  };
});

describe('Home page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getSavedOutfits).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 });
    vi.mocked(api.getUserProfile).mockRejectedValue(new Error('offline'));
  });

  it('does not show the stylist form before the wardrobe summary arrives', async () => {
    vi.mocked(api.listWardrobeItems).mockReturnValue(new Promise(() => {}));

    render(<Home />);

    expect(screen.queryByLabelText('Bạn sẽ đi đâu hôm nay?')).toBeNull();
    expect(screen.getByText('Đang mở tủ đồ…')).toBeDefined();
  });

  it('shows onboarding, not the stylist form, for an empty wardrobe', async () => {
    vi.mocked(api.listWardrobeItems).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 6 });

    render(<Home />);

    expect(await screen.findByRole('link', { name: /Thêm món đồ đầu tiên/ })).toBeDefined();
    expect(screen.queryByLabelText('Bạn sẽ đi đâu hôm nay?')).toBeNull();
  });

  it('reports a failed wardrobe request instead of claiming the wardrobe is empty', async () => {
    vi.mocked(api.listWardrobeItems).mockRejectedValue(new Error('offline'));

    render(<Home />);

    expect(await screen.findByText(/Chưa tải được tủ đồ/)).toBeDefined();
    expect(screen.queryByText(/Chưa có món nào/)).toBeNull();
    expect(screen.getByLabelText('Bạn sẽ đi đâu hôm nay?')).toBeDefined();
  });
});
