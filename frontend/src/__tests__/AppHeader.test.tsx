import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { AppHeader, NAV_ITEMS } from '@/components/navigation/AppHeader';

const mockUsePathname = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
}));

describe('AppHeader Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders brand logo and all 4 primary navigation links in exact order', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    expect(nav).toBeDefined();

    const links = nav.querySelectorAll('a');
    expect(links.length).toBe(4);

    expect(links[0].getAttribute('href')).toBe('/wardrobe');
    expect(links[1].getAttribute('href')).toBe('/chat');
    expect(links[2].getAttribute('href')).toBe('/saved');
    expect(links[3].getAttribute('href')).toBe('/profile');
  });

  it('highlights active item and sets aria-current="page" for /wardrobe', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    const wardrobeLink = screen.getByRole('link', { name: /Tủ Đồ/i });
    expect(wardrobeLink.getAttribute('aria-current')).toBe('page');

    const chatLink = screen.getByRole('link', { name: /Tư Vấn Phối Đồ/i });
    expect(chatLink.getAttribute('aria-current')).toBeNull();
  });

  it('highlights active item and sets aria-current="page" for /chat', () => {
    mockUsePathname.mockReturnValue('/chat');
    render(<AppHeader />);

    const chatLink = screen.getByRole('link', { name: /Tư Vấn Phối Đồ/i });
    expect(chatLink.getAttribute('aria-current')).toBe('page');

    const wardrobeLink = screen.getByRole('link', { name: /Tủ Đồ/i });
    expect(wardrobeLink.getAttribute('aria-current')).toBeNull();
  });

  it('highlights active item and sets aria-current="page" for /saved', () => {
    mockUsePathname.mockReturnValue('/saved');
    render(<AppHeader />);

    const savedLink = screen.getByRole('link', { name: /Bộ Đồ Đã Lưu/i });
    expect(savedLink.getAttribute('aria-current')).toBe('page');
  });

  it('highlights active item and sets aria-current="page" for /profile', () => {
    mockUsePathname.mockReturnValue('/profile');
    render(<AppHeader />);

    const profileLink = screen.getByRole('link', { name: /Gu Thời Trang/i });
    expect(profileLink.getAttribute('aria-current')).toBe('page');
  });

  it('renders responsive mobile labels for all items', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.mobileLabel)).toBeDefined();
      expect(within(nav).getByText(item.label)).toBeDefined();
    }
  });
});
