import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import { TryOnModal } from '@/components/tryon/TryOnModal';
import * as api from '@/lib/api';
import type { TryOnDisplayItem, TryOnResponseData } from '@/types/tryons';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    createTryOn: vi.fn(),
    listTryOnAvatars: vi.fn().mockResolvedValue([]),
  };
});

vi.mock('@/components/media/PrivateMediaImage', () => ({
  PrivateMediaImage: ({ alt }: { alt: string }) => <span role="img" aria-label={alt} />,
}));

const items: TryOnDisplayItem[] = [
  { id: 'vest', slot: 'outerwear', name: 'Áo gile đen' },
  { id: 'sweater', slot: 'top', name: 'Áo len xám' },
  { id: 'jeans', slot: 'bottom', name: 'Quần jeans xanh' },
  { id: 'boots', slot: 'footwear', name: 'Giày boots đen' },
  { id: 'watch', slot: 'accessory', name: 'Đồng hồ bạc' },
];

function response(rendered: string[]): TryOnResponseData {
  return {
    tryon_id: '00000000-0000-4000-8000-000000000001',
    outfit_id: 'outfit-1',
    image_url: '/api/v1/media/render',
    render_kind: 'virtual_tryon',
    fallback_used: false,
    duration_ms: 7000,
    status: 'ready',
    rendered_item_ids: rendered,
  };
}

function renderModal() {
  return render(
    <TryOnModal isOpen outfitId="outfit-1" items={items} isBookmarked={false} onBookmarkChange={vi.fn()} onClose={vi.fn()} />
  );
}

function section(heading: string): HTMLElement {
  // The list follows the heading, or the heading's row when the heading shares it with a badge.
  const title = screen.getByText(heading).closest('h3');
  const next = title?.nextElementSibling;
  const container = next && next.tagName !== 'SPAN' ? next : title?.parentElement?.nextElementSibling;
  if (!(container instanceof HTMLElement)) throw new Error(`No list after ${heading}`);
  return container;
}

describe('TryOnModal garment partition', () => {
  beforeEach(() => {
    vi.mocked(api.createTryOn).mockReset();
  });

  it('sends every item and lists what a layered render wore, without a layer toggle', async () => {
    vi.mocked(api.createTryOn).mockResolvedValue(response(['vest', 'sweater', 'jeans', 'boots']));
    renderModal();

    await waitFor(() => expect(api.createTryOn).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.createTryOn).mock.calls[0][1]?.itemIds).toEqual(['vest', 'sweater', 'jeans', 'boots', 'watch']);

    await screen.findByText('Trang phục ướm trên người');
    const worn = section('Trang phục ướm trên người');
    for (const name of ['Áo gile đen', 'Áo len xám', 'Quần jeans xanh', 'Giày boots đen']) {
      expect(within(worn).getByText(name)).toBeTruthy();
    }
    expect(within(worn).queryByText('Đồng hồ bạc')).toBeNull();
    expect(within(section('Phối kèm (không hiện trên ảnh)')).getByText('Đồng hồ bạc')).toBeTruthy();
    expect(screen.queryByText('Ướm áo trong')).toBeNull();
  });

  it('offers the layer choice when the render wore only one upper layer', async () => {
    vi.mocked(api.createTryOn)
      .mockResolvedValueOnce(response(['vest', 'jeans']))
      .mockResolvedValueOnce(response(['sweater', 'jeans']));
    renderModal();

    const innerButton = await screen.findByRole('button', { name: 'Ướm áo trong' });
    const worn = section('Trang phục ướm trên người');
    expect(within(worn).getByText('Đang ướm')).toBeTruthy();
    expect(within(worn).getByText('Bấm chọn ở trên để ướm')).toBeTruthy();
    expect(within(section('Phối kèm (không hiện trên ảnh)')).getByText('Giày boots đen')).toBeTruthy();

    fireEvent.click(innerButton);
    await waitFor(() => expect(api.createTryOn).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.createTryOn).mock.calls[1][1]?.itemIds).toEqual(['sweater', 'jeans', 'boots', 'watch']);
  });

  it('keeps the slot rule for a moodboard, which reports no rendered items', async () => {
    vi.mocked(api.createTryOn).mockResolvedValue({ ...response([]), render_kind: 'moodboard', fallback_used: true });
    renderModal();

    await screen.findByText('Moodboard dự phòng');
    const worn = section('Trang phục ướm trên người');
    expect(within(worn).getByText('Áo len xám')).toBeTruthy();
    expect(within(worn).queryByText('Giày boots đen')).toBeNull();
    expect(within(section('Phối kèm (không hiện trên ảnh)')).getByText('Giày boots đen')).toBeTruthy();
  });
});
