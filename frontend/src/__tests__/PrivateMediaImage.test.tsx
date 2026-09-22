import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import { setStoredUserId } from '@/lib/api';

afterEach(() => {
  vi.unstubAllGlobals();
});

it('fetches private media with the user header and revokes its blob URL', async () => {
  const userId = '550e8400-e29b-41d4-a716-446655440000';
  setStoredUserId(userId);
  const fetchMedia = vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => new Blob(['image'], { type: 'image/png' }),
  });
  vi.stubGlobal('fetch', fetchMedia);
  const createUrl = vi.fn().mockReturnValue('blob:private-image');
  const revokeUrl = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeUrl });

  const rendered = render(
    <PrivateMediaImage source="/api/v1/media/asset-id" alt="Áo polo" />
  );

  await waitFor(() => expect(screen.getByAltText('Áo polo').getAttribute('src')).toBe('blob:private-image'));
  expect(fetchMedia).toHaveBeenCalledWith(
    'http://localhost:8000/api/v1/media/asset-id',
    expect.objectContaining({ headers: { 'X-User-Id': userId } })
  );
  rendered.unmount();
  expect(revokeUrl).toHaveBeenCalledWith('blob:private-image');
});

it('renders error fallback with retry button when fetch fails and allows retry', async () => {
  const userId = '550e8400-e29b-41d4-a716-446655440000';
  setStoredUserId(userId);
  const fetchMedia = vi
    .fn()
    .mockRejectedValueOnce(new Error('Network error'))
    .mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(['image'], { type: 'image/png' }),
    });
  vi.stubGlobal('fetch', fetchMedia);
  const createUrl = vi.fn().mockReturnValue('blob:retry-success');
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });

  render(<PrivateMediaImage source="/api/v1/media/asset-fail" alt="Ảnh lỗi" />);

  // Should show error fallback and retry button
  await waitFor(() => expect(screen.getByText('Không thể tải ảnh')).toBeDefined());
  const retryBtn = screen.getByRole('button', { name: /Thử tải lại ảnh/i });
  expect(retryBtn).toBeDefined();

  // Click retry
  fireEvent.click(retryBtn);

  // Fetch should be retried and image displayed
  await waitFor(() => expect(screen.getByAltText('Ảnh lỗi').getAttribute('src')).toBe('blob:retry-success'));
  expect(fetchMedia).toHaveBeenCalledTimes(2);
});

it('passes blob URLs directly without fetching via private media API', () => {
  const fetchMedia = vi.fn();
  vi.stubGlobal('fetch', fetchMedia);

  render(<PrivateMediaImage source="blob:http://localhost:3000/temp-blob" alt="Ảnh tạm thời" />);

  const img = screen.getByAltText('Ảnh tạm thời');
  expect(img.getAttribute('src')).toBe('blob:http://localhost:3000/temp-blob');
  expect(fetchMedia).not.toHaveBeenCalled();
});
