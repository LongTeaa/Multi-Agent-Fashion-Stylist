import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  getIngestionBatch: vi.fn(), uploadIngestionImages: vi.fn(),
  confirmIngestionBatch: vi.fn(), deleteIngestionBatch: vi.fn(), updateDetectionCrop: vi.fn(),
  ApiError: class extends Error {},
}));
vi.mock('@/components/media/PrivateMediaImage', () => ({
  PrivateMediaImage: ({ alt }: { alt: string }) => <span>{alt}</span>,
}));
vi.mock('@/components/ingestion/BoundingBoxOverlay', () => ({
  BoundingBoxOverlay: () => null,
}));
vi.mock('@/components/ingestion/DetectionItemCard', () => ({
  DetectionItemCard: ({ detection }: { detection: { detection_id: string } }) => <div>{detection.detection_id}</div>,
}));

afterEach(() => { cleanup(); sessionStorage.clear(); vi.useRealTimers(); vi.resetAllMocks(); });

it('retains a processing batch after 45 seconds and scopes review to the selected source', async () => {
  vi.useFakeTimers();
  sessionStorage.setItem('active_ingestion_batch_id', 'batch');
  const processing = { batch_id: 'batch', status: 'processing', input_kind: 'unknown', quality_warnings: [], detections: [] };
  vi.mocked(api.getIngestionBatch).mockResolvedValue(processing);
  render(<IngestionWorkflow />);
  for (let i = 0; i < 32; i++) {
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
  }
  expect(sessionStorage.getItem('active_ingestion_batch_id')).toBe('batch');
  expect(screen.queryByText(/Không Thể Hoàn Tất/)).toBeNull();
  vi.mocked(api.getIngestionBatch).mockResolvedValue({
    ...processing, status: 'needs_review', source_images: [
      { media_asset_id: 'a', media_url: '/api/v1/media/a', width: 100, height: 100 },
      { media_asset_id: 'b', media_url: '/api/v1/media/b', width: 100, height: 100 },
    ], detections: [
      { detection_id: 'red-item', source_media_asset_id: 'a', crop_url: '/a', bounding_box: [0, 0, 1, 1], attributes: { category: 'top' }, field_confidence: {} },
      { detection_id: 'blue-item', source_media_asset_id: 'b', crop_url: '/b', bounding_box: [0, 0, 1, 1], attributes: { category: 'top' }, field_confidence: {} },
    ],
  });
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
  expect(screen.getByText('red-item')).toBeDefined();
  expect(screen.queryByText('blue-item')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /Ảnh 2/ }));
  expect(screen.getByText('blue-item')).toBeDefined();
  expect(screen.queryByText('red-item')).toBeNull();
});
