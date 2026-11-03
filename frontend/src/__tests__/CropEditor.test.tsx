import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { CropEditor } from '@/components/ingestion/CropEditor';

vi.mock('@/components/media/PrivateMediaImage', () => ({ PrivateMediaImage: () => <span>Ảnh thử</span> }));

it('restores the original AI box only when the user explicitly saves', async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  render(<CropEditor source="/api/v1/media/test" initialBox={[0, 0, 1, 1]}
    rawBox={[.1, .2, .8, .9]} onSave={save} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chỉnh vùng cắt' }));
  fireEvent.click(screen.getByRole('button', { name: 'Khung AI gốc' }));
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Lưu vùng cắt' }));
  await waitFor(() => expect(save).toHaveBeenCalledWith([.1, .2, .8, .9]));
});

it('does not invent an original AI box for legacy detections', () => {
  render(<CropEditor source="/api/v1/media/test" initialBox={[0, 0, 1, 1]} onSave={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Chỉnh vùng cắt' }));
  expect(screen.queryByRole('button', { name: 'Khung AI gốc' })).toBeNull();
});
