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

  it('renders the brand link and the 4 primary destinations with the stylist first', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: /Trang chủ/i }).getAttribute('href')).toBe('/');

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    const links = nav.querySelectorAll('a');
    expect(links.length).toBe(4);

    expect(links[0].getAttribute('href')).toBe('/chat');
    expect(links[1].getAttribute('href')).toBe('/wardrobe');
    expect(links[2].getAttribute('href')).toBe('/saved');
    expect(links[3].getAttribute('href')).toBe('/profile');
  });

  it('highlights active item and sets aria-current="page" for /wardrobe', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: 'Tủ đồ' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'Phối đồ' }).getAttribute('aria-current')).toBeNull();
  });

  it('highlights active item and sets aria-current="page" for /chat', () => {
    mockUsePathname.mockReturnValue('/chat');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: 'Phối đồ' }).getAttribute('aria-current')).toBe('page');
    expect(screen.getByRole('link', { name: 'Tủ đồ' }).getAttribute('aria-current')).toBeNull();
  });

  it('highlights active item and sets aria-current="page" for /saved', () => {
    mockUsePathname.mockReturnValue('/saved');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: 'Đã lưu' }).getAttribute('aria-current')).toBe('page');
  });

  it('highlights active item and sets aria-current="page" for /profile', () => {
    mockUsePathname.mockReturnValue('/profile');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: 'Gu của tôi' }).getAttribute('aria-current')).toBe('page');
  });

  it('does not mark a destination active for an unrelated path sharing a prefix', () => {
    mockUsePathname.mockReturnValue('/savedsearch');
    render(<AppHeader />);

    expect(screen.getByRole('link', { name: 'Đã lưu' }).getAttribute('aria-current')).toBeNull();
  });

  it('renders one text label per destination (icons are decorative)', () => {
    mockUsePathname.mockReturnValue('/wardrobe');
    render(<AppHeader />);

    const nav = screen.getByRole('navigation', { name: 'Điều hướng chính' });
    for (const item of NAV_ITEMS) {
      expect(within(nav).getByText(item.label)).toBeDefined();
    }
    nav.querySelectorAll('svg').forEach((icon) => {
      expect(icon.getAttribute('aria-hidden')).toBe('true');
    });
  });
});
