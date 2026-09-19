import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
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
