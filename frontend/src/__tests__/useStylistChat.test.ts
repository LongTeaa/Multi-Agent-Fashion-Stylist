import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStylistChat } from '@/hooks/useStylistChat';
import * as apiModule from '@/lib/api';
import { ApiError } from '@/lib/api';
import type { StylistChatResponseData } from '@/types/chat';

describe('useStylistChat Hook', () => {
  const mockSuccessResponse: StylistChatResponseData = {
    request_id: 'req-success-123',
    needs_clarification: false,
    clarification_question: null,
    context: {
      occasion: 'cafe',
      time_of_day: 'evening',
      event_date: null,
      location_text: 'Đà Lạt',
      environment: 'outdoor',
      weather_condition: 'cold',
      temperature_celsius: 16,
      target_formality_range: [2, 3],
      style_hints: ['smart_casual'],
      vibe_keywords: ['lịch sự nhẹ'],
      must_have: [],
      must_avoid: [],
      weather_source: 'user',
    },
    recommendations: [
      {
        outfit_id: 'outfit-1',
        rank: 1,
        composite_score: 0.92,
        items: [
          {
            slot: 'top',
            item_id: 'item-top-1',
            name: 'Áo len mỏng cổ tròn',
            image_url: '/api/v1/media/top-1',
          },
          {
            slot: 'bottom',
            item_id: 'item-bottom-1',
            name: 'Quần tây xám',
            image_url: '/api/v1/media/bottom-1',
          },
          {
            slot: 'footwear',
            item_id: 'item-shoes-1',
            name: 'Giày chelsea da',
            image_url: '/api/v1/media/shoes-1',
          },
        ],
        explanation_vi: 'Set đồ giữ ấm vừa phải và lịch sự.',
        applied_preferences: ['smart casual'],
      },
    ],
    feedback_prompt_eligible: false,
    feedback_target_outfit_id: null,
    warnings: [],
  };

  const mockClarificationResponse: StylistChatResponseData = {
    request_id: 'req-clarify-456',
    needs_clarification: true,
    clarification_question: 'Bạn muốn trang phục theo phong cách thoải mái hay thanh lịch hơn?',
    context: {
      occasion: 'cafe',
      time_of_day: null,
      event_date: null,
      location_text: null,
      environment: null,
      weather_condition: null,
      temperature_celsius: null,
      target_formality_range: [1, 3],
      style_hints: [],
      vibe_keywords: [],
      must_have: [],
      must_avoid: [],
      weather_source: 'default',
    },
    recommendations: [],
    feedback_prompt_eligible: false,
    feedback_target_outfit_id: null,
    warnings: [],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes in idle state with empty response and errors', () => {
    const { result } = renderHook(() => useStylistChat());

    expect(result.current.status).toBe('idle');
    expect(result.current.response).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.lastQuery).toBe('');
    expect(result.current.lastLocation).toBeUndefined();
  });

  it('handles successful recommendation request', async () => {
    const sendSpy = vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce(mockSuccessResponse);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi cafe Đà Lạt', 'Đà Lạt');
    });

    expect(sendSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'Đi cafe Đà Lạt',
        location: 'Đà Lạt',
        idempotency_key: expect.any(String),
      })
    );
    expect(result.current.status).toBe('success');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.response).toEqual(mockSuccessResponse);
    expect(result.current.error).toBeNull();
    expect(result.current.lastQuery).toBe('Đi cafe Đà Lạt');
    expect(result.current.lastLocation).toBe('Đà Lạt');
  });

  it('handles clarification flow (needs_clarification = true)', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce(mockClarificationResponse);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi chơi');
    });

    expect(result.current.status).toBe('clarification');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.response?.needs_clarification).toBe(true);
    expect(result.current.response?.clarification_question).toBe(
      'Bạn muốn trang phục theo phong cách thoải mái hay thanh lịch hơn?'
    );
    expect(result.current.response?.recommendations).toHaveLength(0);
    expect(result.current.error).toBeNull();
  });

  it('handles domain errors such as WARDROBE_EMPTY', async () => {
    const apiError = new ApiError('Tủ đồ rỗng.', 'WARDROBE_EMPTY', 422);
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(apiError);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi làm');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBe(apiError);
    expect(result.current.error?.code).toBe('WARDROBE_EMPTY');
    expect(result.current.response).toBeNull();
  });

  it('handles NO_COMPLETE_OUTFIT domain error', async () => {
    const apiError = new ApiError('Không thể tạo bộ phối hoàn chỉnh.', 'NO_COMPLETE_OUTFIT', 422);
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(apiError);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi bơi');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error?.code).toBe('NO_COMPLETE_OUTFIT');
  });

  it('handles NETWORK_ERROR failure and wraps non-ApiError instances', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(new Error('Connection dropped'));

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi dạo');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error?.message).toBe('Connection dropped');
  });

  it('supports retry() with the last submitted query and location', async () => {
    const sendSpy = vi
      .spyOn(apiModule, 'sendStylistChat')
      .mockRejectedValueOnce(new ApiError('Tạm thời lỗi', 'SERVICE_UNAVAILABLE', 503))
      .mockResolvedValueOnce(mockSuccessResponse);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Đi ăn tối sang trọng', 'Hà Nội');
    });

    expect(result.current.status).toBe('error');

    await act(async () => {
      await result.current.retry();
    });

    expect(sendSpy).toHaveBeenCalledTimes(2);
    const firstCallKey = sendSpy.mock.calls[0][0].idempotency_key;
    expect(sendSpy).toHaveBeenLastCalledWith({
      query: 'Đi ăn tối sang trọng',
      location: 'Hà Nội',
      idempotency_key: firstCallKey,
    });
    expect(result.current.status).toBe('success');
    expect(result.current.response).toEqual(mockSuccessResponse);
  });

  it('supports reset() and clearError()', async () => {
    vi.spyOn(apiModule, 'sendStylistChat').mockRejectedValueOnce(
      new ApiError('Lỗi', 'VALIDATION_ERROR', 422)
    );

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Test');
    });

    expect(result.current.status).toBe('error');

    act(() => {
      result.current.clearError();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.lastQuery).toBe('');
  });

  it('prevents race conditions by discarding stale out-of-order responses', async () => {
    // Request 1 is slow, Request 2 is fast
    let resolveRequest1: (val: StylistChatResponseData) => void;
    const slowPromise = new Promise<StylistChatResponseData>((resolve) => {
      resolveRequest1 = resolve;
    });

    const fastResponse: StylistChatResponseData = {
      ...mockSuccessResponse,
      request_id: 'req-fast-999',
      recommendations: [
        {
          ...mockSuccessResponse.recommendations[0],
          outfit_id: 'outfit-fast-999',
        },
      ],
    };

    const slowResponse: StylistChatResponseData = {
      ...mockSuccessResponse,
      request_id: 'req-slow-111',
      recommendations: [
        {
          ...mockSuccessResponse.recommendations[0],
          outfit_id: 'outfit-slow-111',
        },
      ],
    };

    const sendSpy = vi
      .spyOn(apiModule, 'sendStylistChat')
      .mockImplementationOnce(() => slowPromise)
      .mockResolvedValueOnce(fastResponse);

    const { result } = renderHook(() => useStylistChat());

    // 1. Dispatch Request 1 (slow)
    let p1: Promise<void>;
    act(() => {
      p1 = result.current.sendMessage('Truy vấn 1');
    });

    expect(result.current.isLoading).toBe(true);

    // 2. Dispatch Request 2 (fast)
    await act(async () => {
      await result.current.sendMessage('Truy vấn 2');
    });

    // Request 2 finishes first
    expect(result.current.status).toBe('success');
    expect(result.current.response?.request_id).toBe('req-fast-999');
    expect(result.current.response?.recommendations[0].outfit_id).toBe('outfit-fast-999');

    // 3. Now let Request 1 resolve
    await act(async () => {
      resolveRequest1!(slowResponse);
      await p1;
    });

    // CRITICAL: Request 1 must NOT overwrite Request 2!
    expect(result.current.response?.request_id).toBe('req-fast-999');
    expect(result.current.response?.recommendations[0].outfit_id).toBe('outfit-fast-999');
    expect(sendSpy).toHaveBeenCalledTimes(2);
  });

  it('strictly ignores queries exceeding 1000 characters', async () => {
    const sendSpy = vi.spyOn(apiModule, 'sendStylistChat');
    const { result } = renderHook(() => useStylistChat());

    const tooLong = 'A'.repeat(1001);
    await act(async () => {
      await result.current.sendMessage(tooLong);
    });

    expect(sendSpy).not.toHaveBeenCalled();
    expect(result.current.status).toBe('idle');
  });

  it('safely ignores response if hook unmounts while request is in flight', async () => {
    let resolveRequest: (val: StylistChatResponseData) => void;
    const delayedPromise = new Promise<StylistChatResponseData>((resolve) => {
      resolveRequest = resolve;
    });

    vi.spyOn(apiModule, 'sendStylistChat').mockImplementationOnce(() => delayedPromise);

    const { result, unmount } = renderHook(() => useStylistChat());

    let p: Promise<void>;
    act(() => {
      p = result.current.sendMessage('Truy vấn trước khi unmount');
    });

    expect(result.current.isLoading).toBe(true);

    // Unmount hook before response arrives
    unmount();

    // Now resolve
    await act(async () => {
      resolveRequest!(mockSuccessResponse);
      await p;
    });

    // Hook unmounted safely without error
  });

  it('correctly handles recommendations with dress, footwear, outerwear, and accessory slots', async () => {
    const dressOutfitResponse: StylistChatResponseData = {
      request_id: 'req-dress-789',
      needs_clarification: false,
      clarification_question: null,
      context: {
        target_formality_range: [2, 3],
        style_hints: ['elegant'],
        vibe_keywords: ['dịu dàng'],
        must_have: [],
        must_avoid: [],
        weather_source: 'user',
      },
      recommendations: [
        {
          outfit_id: 'outfit-dress-1',
          rank: 1,
          composite_score: 0.96,
          items: [
            {
              slot: 'dress',
              item_id: 'item-dress-1',
              name: 'Đầm lụa hoa nhí',
              image_url: '/api/v1/media/dress-1',
            },
            {
              slot: 'outerwear',
              item_id: 'item-outer-1',
              name: 'Áo khoác cardigan mỏng',
              image_url: '/api/v1/media/outer-1',
            },
            {
              slot: 'footwear',
              item_id: 'item-shoes-2',
              name: 'Giày búp bê mũi nhọn',
              image_url: '/api/v1/media/shoes-2',
            },
            {
              slot: 'accessory',
              item_id: 'item-acc-1',
              name: 'Túi xách kẹp nách da',
              image_url: '/api/v1/media/acc-1',
            },
          ],
          explanation_vi: 'Set đầm hoa phối cardigan và phụ kiện thanh lịch.',
          applied_preferences: ['elegant'],
        },
      ],
      feedback_prompt_eligible: false,
      feedback_target_outfit_id: null,
      warnings: [],
    };

    vi.spyOn(apiModule, 'sendStylistChat').mockResolvedValueOnce(dressOutfitResponse);

    const { result } = renderHook(() => useStylistChat());

    await act(async () => {
      await result.current.sendMessage('Gợi ý set đầm đi tiệc nhẹ');
    });

    expect(result.current.status).toBe('success');
    expect(result.current.response?.recommendations?.[0].items).toHaveLength(4);
    const slots = result.current.response?.recommendations?.[0].items.map((i) => i.slot);
    expect(slots).toEqual(['dress', 'outerwear', 'footwear', 'accessory']);
  });
});

