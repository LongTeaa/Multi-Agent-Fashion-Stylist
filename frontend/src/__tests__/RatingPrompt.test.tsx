import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { RatingPrompt } from '@/components/feedback/RatingPrompt';
import * as api from '@/lib/api';
import { ApiError } from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    rateOutfit: vi.fn(),
    dismissFeedbackPrompt: vi.fn(),
    getStoredSessionId: vi.fn(() => '11111111-1111-4111-8111-111111111111'),
  };
});

describe('RatingPrompt Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders prompt copy, target rank badge, and 5 star buttons', () => {
    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        targetRank={1}
      />
    );

    // Region accessibility
    expect(screen.getByRole('region', { name: /Khảo sát đánh giá gợi ý phối đồ/i })).toBeDefined();

    // Copy check
    expect(screen.getByText('Bạn chấm gợi ý vừa rồi mấy sao?')).toBeDefined();
    expect(screen.getByText('Set #1')).toBeDefined();

    // 5 stars buttons
    for (let s = 1; s <= 5; s++) {
      expect(screen.getByRole('button', { name: `Đánh giá ${s} sao` })).toBeDefined();
    }

    // Dismiss buttons: close 'X' and 'Để sau'
    expect(screen.getByRole('button', { name: /Đóng khảo sát đánh giá/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Để sau/i })).toBeDefined();

    // INVARIANT: Strictly no like/dislike buttons
    expect(screen.queryByRole('button', { name: /thích/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /không thích/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /like/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /dislike/i })).toBeNull();
  });

  it('submits rating with source "prompted" and client_session_id, shows confirmation, and auto-dismisses', async () => {
    vi.useFakeTimers();

    vi.mocked(api.rateOutfit).mockResolvedValueOnce({
      rating_id: 'rating-1',
      outfit_id: 'outfit-101',
      stars: 5,
      source: 'prompted',
      ratings_count: 1,
      created_at: '2026-09-15T08:00:00Z',
      updated_at: '2026-09-15T08:00:00Z',
    });

    const onRated = vi.fn();
    const onDismiss = vi.fn();

    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        targetRank={1}
        onRated={onRated}
        onDismiss={onDismiss}
      />
    );

    const star5Btn = screen.getByRole('button', { name: 'Đánh giá 5 sao' });
    fireEvent.click(star5Btn);

    await act(async () => {
      // Allow async rateOutfit promise to resolve
    });

    expect(api.rateOutfit).toHaveBeenCalledWith('outfit-101', {
      stars: 5,
      source: 'prompted',
      client_session_id: '11111111-1111-4111-8111-111111111111',
    });

    // Thank-you message is visible immediately
    expect(screen.getByText('Cảm ơn bạn đã phản hồi!')).toBeDefined();
    // onRated and onDismiss are not yet fired until timer expires
    expect(onRated).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();

    // Fast-forward auto-dismiss timer (1500ms)
    act(() => {
      vi.advanceTimersByTime(1500);
    });

    expect(onRated).toHaveBeenCalledWith('outfit-101', 5);
    expect(onDismiss).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });

  it('supports keyboard navigation via onFocus and onBlur on star buttons', () => {
    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
      />
    );

    const star4Btn = screen.getByRole('button', { name: 'Đánh giá 4 sao' });
    fireEvent.focus(star4Btn);

    const star4Svg = star4Btn.querySelector('svg');
    expect(star4Svg?.getAttribute('class')).toContain('fill-amber-400');

    fireEvent.blur(star4Btn);
    expect(star4Svg?.getAttribute('class')).toContain('fill-none');
  });

  it('handles dismiss via "Để sau" button: calls dismissFeedbackPrompt and onDismiss', async () => {
    vi.mocked(api.dismissFeedbackPrompt).mockResolvedValueOnce({
      cooldown_remaining: 3,
      dismissed: true,
    });

    const onDismiss = vi.fn();

    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        onDismiss={onDismiss}
      />
    );

    const dismissBtn = screen.getByRole('button', { name: /Để sau/i });
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(api.dismissFeedbackPrompt).toHaveBeenCalledWith({
        client_session_id: '11111111-1111-4111-8111-111111111111',
      });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('handles dismiss via "✕" icon button: calls dismissFeedbackPrompt and onDismiss', async () => {
    vi.mocked(api.dismissFeedbackPrompt).mockResolvedValueOnce({
      cooldown_remaining: 3,
      dismissed: true,
    });

    const onDismiss = vi.fn();

    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        onDismiss={onDismiss}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /Đóng khảo sát đánh giá/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(api.dismissFeedbackPrompt).toHaveBeenCalledWith({
        client_session_id: '11111111-1111-4111-8111-111111111111',
      });
    });

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it('displays error and keeps prompt open if dismiss API call fails', async () => {
    vi.mocked(api.dismissFeedbackPrompt).mockRejectedValueOnce(
      new ApiError('Network error', 'NETWORK_ERROR', 500)
    );

    const onDismiss = vi.fn();

    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        onDismiss={onDismiss}
      />
    );

    const dismissBtn = screen.getByRole('button', { name: /Để sau/i });
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(api.dismissFeedbackPrompt).toHaveBeenCalledTimes(1);
    });

    // Should display error message and keep prompt open rather than swallowing silently
    expect(screen.getByText('Network error')).toBeDefined();
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('displays error alert when rateOutfit fails and leaves prompt open for retry', async () => {
    vi.mocked(api.rateOutfit).mockRejectedValueOnce(
      new ApiError('Hệ thống bận, vui lòng thử lại.', 'SERVICE_UNAVAILABLE', 503)
    );

    const onRated = vi.fn();
    const onDismiss = vi.fn();

    render(
      <RatingPrompt
        targetOutfitId="outfit-101"
        onRated={onRated}
        onDismiss={onDismiss}
      />
    );

    const star3Btn = screen.getByRole('button', { name: 'Đánh giá 3 sao' });
    fireEvent.click(star3Btn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(screen.getByText('Hệ thống bận, vui lòng thử lại.')).toBeDefined();
    expect(onRated).not.toHaveBeenCalled();
    expect(onDismiss).not.toHaveBeenCalled();
  });
});
